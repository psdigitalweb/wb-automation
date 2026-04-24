#!/usr/bin/env python3
"""Offline spike: build category-local meaning groups from query clusters and interpret them with LLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
_SCRIPT_ENV_FLAG = "ECOMCORE_QUERY_MEANING_GROUPS_SPIKE_IN_DOCKER"
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.IGNORECASE)
_ALLOWED_GROUP_TYPES = {
    "buyer_meaning",
    "functional",
    "format_set",
    "decor/interior",
    "event/holiday",
    "generic",
    "garbage",
    "mixed",
}
_SYSTEM_PROMPT = """Ты анализируешь группу поисковых запросов.

Твоя задача:
понять, ЧТО ОБЪЕДИНЯЕТ эти запросы по смыслу покупки.

Не перечисляй слова.
Не описывай формально.

Ответь:
- короткий label группы (1 строка)
- описание смысла (1–2 предложения)
- тип группы:
  - buyer_meaning (мотивация покупки)
  - functional
  - format_set
  - decor/interior
  - event/holiday
  - generic
  - garbage
  - mixed

Важно:
- не выдумывай смысл, если его нет
- если группа разнородная -> напиши "mixed"
- если это просто вариации одного товара -> functional
- если это "красиво / стиль / pinterest / мило" -> buyer_meaning
- если это "в подарок" -> buyer_meaning
- если это "мем / прикол / надпись" -> buyer_meaning

Верни JSON:
{
  "label": "...",
  "description": "...",
  "type": "...",
  "confidence": 0.0
}"""


@dataclass(frozen=True)
class ProfileRow:
    cluster_key: str
    profile_label_candidate: str
    anchor_query: str
    representative_queries: list[str]
    profile_strength: str
    meaning_text: str
    informativeness_score: int
    diversity_bucket: str


def _running_inside_container() -> bool:
    return os.getenv(_SCRIPT_ENV_FLAG) == "1" or Path("/.dockerenv").exists()


def _load_env_defaults(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _declared_database_host() -> str | None:
    env_defaults = _load_env_defaults(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL") or env_defaults.get("DATABASE_URL")
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.hostname:
            return parsed.hostname
    return os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST")


def _should_reroute_to_docker() -> bool:
    if _running_inside_container():
        return False
    database_host = _declared_database_host()
    return bool(database_host and database_host.lower() in DOCKER_ONLY_DB_HOSTS)


def _rerun_in_worker_container(argv: list[str]) -> int:
    compose_file = PROJECT_ROOT / "infra" / "docker" / "docker-compose.yml"
    ensure_stack_command = ["docker", "compose", "-f", str(compose_file), "up", "-d", "postgres", "worker"]
    exec_command = ["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"{_SCRIPT_ENV_FLAG}=1"]
    for env_name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        env_value = os.getenv(env_name)
        if env_value:
            exec_command.extend(["-e", f"{env_name}={env_value}"])
    exec_command.extend(["worker", "python", "scripts/query_meaning_groups_spike.py", *argv])
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running query meaning-groups spike in the worker container...",
        file=sys.stderr,
    )
    ensure_result = subprocess.run(ensure_stack_command, cwd=PROJECT_ROOT)
    if ensure_result.returncode != 0:
        return ensure_result.returncode
    return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode


def _extract_json_object(content: str) -> dict[str, Any]:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value)
        text_value = re.sub(r"\s*```$", "", text_value)
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model response does not contain JSON object")
    return json.loads(text_value[start : end + 1])


def _sanitize_llm_group(payload: dict[str, Any]) -> dict[str, Any]:
    label = str(payload.get("label") or "").strip()
    description = str(payload.get("description") or "").strip()
    group_type = str(payload.get("type") or "").strip()
    if group_type not in _ALLOWED_GROUP_TYPES:
        raise ValueError(f"Unsupported group type: {group_type}")
    confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    return {
        "label": label or "unlabeled group",
        "description": description or "No clear description returned.",
        "type": group_type,
        "confidence": round(confidence, 4),
    }


def _tokenize(text_value: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(str(text_value or "")) if len(token) >= 2]


def _bucket_for_text(text_value: str) -> str:
    text = text_value.lower()
    if any(pattern in text for pattern in ("подар", "надпис", "мем", "прикол", "pinterest", "эстет", "красив", "мил")):
        return "buyer_hint"
    if any(pattern in text for pattern in ("декор", "интерьер", "на стен", "новогод", "пасх", "праздник", "8 марта", "23 февраля")):
        return "decor_event_hint"
    if any(pattern in text for pattern in ("набор", "комплект", "шт", "см", "мм", "размер")):
        return "format_size"
    if any(pattern in text for pattern in ("суп", "микроволнов", "свч", "десерт", "обед", "сервиров", "для детей", "для ребенка")):
        return "functional"
    return "generic"


def _meaning_text(label: str, anchor: str, representative_queries: list[str]) -> str:
    queries_block = "\n".join(f"- {query}" for query in representative_queries) if representative_queries else "-"
    return f"{label}\nanchor: {anchor or '-'}\nqueries:\n{queries_block}".strip()


def _informativeness_score(*, label: str, anchor: str, representative_queries: list[str], profile_strength: str) -> int:
    strength_weight = {"strong": 6, "medium": 4, "weak": 2}.get(profile_strength, 1)
    unique_tokens = len(set(_tokenize(" ".join([label, anchor, *representative_queries]))))
    rep_weight = min(5, len(representative_queries))
    return strength_weight + rep_weight + min(8, unique_tokens)


def _collect_profile_rows(session: Any, *, project_id: int, category_id: int, sample_limit: int) -> tuple[list[ProfileRow], dict[str, Any]]:
    from app.services.seo.query_pipeline import get_query_clusters, run_query_profile_extraction

    profile_result = run_query_profile_extraction(
        session,
        project_id=project_id,
        category_id=category_id,
        top_limit=40,
        samples_limit=40,
        refresh_hybrid=True,
        persist=False,
    )
    clusters = get_query_clusters(session, project_id=project_id, category_id=category_id)
    cluster_by_key = {cluster.cluster_key: cluster for cluster in clusters}

    all_rows: list[ProfileRow] = []
    excluded_empty = 0
    excluded_weak_noise = 0
    for profile in profile_result.profiles:
        representative_queries: list[str] = []
        cluster = cluster_by_key.get(profile.cluster_key)
        if cluster is not None:
            for member in cluster.members[:5]:
                query = str(member.display_query or member.normalized_query_text or "").strip()
                if query and query not in representative_queries:
                    representative_queries.append(query)

        label = str(profile.profile_label_candidate or "").strip()
        anchor = str(profile.source_anchor_query or "").strip()
        meaning_text = _meaning_text(label, anchor, representative_queries)
        marker_count = 0
        if profile.profile_strength == "empty" or not meaning_text.replace("-", "").strip():
            excluded_empty += 1
            continue
        if profile.profile_strength == "weak" and len(set(_tokenize(" ".join([label, anchor, *representative_queries])))) <= 2:
            excluded_weak_noise += 1
            continue

        diversity_bucket = _bucket_for_text(" ".join([label, anchor, *representative_queries]))
        all_rows.append(
            ProfileRow(
                cluster_key=profile.cluster_key,
                profile_label_candidate=label,
                anchor_query=anchor,
                representative_queries=representative_queries,
                profile_strength=profile.profile_strength,
                meaning_text=meaning_text,
                informativeness_score=_informativeness_score(
                    label=label,
                    anchor=anchor,
                    representative_queries=representative_queries,
                    profile_strength=profile.profile_strength,
                ),
                diversity_bucket=diversity_bucket,
            )
        )

    buckets: dict[str, list[ProfileRow]] = defaultdict(list)
    for row in all_rows:
        buckets[row.diversity_bucket].append(row)
    for bucket_name in buckets:
        buckets[bucket_name].sort(
            key=lambda row: (
                -row.informativeness_score,
                0 if row.profile_strength == "strong" else 1 if row.profile_strength == "medium" else 2,
                -len(row.representative_queries),
                row.cluster_key,
            )
        )

    selected: list[ProfileRow] = []
    bucket_names = ["buyer_hint", "decor_event_hint", "functional", "format_size", "generic"]
    pointers = {name: 0 for name in bucket_names}
    while len(selected) < min(sample_limit, len(all_rows)):
        progressed = False
        for bucket_name in bucket_names:
            bucket = buckets.get(bucket_name, [])
            pointer = pointers[bucket_name]
            if pointer >= len(bucket):
                continue
            selected.append(bucket[pointer])
            pointers[bucket_name] += 1
            progressed = True
            if len(selected) >= min(sample_limit, len(all_rows)):
                break
        if not progressed:
            break

    sample_strategy = "bucketed informative sample (buyer/decor-event/functional/format/generic round-robin)"
    return selected, {
        "total_profiles_available": len(profile_result.profiles),
        "excluded_empty_profiles": excluded_empty,
        "excluded_weak_noise_profiles": excluded_weak_noise,
        "sampled_profiles": len(selected),
        "sample_strategy": sample_strategy,
    }


def _compute_embeddings(texts: list[str], *, model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    return model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)


def _top_terms(items: list[ProfileRow], *, limit: int = 10) -> list[str]:
    counter: Counter[str] = Counter()
    for item in items:
        tokens = [token for token in _tokenize(" ".join([item.profile_label_candidate, item.anchor_query, *item.representative_queries])) if len(token) >= 3]
        counter.update(tokens)
    return [term for term, _count in counter.most_common(limit)]


def _collect_samples(items: list[ProfileRow], *, label_limit: int = 25, anchor_limit: int = 20, query_limit: int = 20) -> tuple[list[str], list[str], list[str]]:
    labels: list[str] = []
    anchors: list[str] = []
    queries: list[str] = []
    for item in items:
        label = item.profile_label_candidate or "-"
        if label not in labels and len(labels) < label_limit:
            labels.append(label)
        anchor = item.anchor_query or "-"
        if anchor not in anchors and len(anchors) < anchor_limit:
            anchors.append(anchor)
        for query in item.representative_queries:
            if query not in queries and len(queries) < query_limit:
                queries.append(query)
        if len(labels) >= label_limit and len(anchors) >= anchor_limit and len(queries) >= query_limit:
            break
    return labels, anchors, queries


def _silhouette(matrix: Any, labels: Any) -> float | None:
    from sklearn.metrics import silhouette_score

    unique_labels = {int(value) for value in labels}
    if len(unique_labels) <= 1 or len(unique_labels) >= len(labels):
        return None
    return float(silhouette_score(matrix, labels, metric="cosine", sample_size=min(2000, len(labels)), random_state=42))


def _build_hdbscan_groups(rows: list[ProfileRow], embeddings: Any, *, min_cluster_size: int) -> dict[str, Any]:
    import hdbscan

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=max(5, min_cluster_size // 3), metric="euclidean")
    labels = clusterer.fit_predict(embeddings)
    groups: dict[int, list[ProfileRow]] = defaultdict(list)
    noise: list[ProfileRow] = []
    for row, label in zip(rows, labels, strict=False):
        if int(label) == -1:
            noise.append(row)
        else:
            groups[int(label)].append(row)
    silhouette = None
    non_noise_labels = [label for label in labels if int(label) != -1]
    if len(groups) > 1 and len(non_noise_labels) > 1:
        non_noise_embeddings = [embedding for embedding, label in zip(embeddings, labels, strict=False) if int(label) != -1]
        silhouette = _silhouette(non_noise_embeddings, non_noise_labels)
    return {
        "method_key": f"hdbscan_mcs{min_cluster_size}",
        "embedding_method": "hdbscan",
        "groups": groups,
        "noise": noise,
        "noise_count": len(noise),
        "silhouette": silhouette,
    }


def _build_kmeans_groups(rows: list[ProfileRow], embeddings: Any, *, k_value: int) -> dict[str, Any]:
    from sklearn.cluster import KMeans

    estimator = KMeans(n_clusters=k_value, n_init=20, random_state=42)
    labels = estimator.fit_predict(embeddings)
    groups: dict[int, list[ProfileRow]] = defaultdict(list)
    for row, label in zip(rows, labels, strict=False):
        groups[int(label)].append(row)
    return {
        "method_key": f"kmeans_k{k_value}",
        "embedding_method": "kmeans",
        "groups": groups,
        "noise": [],
        "noise_count": 0,
        "silhouette": _silhouette(embeddings, labels),
    }


def _group_prompt(group: dict[str, Any]) -> str:
    labels = "\n".join(f"- {label}" for label in group["sample_labels"]) or "-"
    anchors = "\n".join(f"- {query}" for query in group["sample_anchor_queries"]) or "-"
    queries = "\n".join(f"- {query}" for query in group["sample_representative_queries"]) or "-"
    return (
        f"Группа запросов:\n\n"
        f"method: {group['method_key']}\n"
        f"group_id: {group['group_id']}\n"
        f"size: {group['size']}\n"
        f"top_terms: {', '.join(group['top_terms']) or '-'}\n\n"
        f"sample labels:\n{labels}\n\n"
        f"anchor queries:\n{anchors}\n\n"
        f"representative queries:\n{queries}\n"
    )


def _interpret_group(http: Any, *, api_key: str, model_name: str, group: dict[str, Any]) -> dict[str, Any]:
    import requests

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local.ecomcore.spike",
        "X-Title": "EcomCore Query Meaning Groups Spike",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _group_prompt(group)},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = http.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"retryable_status:{response.status_code}:{response.text[:400]}")
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _sanitize_llm_group(_extract_json_object(content))
        except Exception as exc:
            last_error = exc
            if attempt >= 4:
                break
            time.sleep(min(20, 1.5 * (2 ** attempt)))
    raise RuntimeError(str(last_error) if last_error else "Unknown OpenRouter error")


def _render_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_group(*, method_key: str, embedding_method: str, group_id: int, items: list[ProfileRow]) -> dict[str, Any]:
    sample_labels, sample_anchors, sample_queries = _collect_samples(items)
    return {
        "group_id": f"{method_key}:{group_id}",
        "raw_group_id": int(group_id),
        "method_key": method_key,
        "embedding_method": embedding_method,
        "size": len(items),
        "sample_labels": sample_labels,
        "sample_anchor_queries": sample_anchors,
        "sample_representative_queries": sample_queries,
        "top_terms": _top_terms(items),
        "cluster_keys": [item.cluster_key for item in items[:30]],
    }


def _build_report(*, output_path: Path, payload: dict[str, Any]) -> None:
    interpreted_groups = payload["groups"]
    counts_by_type = Counter(group["type"] for group in interpreted_groups)
    buyer_groups = [group for group in interpreted_groups if group["type"] == "buyer_meaning"]
    functional_groups = [group for group in interpreted_groups if group["type"] == "functional"]
    format_groups = [group for group in interpreted_groups if group["type"] == "format_set"]
    decor_groups = [group for group in interpreted_groups if group["type"] == "decor/interior"]
    event_groups = [group for group in interpreted_groups if group["type"] == "event/holiday"]
    mixed_groups = [group for group in interpreted_groups if group["type"] in {"mixed", "garbage", "generic"}]

    lines = [
        "# Query Meaning Groups Report v1",
        "",
        "## Summary",
        "",
        f"- total_profiles_available: `{payload['sample_summary']['total_profiles_available']}`",
        f"- excluded_empty_profiles: `{payload['sample_summary']['excluded_empty_profiles']}`",
        f"- excluded_weak_noise_profiles: `{payload['sample_summary']['excluded_weak_noise_profiles']}`",
        f"- sampled_profiles: `{payload['sample_summary']['sampled_profiles']}`",
        f"- sample_strategy: `{payload['sample_summary']['sample_strategy']}`",
        f"- total_interpreted_groups: `{len(interpreted_groups)}`",
        "",
        "### Methods",
        "",
    ]
    for method in payload["methods"]:
        lines.append(
            f"- `{method['method_key']}`: groups=`{method['group_count']}`, noise=`{method['noise_count']}`, silhouette=`{method['silhouette']}`"
        )
    lines.extend(["", "### Distribution by type", ""])
    for group_type, count in counts_by_type.most_common():
        lines.append(f"- {group_type}: `{count}`")

    def render_group_block(title: str, items: list[dict[str, Any]], *, limit: int | None = None) -> None:
        lines.extend(["", f"## {title}", ""])
        selected = items if limit is None else items[:limit]
        if not selected:
            lines.append("- none")
            return
        for group in selected:
            examples = group["sample_anchor_queries"][:20] or group["sample_representative_queries"][:20]
            lines.extend(
                [
                    f"### {group['label']}",
                    "",
                    f"- group_id: `{group['group_id']}`",
                    f"- method: `{group['method_key']}`",
                    f"- size: `{group['size']}`",
                    f"- type: `{group['type']}`",
                    f"- confidence: `{group['confidence']}`",
                    f"- description: {group['description']}",
                    "",
                    "**Examples**",
                    "",
                ]
            )
            lines.extend(f"- {example}" for example in examples[:20])
            lines.append("")

    render_group_block("Buyer-meaning groups", sorted(buyer_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])))
    render_group_block("Functional groups", sorted(functional_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])))
    render_group_block("Format groups", sorted(format_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])))
    render_group_block("Decor/interior groups", sorted(decor_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])))
    render_group_block("Event groups", sorted(event_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])))
    render_group_block("Mixed / bad groups", sorted(mixed_groups, key=lambda group: (-group["size"], -group["confidence"], group["group_id"])), limit=20)

    buyer_labels = " ".join(f"{group['label']} {group['description']}" for group in buyer_groups).lower()
    has_aesthetic = any(pattern in buyer_labels for pattern in ("эстет", "pinterest", "стиль", "красив", "мил"))
    has_gift = any(pattern in buyer_labels for pattern in ("подар", "gift"))
    has_fun = any(pattern in buyer_labels for pattern in ("мем", "прикол", "надпис", "шут"))
    if has_aesthetic and has_gift and has_fun:
        verdict = "работает"
    elif buyer_groups:
        verdict = "частично"
    else:
        verdict = "не работает"
    lines.extend(
        [
            "",
            "## Does this look like real demand segmentation?",
            "",
            f"- verdict: `{verdict}`",
        ]
    )
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _run_spike(
    *,
    project_id: int,
    category_id: int,
    sample_limit: int,
    embedding_model: str,
    llm_model: str,
) -> dict[str, Any]:
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment")
    llm_model = os.getenv("OPENROUTER_MODEL") or llm_model
    if not llm_model:
        raise RuntimeError("OPENROUTER_MODEL is required or a default model must be available")

    from app.db import SessionLocal

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_json_path = OUTPUTS_DIR / "query_meaning_groups_v1.json"
    output_report_path = OUTPUTS_DIR / "query_meaning_groups_report_v1.md"

    session = SessionLocal()
    try:
        rows, sample_summary = _collect_profile_rows(session, project_id=project_id, category_id=category_id, sample_limit=sample_limit)
    finally:
        session.close()

    texts = [row.meaning_text for row in rows]
    embeddings = _compute_embeddings(texts, model_name=embedding_model)

    methods: list[dict[str, Any]] = []
    hdbscan_result = _build_hdbscan_groups(rows, embeddings, min_cluster_size=35)
    methods.append(hdbscan_result)
    kmeans_candidates = [_build_kmeans_groups(rows, embeddings, k_value=k_value) for k_value in (10, 15, 20, 25)]
    top_kmeans = sorted(kmeans_candidates, key=lambda item: (-(item["silhouette"] or -1.0), item["method_key"]))[:2]
    methods.extend(top_kmeans)

    serialized_groups: list[dict[str, Any]] = []
    for method in methods:
        for raw_group_id, items in sorted(method["groups"].items(), key=lambda pair: (-len(pair[1]), pair[0])):
            serialized_groups.append(
                _serialize_group(
                    method_key=method["method_key"],
                    embedding_method=method["embedding_method"],
                    group_id=int(raw_group_id),
                    items=items,
                )
            )

    existing_payload: dict[str, Any] = {}
    if output_json_path.exists():
        try:
            existing_payload = json.loads(output_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_payload = {}
    interpreted_by_key = {group["group_id"]: group for group in existing_payload.get("groups", []) if group.get("group_id")}
    errors: list[dict[str, Any]] = []
    http = requests.Session()
    processed = 0
    for group in serialized_groups:
        if group["group_id"] in interpreted_by_key:
            continue
        try:
            interpretation = _interpret_group(http, api_key=api_key, model_name=llm_model, group=group)
            interpreted_by_key[group["group_id"]] = {**group, **interpretation}
        except Exception as exc:
            errors.append({"group_id": group["group_id"], "error": str(exc)})
        processed += 1
        if processed % 5 == 0:
            partial_payload = {
                "project_id": project_id,
                "category_id": category_id,
                "embedding_model": embedding_model,
                "llm_model": llm_model,
                "sample_summary": sample_summary,
                "methods": [
                    {
                        "method_key": method["method_key"],
                        "embedding_method": method["embedding_method"],
                        "group_count": len(method["groups"]),
                        "noise_count": method["noise_count"],
                        "silhouette": round(method["silhouette"], 4) if method["silhouette"] is not None else None,
                    }
                    for method in methods
                ],
                "groups": sorted(interpreted_by_key.values(), key=lambda item: item["group_id"]),
                "errors": errors,
            }
            _render_json(output_json_path, partial_payload)
            time.sleep(0.35)

    payload = {
        "project_id": project_id,
        "category_id": category_id,
        "embedding_model": embedding_model,
        "llm_model": llm_model,
        "sample_summary": sample_summary,
        "methods": [
            {
                "method_key": method["method_key"],
                "embedding_method": method["embedding_method"],
                "group_count": len(method["groups"]),
                "noise_count": method["noise_count"],
                "silhouette": round(method["silhouette"], 4) if method["silhouette"] is not None else None,
            }
            for method in methods
        ],
        "groups": sorted(interpreted_by_key.values(), key=lambda item: item["group_id"]),
        "errors": errors,
    }
    _render_json(output_json_path, payload)
    _build_report(output_path=output_report_path, payload=payload)
    return {
        "output_json_path": str(output_json_path),
        "output_report_path": str(output_report_path),
        "groups_total": len(payload["groups"]),
        "buyer_meaning_groups": sum(1 for group in payload["groups"] if group["type"] == "buyer_meaning"),
        "errors": len(errors),
    }


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])
    sys.path.insert(0, str(SRC_ROOT))
    parser = argparse.ArgumentParser(description="Offline query meaning groups spike")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id")
    parser.add_argument("--sample-limit", default=2000, type=int, help="Sample size of non-empty profiles")
    parser.add_argument("--embedding-model", default=_DEFAULT_EMBEDDING_MODEL, help="Sentence embedding model")
    parser.add_argument("--llm-model", default=_DEFAULT_LLM_MODEL, help="Fallback OpenRouter model when env is unset")
    args = parser.parse_args()
    summary = _run_spike(
        project_id=args.project_id,
        category_id=args.category_id,
        sample_limit=max(1500, min(3000, int(args.sample_limit))),
        embedding_model=str(args.embedding_model),
        llm_model=str(args.llm_model),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
