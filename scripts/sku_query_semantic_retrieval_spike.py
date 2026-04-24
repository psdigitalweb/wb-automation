#!/usr/bin/env python3
"""Standalone E2E spike: SKU -> buyer-meaning -> query cluster retrieval."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
_SCRIPT_ENV_FLAG = "ECOMCORE_SKU_QUERY_SEMANTIC_RETRIEVAL_IN_DOCKER"
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_LLM_MODEL = "openai/gpt-4.1-mini"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_BUYER_CLASSES = {"aesthetic", "gift", "fun_meme"}
_EXCLUDED_CLASSES = {"decor_interior", "event_holiday", "garbage"}
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.IGNORECASE)
_ALLOWED_CLASSES = {
    "aesthetic",
    "gift",
    "fun_meme",
    "self_treat",
    "serving_photo",
    "decor_interior",
    "event_holiday",
    "functional",
    "format_set",
    "size",
    "audience_kids",
    "generic",
    "garbage",
}
_SYSTEM_PROMPT = """Ты определяешь СМЫСЛ ПОКУПКИ товара.

Выбери:
- MAIN (обязательный)
- SECONDARY (0-2)

Классы:
- aesthetic
- gift
- fun_meme
- self_treat
- serving_photo
- decor_interior
- event_holiday
- functional
- format_set
- size
- audience_kids
- generic
- garbage

Правила:
- не выдумывай смысл, если его нет
- если товар "про красивое/вайб" -> aesthetic
- если "в подарок" -> gift
- если "надпись/прикол" -> fun_meme

Верни JSON:
{
  "main": "...",
  "secondary": ["..."],
  "confidence": 0.0,
  "reason": "..."
}"""


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
    exec_command.extend(["worker", "python", "scripts/sku_query_semantic_retrieval_spike.py", *argv])
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running SKU semantic retrieval spike in the worker container...",
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


def _sanitize_label(payload: dict[str, Any]) -> dict[str, Any]:
    main = str(payload.get("main") or "").strip()
    if main not in _ALLOWED_CLASSES:
        raise ValueError(f"Unsupported main class: {main}")
    secondary_raw = payload.get("secondary") or []
    secondary: list[str] = []
    if isinstance(secondary_raw, list):
        for item in secondary_raw[:2]:
            label = str(item or "").strip()
            if label in _ALLOWED_CLASSES and label != main and label not in secondary:
                secondary.append(label)
    confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    reason = str(payload.get("reason") or "").strip()
    return {"main": main, "secondary": secondary, "confidence": round(confidence, 4), "reason": reason}


def _collect_reviews(session: Any, *, project_id: int, nm_id: int, limit: int = 30) -> list[str]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT raw
            FROM wb_feedback_snapshots
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY created_date DESC NULLS LAST, snapshot_at DESC NULLS LAST, id DESC
            LIMIT 80
            """
        ),
        {"project_id": project_id, "nm_id": nm_id},
    ).mappings().all()

    reviews: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        raw = raw or {}
        for field_name in ("text", "pros", "cons"):
            value = str(raw.get(field_name) or "").strip()
            if not value:
                continue
            normalized = value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            reviews.append(value)
            if len(reviews) >= limit:
                return reviews
    return reviews


def _sku_meaning_input(*, title: str, description: str, reviews: list[str]) -> str:
    parts = [title.strip(), description.strip()]
    if reviews:
        parts.append("\n".join(reviews))
    return "\n".join(part for part in parts if part)


def _pick_skus(session: Any, *, project_id: int, category_id: int, sku_limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    preferred_nm_ids = [321128388, 38802116]
    rows = session.execute(
        text(
            """
            SELECT
                id,
                nm_id,
                subject_id,
                title,
                description,
                vendor_code,
                raw,
                updated_at
            FROM products
            WHERE project_id = :project_id
              AND subject_id = :category_id
            ORDER BY
                CASE
                    WHEN nm_id = 321128388 THEN 0
                    WHEN nm_id = 38802116 THEN 1
                    ELSE 2
                END,
                updated_at DESC NULLS LAST,
                id DESC
            LIMIT 40
            """
        ),
        {"project_id": project_id, "category_id": category_id},
    ).mappings().all()

    chosen: list[dict[str, Any]] = []
    seen_nm_ids: set[int] = set()
    for row in rows:
        nm_id = int(row["nm_id"])
        if nm_id in seen_nm_ids:
            continue
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        raw = raw or {}
        title = str(row.get("title") or raw.get("title") or "").strip()
        description = str(row.get("description") or raw.get("description") or "").strip()
        chosen.append(
            {
                "nm_id": nm_id,
                "subject_id": row.get("subject_id"),
                "title": title,
                "description": description,
                "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
            }
        )
        seen_nm_ids.add(nm_id)
        if len(chosen) >= max(3, sku_limit):
            break

    missing_preferred = [nm_id for nm_id in preferred_nm_ids if nm_id not in seen_nm_ids]
    if missing_preferred:
        extra_rows = session.execute(
            text(
                """
                SELECT
                    nm_id,
                    subject_id,
                    title,
                    description,
                    vendor_code,
                    raw
                FROM products
                WHERE project_id = :project_id
                  AND nm_id = ANY(:nm_ids)
                """
            ),
            {"project_id": project_id, "nm_ids": missing_preferred},
        ).mappings().all()
        for row in extra_rows:
            nm_id = int(row["nm_id"])
            if nm_id in seen_nm_ids:
                continue
            raw = row.get("raw")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            raw = raw or {}
            chosen.insert(
                0,
                {
                    "nm_id": nm_id,
                    "subject_id": row.get("subject_id"),
                    "title": str(row.get("title") or raw.get("title") or "").strip(),
                    "description": str(row.get("description") or raw.get("description") or "").strip(),
                    "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
                },
            )
            seen_nm_ids.add(nm_id)

    chosen.sort(key=lambda sku: (0 if sku["nm_id"] == 321128388 else 1 if sku["nm_id"] == 38802116 else 2, -len(sku["description"]), sku["nm_id"]))
    return chosen[: max(3, sku_limit)]


def _classify_sku_meaning(http: Any, *, api_key: str, model_name: str, sku_meaning_input: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local.ecomcore.spike",
        "X-Title": "EcomCore SKU Query Semantic Retrieval Spike",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": sku_meaning_input},
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
            return _sanitize_label(_extract_json_object(content))
        except Exception as exc:
            last_error = exc
            if attempt >= 4:
                break
            time.sleep(min(20, 1.5 * (2 ** attempt)))
    raise RuntimeError(str(last_error) if last_error else "Unknown OpenRouter error")


def _cluster_product_type_guard(cluster: dict[str, Any]) -> bool:
    text_value = " ".join(
        [
            str(cluster.get("profile_label_candidate") or ""),
            str(cluster.get("anchor_query") or ""),
            *[str(query or "") for query in cluster.get("representative_queries") or []],
        ]
    ).lower()
    return "тарел" in text_value


def _cluster_meaning_text(cluster: dict[str, Any]) -> str:
    queries = cluster.get("representative_queries") or []
    return "\n".join(
        [
            str(cluster.get("profile_label_candidate") or "").strip(),
            f"anchor: {str(cluster.get('anchor_query') or '').strip()}",
            "queries:",
            *[f"- {str(query).strip()}" for query in queries],
        ]
    ).strip()


def _short_reason(*, sku_meaning: dict[str, Any], cluster: dict[str, Any], similarity: float) -> str:
    sku_classes = {sku_meaning["main"], *sku_meaning["secondary"]}
    cluster_classes = {cluster["main"], *(cluster.get("secondary") or [])}
    overlap = [cls for cls in ("aesthetic", "gift", "fun_meme") if cls in sku_classes and cls in cluster_classes]
    if overlap:
        return f"shared buyer-meaning {', '.join(overlap)} + similarity {similarity:.4f}"
    if cluster["main"] in _BUYER_CLASSES:
        return f"buyer cluster main={cluster['main']} + similarity {similarity:.4f}"
    return f"secondary buyer-meaning hit + similarity {similarity:.4f}"


def _dedupe_queries(top_clusters: list[dict[str, Any]], *, max_queries: int = 50) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for cluster in top_clusters:
        candidates = [cluster.get("anchor_query") or "", *(cluster.get("representative_queries") or [])]
        for query in candidates:
            query_value = str(query or "").strip()
            if not query_value:
                continue
            normalized = query_value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(query_value)
            if len(result) >= max_queries:
                return result
    return result


def _manual_assessment(queries: list[str]) -> dict[str, Any]:
    lower_queries = [query.lower() for query in queries]
    buyer_hits = [query for query in queries if any(pattern in query.lower() for pattern in ("pinterest", "эстет", "красив", "мил", "подар", "надпис", "прикол", "мем"))]
    garbage_hits = [query for query in queries if any(pattern in query.lower() for pattern in ("для дома", "для супа", "набор", "шт", "свч", "микровол"))]
    verdict = "похоже на buyer-meaning retrieval" if len(buyer_hits) > len(garbage_hits) else "сильная примесь generic/functional"
    return {
        "buyer_like_examples": buyer_hits[:10],
        "garbage_like_examples": garbage_hits[:10],
        "verdict": verdict,
    }


def _render_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_report(*, output_path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# SKU Query Semantic Retrieval Report",
        "",
        f"- project_id: `{payload['project_id']}`",
        f"- category_id: `{payload['category_id']}`",
        f"- llm_model: `{payload['llm_model']}`",
        f"- embedding_model: `{payload['embedding_model']}`",
        "",
    ]
    for sku in payload["skus"]:
        meaning = sku["sku_meaning"]
        lines.extend(
            [
                f"## SKU `{sku['nm_id']}`",
                "",
                f"- title: {sku['title']}",
                f"- main: `{meaning['main']}`",
                f"- secondary: `{meaning['secondary']}`",
                f"- reason: {meaning['reason']}",
                "",
                "### Top semantic clusters",
                "",
            ]
        )
        for cluster in sku["top_clusters"][:30]:
            lines.append(
                f"- `{cluster['similarity']:.4f}` | {cluster['profile_label_candidate'] or '-'} | anchor: {cluster['anchor_query'] or '-'} | main={cluster['main']} | {cluster['selection_reason']}"
            )
        lines.extend(["", "### Final query list", ""])
        lines.extend(f"- {query}" for query in sku["final_queries"][:50])
        lines.extend(
            [
                "",
                "### Manual assessment",
                "",
                f"- verdict: {sku['manual_assessment']['verdict']}",
                f"- buyer_like_examples: {sku['manual_assessment']['buyer_like_examples']}",
                f"- garbage_like_examples: {sku['manual_assessment']['garbage_like_examples']}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _run_spike(
    *,
    project_id: int,
    category_id: int,
    sku_limit: int,
    llm_model: str,
    embedding_model: str,
) -> dict[str, Any]:
    import numpy as np
    import requests
    from sentence_transformers import SentenceTransformer

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment")
    llm_model = os.getenv("OPENROUTER_MODEL") or llm_model

    labels_path = OUTPUTS_DIR / "query_llm_meaning_labels_v2.json"
    if not labels_path.exists():
        raise RuntimeError("outputs/query_llm_meaning_labels_v2.json is required")
    query_labels = json.loads(labels_path.read_text(encoding="utf-8"))

    from app.db import SessionLocal

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_json_path = OUTPUTS_DIR / "sku_query_semantic_retrieval.json"
    output_report_path = OUTPUTS_DIR / "sku_query_semantic_retrieval_report.md"

    session = SessionLocal()
    try:
        skus = _pick_skus(session, project_id=project_id, category_id=category_id, sku_limit=sku_limit)
        for sku in skus:
            sku["reviews"] = _collect_reviews(session, project_id=project_id, nm_id=int(sku["nm_id"]), limit=30)
            sku["sku_meaning_input"] = _sku_meaning_input(
                title=sku["title"],
                description=sku["description"],
                reviews=sku["reviews"],
            )
    finally:
        session.close()

    http = requests.Session()
    for sku in skus:
        sku["sku_meaning"] = _classify_sku_meaning(http, api_key=api_key, model_name=llm_model, sku_meaning_input=sku["sku_meaning_input"])

    candidate_clusters: list[dict[str, Any]] = []
    for cluster in query_labels:
        if not _cluster_product_type_guard(cluster):
            continue
        if cluster["main"] in _EXCLUDED_CLASSES:
            continue
        cluster_classes = {cluster["main"], *(cluster.get("secondary") or [])}
        if not (cluster["main"] in _BUYER_CLASSES or cluster_classes.intersection(_BUYER_CLASSES)):
            continue
        candidate_clusters.append({**cluster, "meaning_text": _cluster_meaning_text(cluster)})

    model = SentenceTransformer(embedding_model)
    cluster_embeddings = model.encode(
        [cluster["meaning_text"] for cluster in candidate_clusters],
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    cluster_embeddings = np.asarray(cluster_embeddings, dtype="float32")

    sku_embeddings = model.encode(
        [sku["sku_meaning_input"] for sku in skus],
        batch_size=16,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    sku_embeddings = np.asarray(sku_embeddings, dtype="float32")
    similarities = np.matmul(sku_embeddings, cluster_embeddings.T)

    for sku_index, sku in enumerate(skus):
        order = np.argsort(-similarities[sku_index])[:30]
        top_clusters: list[dict[str, Any]] = []
        for idx in order:
            cluster = candidate_clusters[int(idx)]
            similarity = float(similarities[sku_index][idx])
            top_clusters.append(
                {
                    "cluster_key": cluster["cluster_key"],
                    "profile_label_candidate": cluster.get("profile_label_candidate") or "",
                    "anchor_query": cluster.get("anchor_query") or "",
                    "representative_queries": list(cluster.get("representative_queries") or []),
                    "main": cluster["main"],
                    "secondary": list(cluster.get("secondary") or []),
                    "confidence": float(cluster["confidence"]),
                    "similarity": round(similarity, 4),
                    "selection_reason": _short_reason(sku_meaning=sku["sku_meaning"], cluster=cluster, similarity=similarity),
                }
            )
        sku["top_clusters"] = top_clusters
        sku["final_queries"] = _dedupe_queries(top_clusters, max_queries=50)
        sku["manual_assessment"] = _manual_assessment(sku["final_queries"])

    payload = {
        "project_id": project_id,
        "category_id": category_id,
        "llm_model": llm_model,
        "embedding_model": embedding_model,
        "query_labels_source": str(labels_path),
        "candidate_clusters_count": len(candidate_clusters),
        "skus": [
            {
                "nm_id": sku["nm_id"],
                "title": sku["title"],
                "description": sku["description"],
                "vendor_code": sku["vendor_code"],
                "reviews": sku["reviews"],
                "sku_meaning_input": sku["sku_meaning_input"],
                "sku_meaning": sku["sku_meaning"],
                "top_clusters": sku["top_clusters"],
                "final_queries": sku["final_queries"],
                "manual_assessment": sku["manual_assessment"],
            }
            for sku in skus
        ],
    }
    _render_json(output_json_path, payload)
    _build_report(output_path=output_report_path, payload=payload)
    return {
        "output_json_path": str(output_json_path),
        "output_report_path": str(output_report_path),
        "candidate_clusters_count": len(candidate_clusters),
        "sku_count": len(skus),
    }


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])
    sys.path.insert(0, str(SRC_ROOT))
    parser = argparse.ArgumentParser(description="Standalone SKU -> buyer meaning -> query retrieval spike")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id")
    parser.add_argument("--sku-limit", type=int, default=5, help="How many SKUs to evaluate")
    parser.add_argument("--llm-model", default=_DEFAULT_LLM_MODEL, help="LLM for SKU meaning")
    parser.add_argument("--embedding-model", default=_DEFAULT_EMBEDDING_MODEL, help="Sentence embedding model")
    args = parser.parse_args()
    summary = _run_spike(
        project_id=args.project_id,
        category_id=args.category_id,
        sku_limit=max(3, min(5, int(args.sku_limit))),
        llm_model=str(args.llm_model),
        embedding_model=str(args.embedding_model),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
