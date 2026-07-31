#!/usr/bin/env python3
"""Offline query-side meaning decomposition spike for one WB category."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
_SCRIPT_ENV_FLAG = "ECOMCORE_QUERY_MEANING_DECOMPOSITION_IN_DOCKER"
_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_K_VALUES = (8, 10, 12, 15, 20)
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "and", "for", "or", "the", "v1",
    "в", "во", "все", "для", "до", "из", "и", "или", "к", "ко", "на", "не",
    "но", "о", "об", "от", "по", "под", "при", "с", "со", "у",
    "label", "product", "type", "use", "case", "attribute", "anchor", "query",
    "queries", "representative", "profile", "profiles",
}
_INTERPRETATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "aesthetic": (
        "эстет", "pinterest", "пинтерест", "стиль", "стильн", "красив", "мила",
        "cute", "декор", "декоратив", "рисунк", "узор", "надпись", "котик", "цветок", "серд",
    ),
    "gift": (
        "подар", "подарок", "подароч", "любимой", "любимому", "подруге", "другу",
        "маме", "папе", "ребенка", "ребёнка", "др", "день рождения", "8 марта",
    ),
    "meme_fun_text": ("мем", "прикол", "смешн", "fun", "жр", "hello", "time for food", "надпись", "текст"),
    "functional": (
        "суп", "супов", "микроволнов", "свч", "для дома", "для кухни", "для детей",
        "для ребенка", "для ребёнка", "для стола", "сервиров", "кормлен", "паст",
    ),
    "format_set": ("набор", "комплект", "сервиз", "глубок", "десерт", "обеден", "секцион", "формат"),
    "size": ("см", "мм", "диаметр", "size", "20", "24", "25", "26", "30"),
    "generic": ("тарелка", "тарелки", "посуда", "plate"),
    "garbage": ("салфет", "подстав", "подлож", "скатерт", "дюбел", "под тарелки", "коврик"),
}


@dataclass(frozen=True)
class ProfileRow:
    cluster_key: str
    profile_label_candidate: str
    anchor_query: str
    profile_strength: str
    product_type_markers: list[str]
    use_case_markers: list[str]
    attribute_markers: list[str]
    representative_queries: list[str]
    meaning_text: str


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
    exec_command = [
        "docker", "compose", "-f", str(compose_file), "exec", "-T",
        "-e", f"{_SCRIPT_ENV_FLAG}=1", "worker", "python", "scripts/query_meaning_decomposition_spike.py", *argv,
    ]
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running query meaning decomposition spike in the worker container...",
        file=sys.stderr,
    )
    ensure_result = subprocess.run(ensure_stack_command, cwd=PROJECT_ROOT)
    if ensure_result.returncode != 0:
        return ensure_result.returncode
    return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode


def _render_marker_list(markers: list[Any]) -> list[str]:
    values: list[str] = []
    for marker in markers:
        normalized = str(getattr(marker, "normalized_value", "") or "").strip()
        raw = str(getattr(marker, "value", "") or "").strip()
        family = getattr(marker, "family", None)
        label = normalized or raw
        if label:
            values.append(f"{family}:{label}" if family else label)
    return values


def _tokenize(text_value: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(str(text_value or "")) if len(token) >= 2]


def _top_terms(texts: list[str], *, limit: int = 10) -> list[str]:
    unigram_counter: Counter[str] = Counter()
    bigram_counter: Counter[str] = Counter()
    for text_value in texts:
        tokens = [token for token in _tokenize(text_value) if token not in _STOPWORDS]
        unigram_counter.update(tokens)
        bigram_counter.update(
            f"{left} {right}"
            for left, right in zip(tokens, tokens[1:])
            if left not in _STOPWORDS and right not in _STOPWORDS
        )
    ranked: list[tuple[str, int]] = []
    for phrase, count in bigram_counter.most_common(limit * 3):
        if count >= 2:
            ranked.append((phrase, count))
    for token, count in unigram_counter.most_common(limit * 3):
        if count >= 3:
            ranked.append((token, count))
    seen: set[str] = set()
    result: list[str] = []
    for term, count in ranked:
        if term in seen:
            continue
        seen.add(term)
        result.append(f"{term} ({count})")
        if len(result) >= limit:
            break
    return result


def _build_meaning_text(profile: Any, representative_queries: list[str]) -> str:
    sections = [
        f"label: {profile.profile_label_candidate or ''}",
        f"product_type: {', '.join(_render_marker_list(profile.product_type_markers))}",
        f"use_case: {', '.join(_render_marker_list(profile.use_case_markers))}",
        f"attributes: {', '.join(_render_marker_list(profile.attribute_markers))}",
        f"anchor_query: {profile.source_anchor_query or ''}",
        f"representative_queries: {', '.join(representative_queries)}",
    ]
    return " | ".join(section.strip() for section in sections if section.strip())


def _is_empty_profile(profile: Any) -> bool:
    marker_count = len(profile.product_type_markers) + len(profile.use_case_markers) + len(profile.attribute_markers)
    return profile.profile_strength == "empty" or marker_count <= 0


def _is_weak_noise_profile(profile: Any, representative_queries: list[str]) -> bool:
    marker_count = len(profile.product_type_markers) + len(profile.use_case_markers) + len(profile.attribute_markers)
    label = str(profile.profile_label_candidate or "").strip()
    anchor = str(profile.source_anchor_query or "").strip()
    if profile.profile_strength != "weak" or marker_count > 0:
        return False
    if len(label) >= 4 or len(anchor) >= 4:
        return False
    return len(representative_queries) <= 1


def _group_examples(items: list[ProfileRow], *, label_limit: int = 12, anchor_limit: int = 10, query_limit: int = 12) -> dict[str, list[str]]:
    labels: list[str] = []
    anchors: list[str] = []
    queries: list[str] = []
    for item in items:
        if item.profile_label_candidate and item.profile_label_candidate not in labels and len(labels) < label_limit:
            labels.append(item.profile_label_candidate)
        if item.anchor_query and item.anchor_query not in anchors and len(anchors) < anchor_limit:
            anchors.append(item.anchor_query)
        for query in item.representative_queries:
            if query not in queries and len(queries) < query_limit:
                queries.append(query)
        if len(labels) >= label_limit and len(anchors) >= anchor_limit and len(queries) >= query_limit:
            break
    return {"labels": labels, "anchors": anchors, "queries": queries}


def _interpret_group(items: list[ProfileRow]) -> tuple[str, dict[str, int]]:
    corpus = " \n ".join(
        " ".join(
            [
                item.profile_label_candidate,
                item.anchor_query,
                " ".join(item.representative_queries),
                " ".join(item.use_case_markers),
                " ".join(item.attribute_markers),
            ]
        )
        for item in items
    ).lower()
    scores: dict[str, int] = {}
    for category, patterns in _INTERPRETATION_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if pattern in corpus:
                score += corpus.count(pattern)
        scores[category] = score
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    best_label, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if best_score <= 0:
        return "unknown", scores
    if best_label == "generic" and best_score >= 3 and second_score <= max(1, best_score // 3):
        return "generic", scores
    if best_label == "garbage" and best_score >= 2:
        return "garbage", scores
    if second_score >= max(2, int(best_score * 0.75)) and best_label not in {"garbage", "generic"}:
        return "mixed", scores
    return best_label, scores


def _silhouette_for_labels(matrix: Any, labels: Any, *, metric: str) -> float | None:
    from sklearn.metrics import silhouette_score

    unique_labels = {int(value) for value in labels}
    if len(unique_labels) <= 1 or len(unique_labels) >= len(labels):
        return None
    return float(silhouette_score(matrix, labels, metric=metric, sample_size=min(2000, len(labels)), random_state=42))


def _build_method_summary(groups: dict[int, list[ProfileRow]], noise_count: int = 0) -> dict[str, Any]:
    sizes = sorted((len(items) for items in groups.values()), reverse=True)
    return {"group_count": len(groups), "noise_count": noise_count, "largest_groups": sizes[:8]}


def _format_group(group_id: int, items: list[ProfileRow]) -> dict[str, Any]:
    examples = _group_examples(items)
    interpretation, scores = _interpret_group(items)
    return {
        "group_id": group_id,
        "size": len(items),
        "labels": examples["labels"],
        "anchors": examples["anchors"],
        "queries": examples["queries"],
        "top_terms": _top_terms([item.meaning_text for item in items], limit=10),
        "interpretation": interpretation,
        "interpretation_scores": scores,
    }


def _pick_special_focus(method_groups: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any] | None]:
    wanted = {
        "aesthetic": "aesthetic",
        "gift": "gift",
        "meme_fun_text": "meme_fun_text",
        "functional": "functional",
        "format_set": "format_set",
        "garbage": "garbage",
    }
    selected: dict[str, dict[str, Any] | None] = {}
    for focus_name, interpretation_name in wanted.items():
        candidates: list[dict[str, Any]] = []
        for groups in method_groups.values():
            for item in groups:
                if item["interpretation"] == interpretation_name:
                    candidates.append(item)
        candidates.sort(
            key=lambda item: (
                -item["interpretation_scores"].get(interpretation_name, 0),
                -item["size"],
                item["group_id"],
            )
        )
        selected[focus_name] = candidates[0] if candidates else None
    return selected


def _collect_failure_cases(method_name: str, groups: list[dict[str, Any]], *, limit: int = 15) -> list[str]:
    candidates = [
        group for group in groups
        if group["interpretation"] in {"mixed", "generic", "garbage", "unknown"} or group["size"] >= 250
    ]
    candidates.sort(
        key=lambda item: (
            item["interpretation"] not in {"mixed", "generic", "garbage"},
            -item["size"],
            item["group_id"],
        )
    )
    lines: list[str] = []
    for group in candidates[:limit]:
        sample_labels = ", ".join(group["labels"][:4]) or "-"
        lines.append(
            f"- `{method_name}` group `{group['group_id']}` | `{group['interpretation']}` | size `{group['size']}` | labels: {sample_labels}"
        )
    return lines


def _write_report(
    *,
    output_path: Path,
    project_id: int,
    category_id: int,
    model_name: str,
    total_profiles: int,
    excluded_empty: list[ProfileRow],
    excluded_weak_noise: list[ProfileRow],
    method_summaries: dict[str, dict[str, Any]],
    lexical_groups: list[dict[str, Any]],
    embedding_hdbscan_groups: list[dict[str, Any]],
    embedding_hdbscan_noise: list[ProfileRow],
    embedding_kmeans_groups: list[dict[str, Any]],
    lexical_scores: list[dict[str, Any]],
    embedding_kmeans_scores: list[dict[str, Any]],
    best_focus: dict[str, dict[str, Any] | None],
    failure_cases: list[str],
) -> None:
    lines: list[str] = [
        "# Query Meaning Decomposition Report",
        "",
        "## 3.1 Summary",
        "",
        f"- project_id: `{project_id}`",
        f"- category_id: `{category_id}`",
        f"- embedding_model: `{model_name}`",
        f"- total_cluster_profiles: `{total_profiles}`",
        f"- excluded_empty_profiles: `{len(excluded_empty)}`",
        f"- excluded_weak_noise_profiles: `{len(excluded_weak_noise)}`",
        "- methods_tested: `baseline lexical TF-IDF + KMeans`, `embedding + HDBSCAN`, `embedding + KMeans`",
        "",
        "### Method Summary",
        "",
        f"- lexical baseline: `{method_summaries['lexical']['group_count']}` groups, best k=`{method_summaries['lexical']['best_k']}`, silhouette=`{method_summaries['lexical']['best_silhouette']:.4f}`",
        f"- embedding + HDBSCAN: `{method_summaries['embedding_hdbscan']['group_count']}` groups, noise=`{method_summaries['embedding_hdbscan']['noise_count']}`",
        f"- embedding + KMeans: `{method_summaries['embedding_kmeans']['group_count']}` groups, best k=`{method_summaries['embedding_kmeans']['best_k']}`, silhouette=`{method_summaries['embedding_kmeans']['best_silhouette']:.4f}`",
        "",
        "### Lexical K Sweep",
        "",
        "| k | silhouette | inertia |",
        "| --- | ---: | ---: |",
    ]
    for row in lexical_scores:
        lines.append(f"| {row['k']} | {row['silhouette']:.4f} | {row['inertia']:.2f} |")
    lines.extend(["", "### Embedding K Sweep", "", "| k | silhouette | inertia |", "| --- | ---: | ---: |"])
    for row in embedding_kmeans_scores:
        lines.append(f"| {row['k']} | {row['silhouette']:.4f} | {row['inertia']:.2f} |")

    def append_method_section(title: str, groups: list[dict[str, Any]], *, include_noise: bool = False) -> None:
        lines.extend(["", f"## 3.2 Meaning Segments by Method — {title}", ""])
        for group in groups:
            lines.extend(
                [
                    f"### Group {group['group_id']}",
                    "",
                    f"- size: `{group['size']}`",
                    f"- interpretation: `{group['interpretation']}`",
                    f"- top_terms: {', '.join(group['top_terms']) if group['top_terms'] else '-'}",
                    "",
                    "**Top Profile Labels**",
                    "",
                ]
            )
            lines.extend(f"- {label}" for label in group["labels"] or ["-"])
            lines.extend(["", "**Top Anchor Queries**", ""])
            lines.extend(f"- {anchor}" for anchor in group["anchors"] or ["-"])
            lines.extend(["", "**Representative Examples**", ""])
            lines.extend(f"- {query}" for query in group["queries"] or ["-"])
            lines.append("")
        if include_noise:
            lines.extend(["### Noise / Excluded Buckets", "", f"- HDBSCAN noise profiles: `{len(embedding_hdbscan_noise)}`"])
            for item in embedding_hdbscan_noise[:20]:
                lines.append(f"- `{item.cluster_key}` | {item.profile_label_candidate or '-'} | anchor: {item.anchor_query or '-'}")

    append_method_section("Lexical TF-IDF + KMeans", lexical_groups)
    append_method_section("Embedding + HDBSCAN", embedding_hdbscan_groups, include_noise=True)
    append_method_section("Embedding + KMeans", embedding_kmeans_groups)

    lines.extend(["", "## 3.3 Special Focus", ""])
    focus_order = [
        ("aesthetic", "best aesthetic / pinterest-like segment"),
        ("gift", "best gift segment"),
        ("meme_fun_text", "best meme / fun / text-on-product segment"),
        ("functional", "strongest functional segment"),
        ("format_set", "strongest format / set segment"),
        ("garbage", "strongest garbage / cross-category segment"),
    ]
    for focus_key, title in focus_order:
        item = best_focus.get(focus_key)
        lines.append(f"### {title}")
        lines.append("")
        if item is None:
            lines.append("- not found")
            lines.append("")
            continue
        lines.append(f"- method: `{item['method']}`")
        lines.append(f"- group_id: `{item['group_id']}`")
        lines.append(f"- size: `{item['size']}`")
        lines.append(f"- interpretation: `{item['interpretation']}`")
        lines.append(f"- labels: {', '.join(item['labels'][:8]) if item['labels'] else '-'}")
        lines.append(f"- anchors: {', '.join(item['anchors'][:8]) if item['anchors'] else '-'}")
        lines.append("")

    lines.extend(["## 3.4 Failure Cases", ""])
    lines.extend(failure_cases or ["- none"])
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _run_spike(*, project_id: int, category_id: int, model_name: str) -> dict[str, Any]:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import HDBSCAN, KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    from app.db import SessionLocal
    from app.services.seo.query_pipeline import get_query_clusters, run_query_profile_extraction

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUTS_DIR / "query_meaning_decomposition_report.md"
    assignments_path = OUTPUTS_DIR / "query_meaning_decomposition_assignments.json"

    session = SessionLocal()
    try:
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

        active_rows: list[ProfileRow] = []
        excluded_empty: list[ProfileRow] = []
        excluded_weak_noise: list[ProfileRow] = []
        total_profiles = len(profile_result.profiles)

        for profile in profile_result.profiles:
            cluster = cluster_by_key.get(profile.cluster_key)
            representative_queries: list[str] = []
            if cluster is not None:
                for member in cluster.members[:8]:
                    query = str(member.display_query or member.normalized_query_text or "").strip()
                    if query and query not in representative_queries:
                        representative_queries.append(query)
            row = ProfileRow(
                cluster_key=profile.cluster_key,
                profile_label_candidate=str(profile.profile_label_candidate or "").strip(),
                anchor_query=str(profile.source_anchor_query or "").strip(),
                profile_strength=str(profile.profile_strength),
                product_type_markers=_render_marker_list(profile.product_type_markers),
                use_case_markers=_render_marker_list(profile.use_case_markers),
                attribute_markers=_render_marker_list(profile.attribute_markers),
                representative_queries=representative_queries,
                meaning_text=_build_meaning_text(profile, representative_queries),
            )
            if _is_empty_profile(profile):
                excluded_empty.append(row)
                continue
            if _is_weak_noise_profile(profile, representative_queries):
                excluded_weak_noise.append(row)
                continue
            active_rows.append(row)

        if len(active_rows) < 50:
            raise RuntimeError("Not enough active profiles for decomposition")

        lexical_vectorizer = TfidfVectorizer(
            analyzer="word",
            lowercase=True,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
        )
        lexical_matrix = lexical_vectorizer.fit_transform([row.meaning_text for row in active_rows])
        lexical_scores: list[dict[str, Any]] = []
        lexical_best_k = _K_VALUES[0]
        lexical_best_labels = None
        lexical_best_silhouette = float("-inf")
        for k in _K_VALUES:
            estimator = KMeans(n_clusters=k, random_state=42, n_init="auto")
            labels = estimator.fit_predict(lexical_matrix)
            silhouette = _silhouette_for_labels(lexical_matrix, labels, metric="cosine")
            lexical_scores.append({"k": k, "silhouette": 0.0 if silhouette is None else float(silhouette), "inertia": float(estimator.inertia_)})
            if silhouette is not None and float(silhouette) > lexical_best_silhouette:
                lexical_best_k = k
                lexical_best_silhouette = float(silhouette)
                lexical_best_labels = labels
        if lexical_best_labels is None:
            raise RuntimeError("Lexical baseline failed")

        lexical_groups_raw: dict[int, list[ProfileRow]] = defaultdict(list)
        for row, label in zip(active_rows, lexical_best_labels):
            lexical_groups_raw[int(label)].append(row)
        lexical_groups = [
            _format_group(group_id, items)
            for group_id, items in sorted(lexical_groups_raw.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ]

        model = SentenceTransformer(model_name, device="cpu")
        embeddings = model.encode(
            [row.meaning_text for row in active_rows],
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        embeddings = np.asarray(embeddings, dtype="float32")

        hdbscan = HDBSCAN(
            min_cluster_size=max(20, len(active_rows) // 300),
            min_samples=5,
            metric="euclidean",
            allow_single_cluster=False,
        )
        hdbscan_labels = hdbscan.fit_predict(embeddings)
        hdbscan_groups_raw: dict[int, list[ProfileRow]] = defaultdict(list)
        hdbscan_noise: list[ProfileRow] = []
        for row, label in zip(active_rows, hdbscan_labels):
            if int(label) == -1:
                hdbscan_noise.append(row)
                continue
            hdbscan_groups_raw[int(label)].append(row)
        embedding_hdbscan_groups = [
            _format_group(group_id, items)
            for group_id, items in sorted(hdbscan_groups_raw.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ]

        embedding_kmeans_scores: list[dict[str, Any]] = []
        embedding_best_k = _K_VALUES[0]
        embedding_best_labels = None
        embedding_best_silhouette = float("-inf")
        for k in _K_VALUES:
            estimator = KMeans(n_clusters=k, random_state=42, n_init="auto")
            labels = estimator.fit_predict(embeddings)
            silhouette = _silhouette_for_labels(embeddings, labels, metric="cosine")
            embedding_kmeans_scores.append({"k": k, "silhouette": 0.0 if silhouette is None else float(silhouette), "inertia": float(estimator.inertia_)})
            if silhouette is not None and float(silhouette) > embedding_best_silhouette:
                embedding_best_k = k
                embedding_best_silhouette = float(silhouette)
                embedding_best_labels = labels
        if embedding_best_labels is None:
            raise RuntimeError("Embedding KMeans failed")

        embedding_kmeans_groups_raw: dict[int, list[ProfileRow]] = defaultdict(list)
        for row, label in zip(active_rows, embedding_best_labels):
            embedding_kmeans_groups_raw[int(label)].append(row)
        embedding_kmeans_groups = [
            _format_group(group_id, items)
            for group_id, items in sorted(embedding_kmeans_groups_raw.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ]

        method_groups = {
            "lexical": [{**item, "method": "lexical"} for item in lexical_groups],
            "embedding_hdbscan": [{**item, "method": "embedding_hdbscan"} for item in embedding_hdbscan_groups],
            "embedding_kmeans": [{**item, "method": "embedding_kmeans"} for item in embedding_kmeans_groups],
        }
        best_focus = _pick_special_focus(method_groups)
        failure_cases = []
        failure_cases.extend(_collect_failure_cases("lexical", lexical_groups, limit=5))
        failure_cases.extend(_collect_failure_cases("embedding_hdbscan", embedding_hdbscan_groups, limit=5))
        failure_cases.extend(_collect_failure_cases("embedding_kmeans", embedding_kmeans_groups, limit=5))

        method_summaries = {
            "lexical": {**_build_method_summary(lexical_groups_raw), "best_k": lexical_best_k, "best_silhouette": lexical_best_silhouette},
            "embedding_hdbscan": {**_build_method_summary(hdbscan_groups_raw, noise_count=len(hdbscan_noise))},
            "embedding_kmeans": {**_build_method_summary(embedding_kmeans_groups_raw), "best_k": embedding_best_k, "best_silhouette": embedding_best_silhouette},
        }
        _write_report(
            output_path=report_path,
            project_id=project_id,
            category_id=category_id,
            model_name=model_name,
            total_profiles=total_profiles,
            excluded_empty=excluded_empty,
            excluded_weak_noise=excluded_weak_noise,
            method_summaries=method_summaries,
            lexical_groups=lexical_groups,
            embedding_hdbscan_groups=embedding_hdbscan_groups,
            embedding_hdbscan_noise=hdbscan_noise,
            embedding_kmeans_groups=embedding_kmeans_groups,
            lexical_scores=lexical_scores,
            embedding_kmeans_scores=embedding_kmeans_scores,
            best_focus=best_focus,
            failure_cases=failure_cases[:20],
        )

        assignments_payload = {
            "project_id": project_id,
            "category_id": category_id,
            "active_profile_count": len(active_rows),
            "excluded_empty_count": len(excluded_empty),
            "excluded_weak_noise_count": len(excluded_weak_noise),
            "lexical_best_k": lexical_best_k,
            "embedding_kmeans_best_k": embedding_best_k,
            "lexical_groups": lexical_groups,
            "embedding_hdbscan_groups": embedding_hdbscan_groups,
            "embedding_hdbscan_noise": [
                {"cluster_key": item.cluster_key, "profile_label_candidate": item.profile_label_candidate, "anchor_query": item.anchor_query}
                for item in hdbscan_noise
            ],
            "embedding_kmeans_groups": embedding_kmeans_groups,
        }
        assignments_path.write_text(json.dumps(assignments_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "project_id": project_id,
            "category_id": category_id,
            "model_name": model_name,
            "total_profiles": total_profiles,
            "active_profiles": len(active_rows),
            "excluded_empty": len(excluded_empty),
            "excluded_weak_noise": len(excluded_weak_noise),
            "lexical_best_k": lexical_best_k,
            "lexical_best_silhouette": lexical_best_silhouette,
            "embedding_hdbscan_groups": len(hdbscan_groups_raw),
            "embedding_hdbscan_noise": len(hdbscan_noise),
            "embedding_kmeans_best_k": embedding_best_k,
            "embedding_kmeans_best_silhouette": embedding_best_silhouette,
            "report_path": str(report_path),
            "assignments_path": str(assignments_path),
            "best_focus": best_focus,
            "failure_cases": failure_cases[:10],
        }
    finally:
        session.close()


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])
    sys.path.insert(0, str(SRC_ROOT))
    parser = argparse.ArgumentParser(description="Offline query-side meaning decomposition spike")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="Sentence embedding model name")
    args = parser.parse_args()
    summary = _run_spike(project_id=args.project_id, category_id=args.category_id, model_name=str(args.model))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
