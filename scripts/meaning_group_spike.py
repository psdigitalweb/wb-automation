#!/usr/bin/env python3
"""Offline research spike for semantic meaning groups over query cluster profiles."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
_SCRIPT_ENV_FLAG = "ECOMCORE_MEANING_GROUP_SPIKE_IN_DOCKER"
_DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "a",
    "and",
    "for",
    "or",
    "the",
    "в",
    "во",
    "для",
    "до",
    "из",
    "и",
    "или",
    "к",
    "ко",
    "на",
    "не",
    "но",
    "о",
    "об",
    "от",
    "по",
    "под",
    "при",
    "с",
    "со",
    "у",
    "label",
    "product",
    "type",
    "use",
    "case",
    "attribute",
    "anchor",
    "query",
}


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
    ensure_stack_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "-d",
        "postgres",
        "worker",
    ]
    exec_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-e",
        f"{_SCRIPT_ENV_FLAG}=1",
        "worker",
        "python",
        "scripts/meaning_group_spike.py",
        *argv,
    ]
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running meaning-group spike in the worker container...",
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
        if not label:
            continue
        values.append(f"{family}:{label}" if family else label)
    return values


def _meaning_text(profile: Any) -> str:
    sections = [
        f"label: {profile.profile_label_candidate or ''}",
        f"product_type: {', '.join(_render_marker_list(profile.product_type_markers))}",
        f"use_case: {', '.join(_render_marker_list(profile.use_case_markers))}",
        f"attributes: {', '.join(_render_marker_list(profile.attribute_markers))}",
        f"anchor: {profile.source_anchor_query or ''}",
    ]
    return " | ".join(section.strip() for section in sections if section.strip())


def _tokenize(text_value: str) -> list[str]:
    tokens = [token.lower() for token in _TOKEN_RE.findall(str(text_value or ""))]
    return [token for token in tokens if len(token) >= 2]


def _top_terms(texts: list[str], *, limit: int = 12) -> list[str]:
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
    for phrase, count in bigram_counter.most_common(limit * 2):
        if count >= 2:
            ranked.append((phrase, count))
    for token, count in unigram_counter.most_common(limit * 2):
        if count >= 2:
            ranked.append((token, count))

    unique_terms: list[str] = []
    seen: set[str] = set()
    for term, count in ranked:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(f"{term} ({count})")
        if len(unique_terms) >= limit:
            break
    return unique_terms


def _cosine_similarity_matrix(a: Any, b: Any) -> Any:
    import numpy as np

    return np.matmul(a, b.T)


def _format_similarity(value: float) -> str:
    if math.isnan(value):
        return "nan"
    return f"{value:.4f}"


def _collect_reviews(session: Any, *, project_id: int, nm_id: int, limit: int = 5) -> list[str]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT raw
            FROM wb_feedback_snapshots
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY created_date DESC NULLS LAST, snapshot_at DESC NULLS LAST, id DESC
            LIMIT 30
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


def _sku_meaning_text(*, title: str, description: str, reviews: list[str]) -> str:
    parts = [f"title: {title or ''}", f"description: {description or ''}"]
    if reviews:
        parts.append("reviews: " + " | ".join(reviews))
    return " | ".join(part.strip() for part in parts if part.strip())


def _pick_probe_skus(session: Any, *, project_id: int, category_id: int, sku_limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    preferred_nm_ids = [38802116, 321128388]
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
                    WHEN nm_id = 38802116 THEN 0
                    WHEN nm_id = 321128388 THEN 1
                    ELSE 2
                END,
                updated_at DESC NULLS LAST,
                id DESC
            LIMIT 30
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
        chosen.append(
            {
                "nm_id": nm_id,
                "subject_id": row.get("subject_id"),
                "title": str(row.get("title") or raw.get("title") or "").strip(),
                "description": str(row.get("description") or raw.get("description") or "").strip(),
                "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
            }
        )
        seen_nm_ids.add(nm_id)
        if len(chosen) >= max(5, sku_limit):
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
                ORDER BY updated_at DESC NULLS LAST, id DESC
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
            chosen.append(
                {
                    "nm_id": nm_id,
                    "subject_id": row.get("subject_id"),
                    "title": str(row.get("title") or raw.get("title") or "").strip(),
                    "description": str(row.get("description") or raw.get("description") or "").strip(),
                    "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
                }
            )
            seen_nm_ids.add(nm_id)

    # Keep deterministic order: preferred first when present, then remaining as selected.
    preferred_rank = {38802116: 0, 321128388: 1}
    chosen.sort(key=lambda item: (preferred_rank.get(int(item["nm_id"]), 99), item["nm_id"]))
    return chosen[:sku_limit]


def _group_examples(group_items: list[dict[str, Any]], *, label_limit: int = 15, anchor_limit: int = 10) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    anchors: list[str] = []
    for item in group_items:
        label = item["profile_label_candidate"]
        anchor = item["anchor_query"]
        if label and label not in labels and len(labels) < label_limit:
            labels.append(label)
        if anchor and anchor not in anchors and len(anchors) < anchor_limit:
            anchors.append(anchor)
        if len(labels) >= label_limit and len(anchors) >= anchor_limit:
            break
    return labels, anchors


def _write_query_groups_report(
    *,
    output_path: Path,
    project_id: int,
    category_id: int,
    model_name: str,
    profile_count: int,
    hdbscan_groups: dict[int, list[dict[str, Any]]],
    hdbscan_noise: list[dict[str, Any]],
    kmeans_groups: dict[int, list[dict[str, Any]]],
    kmeans_scores: list[dict[str, Any]],
    kmeans_best_k: int,
) -> None:
    lines: list[str] = [
        "# Query Meaning Groups",
        "",
        f"- project_id: `{project_id}`",
        f"- category_id: `{category_id}`",
        f"- embedding_model: `{model_name}`",
        f"- profile_count: `{profile_count}`",
        f"- hdbscan_groups: `{len(hdbscan_groups)}`",
        f"- hdbscan_noise_profiles: `{len(hdbscan_noise)}`",
        f"- best_kmeans_k: `{kmeans_best_k}`",
        "",
        "## KMeans Sweep",
        "",
        "| k | silhouette | inertia |",
        "| --- | ---: | ---: |",
    ]
    for row in kmeans_scores:
        lines.append(f"| {row['k']} | {row['silhouette']:.4f} | {row['inertia']:.2f} |")

    lines.extend(["", "## HDBSCAN Groups", ""])
    for group_id, items in sorted(hdbscan_groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        labels, anchors = _group_examples(items)
        top_terms = _top_terms([item["meaning_text"] for item in items], limit=12)
        lines.extend(
            [
                f"### HDBSCAN Group {group_id}",
                "",
                f"- size: `{len(items)}`",
                f"- top_terms: {', '.join(top_terms) if top_terms else '-'}",
                "",
                "**Profile Labels**",
                "",
            ]
        )
        lines.extend(f"- {label}" for label in labels or ["-"])
        lines.extend(["", "**Anchor Queries**", ""])
        lines.extend(f"- {anchor}" for anchor in anchors or ["-"])
        lines.append("")

    lines.extend(["## HDBSCAN Noise", ""])
    if hdbscan_noise:
        noise_examples = hdbscan_noise[:30]
        for item in noise_examples:
            lines.append(f"- `{item['cluster_key']}` | {item['profile_label_candidate']} | anchor: {item['anchor_query'] or '-'}")
    else:
        lines.append("- none")

    lines.extend(["", f"## KMeans Groups (k={kmeans_best_k})", ""])
    for group_id, items in sorted(kmeans_groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        labels, anchors = _group_examples(items)
        top_terms = _top_terms([item["meaning_text"] for item in items], limit=12)
        lines.extend(
            [
                f"### KMeans Group {group_id}",
                "",
                f"- size: `{len(items)}`",
                f"- top_terms: {', '.join(top_terms) if top_terms else '-'}",
                "",
                "**Profile Labels**",
                "",
            ]
        )
        lines.extend(f"- {label}" for label in labels or ["-"])
        lines.extend(["", "**Anchor Queries**", ""])
        lines.extend(f"- {anchor}" for anchor in anchors or ["-"])
        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_sku_probe_report(
    *,
    output_path: Path,
    project_id: int,
    category_id: int,
    model_name: str,
    sku_probes: list[dict[str, Any]],
) -> None:
    lines: list[str] = [
        "# SKU Meaning Probe",
        "",
        f"- project_id: `{project_id}`",
        f"- category_id: `{category_id}`",
        f"- embedding_model: `{model_name}`",
        "",
    ]
    for sku in sku_probes:
        lines.extend(
            [
                f"## SKU {sku['nm_id']} — {sku['title']}",
                "",
                f"- vendor_code: `{sku['vendor_code'] or '-'}`",
                f"- reviews_used: `{len(sku['reviews'])}`",
                "",
                "### Nearest HDBSCAN Groups",
                "",
            ]
        )
        for item in sku["nearest_hdbscan_groups"]:
            lines.extend(
                [
                    f"- group `{item['group_id']}` | similarity `{item['similarity']}` | size `{item['size']}`",
                    f"  examples: {', '.join(item['sample_labels']) if item['sample_labels'] else '-'}",
                ]
            )
        lines.extend(["", "### Nearest KMeans Groups", ""])
        for item in sku["nearest_kmeans_groups"]:
            lines.extend(
                [
                    f"- group `{item['group_id']}` | similarity `{item['similarity']}` | size `{item['size']}`",
                    f"  examples: {', '.join(item['sample_labels']) if item['sample_labels'] else '-'}",
                ]
            )
        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _run_spike(
    *,
    project_id: int,
    category_id: int,
    model_name: str,
    sku_limit: int,
    group_probe_top_n: int,
) -> dict[str, Any]:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import HDBSCAN, KMeans
    from sklearn.metrics import silhouette_score
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.services.seo.query_pipeline import get_query_clusters, run_query_profile_extraction

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    query_groups_path = OUTPUTS_DIR / "query_meaning_groups.md"
    sku_probe_path = OUTPUTS_DIR / "sku_meaning_probe.md"

    session = SessionLocal()
    try:
        product_exists = session.execute(
            text(
                """
                SELECT 1
                FROM products
                WHERE project_id = :project_id
                  AND subject_id = :category_id
                LIMIT 1
                """
            ),
            {"project_id": project_id, "category_id": category_id},
        ).first()
        if product_exists is None:
            raise RuntimeError(f"No products found for project_id={project_id}, category_id={category_id}")

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

        profile_rows: list[dict[str, Any]] = []
        for profile in profile_result.profiles:
            cluster = cluster_by_key.get(profile.cluster_key)
            profile_rows.append(
                {
                    "cluster_key": profile.cluster_key,
                    "profile_label_candidate": profile.profile_label_candidate,
                    "product_type_markers": _render_marker_list(profile.product_type_markers),
                    "use_case_markers": _render_marker_list(profile.use_case_markers),
                    "attribute_markers": _render_marker_list(profile.attribute_markers),
                    "anchor_query": profile.source_anchor_query or "",
                    "members": cluster.members if cluster else [],
                    "meaning_text": _meaning_text(profile),
                }
            )

        model = SentenceTransformer(model_name, device="cpu")
        meaning_embeddings = model.encode(
            [row["meaning_text"] for row in profile_rows],
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        meaning_embeddings = np.asarray(meaning_embeddings, dtype="float32")

        hdbscan = HDBSCAN(
            min_cluster_size=max(20, len(profile_rows) // 300),
            min_samples=5,
            metric="euclidean",
            allow_single_cluster=False,
        )
        hdbscan_labels = hdbscan.fit_predict(meaning_embeddings)
        hdbscan_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        hdbscan_noise: list[dict[str, Any]] = []
        for row, label in zip(profile_rows, hdbscan_labels):
            if int(label) == -1:
                hdbscan_noise.append(row)
                continue
            hdbscan_groups[int(label)].append(row)

        kmeans_scores: list[dict[str, Any]] = []
        best_k = 10
        best_silhouette = float("-inf")
        best_labels = None
        for k in range(10, 21):
            estimator = KMeans(n_clusters=k, random_state=42, n_init="auto")
            labels = estimator.fit_predict(meaning_embeddings)
            silhouette = silhouette_score(
                meaning_embeddings,
                labels,
                metric="cosine",
                sample_size=min(2000, len(profile_rows)),
                random_state=42,
            )
            kmeans_scores.append(
                {
                    "k": k,
                    "silhouette": float(silhouette),
                    "inertia": float(estimator.inertia_),
                }
            )
            if float(silhouette) > best_silhouette:
                best_silhouette = float(silhouette)
                best_k = k
                best_labels = labels

        if best_labels is None:
            raise RuntimeError("KMeans sweep failed to produce labels")

        kmeans_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row, label in zip(profile_rows, best_labels):
            kmeans_groups[int(label)].append(row)

        # Build centroids for SKU probes.
        def build_centroids(groups: dict[int, list[dict[str, Any]]]) -> tuple[np.ndarray, list[int]]:
            group_ids = sorted(groups)
            centroids = []
            key_to_idx = {row["cluster_key"]: idx for idx, row in enumerate(profile_rows)}
            for group_id in group_ids:
                vectors = [meaning_embeddings[key_to_idx[item["cluster_key"]]] for item in groups[group_id]]
                centroid = np.mean(np.stack(vectors, axis=0), axis=0)
                norm = np.linalg.norm(centroid)
                if norm > 0:
                    centroid = centroid / norm
                centroids.append(centroid)
            return np.stack(centroids, axis=0), group_ids

        hdbscan_centroids, hdbscan_group_ids = build_centroids(hdbscan_groups)
        kmeans_centroids, kmeans_group_ids = build_centroids(kmeans_groups)

        probe_skus = _pick_probe_skus(session, project_id=project_id, category_id=category_id, sku_limit=sku_limit)
        for sku in probe_skus:
            sku["reviews"] = _collect_reviews(session, project_id=project_id, nm_id=int(sku["nm_id"]), limit=5)
            sku["meaning_text"] = _sku_meaning_text(
                title=sku["title"],
                description=sku["description"],
                reviews=sku["reviews"],
            )

        sku_embeddings = model.encode(
            [sku["meaning_text"] for sku in probe_skus],
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        sku_embeddings = np.asarray(sku_embeddings, dtype="float32")

        hdbscan_similarity = _cosine_similarity_matrix(sku_embeddings, hdbscan_centroids) if len(hdbscan_groups) else np.zeros((len(probe_skus), 0))
        kmeans_similarity = _cosine_similarity_matrix(sku_embeddings, kmeans_centroids)

        for sku_index, sku in enumerate(probe_skus):
            nearest_hdbscan_groups: list[dict[str, Any]] = []
            if len(hdbscan_groups):
                order = np.argsort(-hdbscan_similarity[sku_index])[:group_probe_top_n]
                for idx in order:
                    group_id = hdbscan_group_ids[int(idx)]
                    items = hdbscan_groups[group_id]
                    nearest_hdbscan_groups.append(
                        {
                            "group_id": group_id,
                            "similarity": _format_similarity(float(hdbscan_similarity[sku_index][idx])),
                            "size": len(items),
                            "sample_labels": [item["profile_label_candidate"] for item in items[:5]],
                        }
                    )
            nearest_kmeans_groups: list[dict[str, Any]] = []
            order = np.argsort(-kmeans_similarity[sku_index])[:group_probe_top_n]
            for idx in order:
                group_id = kmeans_group_ids[int(idx)]
                items = kmeans_groups[group_id]
                nearest_kmeans_groups.append(
                    {
                        "group_id": group_id,
                        "similarity": _format_similarity(float(kmeans_similarity[sku_index][idx])),
                        "size": len(items),
                        "sample_labels": [item["profile_label_candidate"] for item in items[:5]],
                    }
                )
            sku["nearest_hdbscan_groups"] = nearest_hdbscan_groups
            sku["nearest_kmeans_groups"] = nearest_kmeans_groups

        _write_query_groups_report(
            output_path=query_groups_path,
            project_id=project_id,
            category_id=category_id,
            model_name=model_name,
            profile_count=len(profile_rows),
            hdbscan_groups=hdbscan_groups,
            hdbscan_noise=hdbscan_noise,
            kmeans_groups=kmeans_groups,
            kmeans_scores=kmeans_scores,
            kmeans_best_k=best_k,
        )
        _write_sku_probe_report(
            output_path=sku_probe_path,
            project_id=project_id,
            category_id=category_id,
            model_name=model_name,
            sku_probes=probe_skus,
        )

        sample_hdbscan_groups = []
        for group_id, items in sorted(hdbscan_groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:5]:
            sample_hdbscan_groups.append(
                {
                    "group_id": group_id,
                    "size": len(items),
                    "sample_labels": [item["profile_label_candidate"] for item in items[:8]],
                    "top_terms": _top_terms([item["meaning_text"] for item in items], limit=8),
                }
            )

        sample_sku_probes = []
        for sku in probe_skus[:3]:
            sample_sku_probes.append(
                {
                    "nm_id": sku["nm_id"],
                    "title": sku["title"],
                    "nearest_hdbscan_groups": sku["nearest_hdbscan_groups"][:3],
                    "nearest_kmeans_groups": sku["nearest_kmeans_groups"][:3],
                }
            )

        return {
            "project_id": project_id,
            "category_id": category_id,
            "model_name": model_name,
            "profile_count": len(profile_rows),
            "hdbscan_group_count": len(hdbscan_groups),
            "hdbscan_noise_count": len(hdbscan_noise),
            "kmeans_best_k": best_k,
            "kmeans_scores": kmeans_scores,
            "query_groups_report": str(query_groups_path),
            "sku_probe_report": str(sku_probe_path),
            "sample_hdbscan_groups": sample_hdbscan_groups,
            "sample_sku_probes": sample_sku_probes,
        }
    finally:
        session.close()


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])

    sys.path.insert(0, str(SRC_ROOT))

    parser = argparse.ArgumentParser(description="Offline research spike for query meaning groups")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="Sentence embedding model name")
    parser.add_argument("--sku-limit", type=int, default=8, help="How many SKU probes to run")
    parser.add_argument("--top-group-probes", type=int, default=5, help="How many nearest groups per SKU to report")
    args = parser.parse_args()

    summary = _run_spike(
        project_id=args.project_id,
        category_id=args.category_id,
        model_name=str(args.model),
        sku_limit=max(5, min(10, int(args.sku_limit))),
        group_probe_top_n=max(3, min(5, int(args.top_group_probes))),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
