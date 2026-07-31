"""Literal-free runtime helpers shared by active matcher paths.

The Step 9 contract removes ``matcher_v2``'s dependency on the legacy matcher
module for generic scoring / ordering helpers. Category-specific logic still
lives in ``profile_matcher.py`` while the deprecated literal-heavy path stays
isolated under ``query_meaning_matcher._legacy``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SeoQueryClusterMembership, SeoQueryMeaning, SeoSkuQueryJudgment
from app.services.seo.category_profile_rules import product_type_compatibility_reason
from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.atoms.v1.matcher_v1 import match_atoms_v1
from app.services.seo.atoms.v1.schemas import QueryAtoms
from app.services.seo.query_pipeline import normalize_query_text

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


_WEAK_OVERLAP_TOKENS = {
    "а",
    "без",
    "в",
    "во",
    "для",
    "до",
    "и",
    "из",
    "к",
    "ко",
    "на",
    "не",
    "о",
    "об",
    "от",
    "по",
    "под",
    "при",
    "про",
    "с",
    "со",
    "у",
}


def _ranking_by_cluster(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    cluster_ids: list[int],
) -> dict[int, float]:
    if not cluster_ids:
        return {}
    rows = session.execute(
        select(
            SeoQueryClusterMembership.cluster_id,
            SeoQueryClusterMembership.ranking_value_used,
        )
        .where(
            SeoQueryClusterMembership.project_id == int(project_id),
            SeoQueryClusterMembership.category_id == int(category_id),
            SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
        )
        .order_by(desc(SeoQueryClusterMembership.ranking_value_used))
    ).all()
    result: dict[int, float] = {}
    for cluster_id, ranking in rows:
        cid = int(cluster_id)
        try:
            value = float(ranking or 0)
        except Exception:
            value = 0.0
        result[cid] = max(result.get(cid, 0.0), value)
    return result


def _overlap_score(
    label: str,
    left: set[str],
    right: set[str],
    weight: float,
) -> tuple[float, list[str], list[str]]:
    overlap = sorted((left & right) - _WEAK_OVERLAP_TOKENS)
    if not overlap:
        return 0.0, [], []
    score = min(weight, weight * (0.55 + 0.25 * len(overlap)))
    return score, overlap, [f"{label} matched: {', '.join(overlap[:5])}"]


def _frequency_boost(value: float | None, *, allow: bool) -> float:
    if not allow or value is None or value <= 0:
        return 0.0
    return min(0.08, math.log10(value + 1.0) / 90.0)


def _query_display(row: SeoQueryMeaning) -> str:
    examples = list(row.source_query_examples or [])
    return str(examples[0]) if examples else str(row.cluster_key)


def _judgment_overrides_by_query(
    session: Session,
    *,
    annotation_id: int,
) -> tuple[dict[str, SeoSkuQueryJudgment], dict[str, SeoSkuQueryJudgment]]:
    rows = session.scalars(
        select(SeoSkuQueryJudgment).where(
            SeoSkuQueryJudgment.annotation_id == int(annotation_id)
        )
    ).all()
    by_query: dict[str, SeoSkuQueryJudgment] = {}
    by_cluster_key: dict[str, SeoSkuQueryJudgment] = {}
    for row in rows:
        normalized = normalize_query_text(
            str(row.normalized_query_text or row.query_text or "")
        )
        if normalized:
            by_query[normalized] = row
        if row.cluster_key:
            by_cluster_key[str(row.cluster_key)] = row
    return by_query, by_cluster_key


def _manual_bucket_override(
    row: SeoQueryMeaning,
    judgment: SeoSkuQueryJudgment | None,
) -> tuple[str | None, list[str], list[str]]:
    if judgment is None:
        return None, [], []
    label = str(judgment.label or "")
    reason = f"manual judgment: {label}"
    if judgment.rationale:
        reason = f"{reason} ({judgment.rationale})"
    if label in {"manual_rejected", "irrelevant", "conflict", "dangerous_claim"}:
        return "rejected", [reason], [reason]
    if label == "too_broad":
        return "broad", [reason], []
    if label in {"highly_relevant", "maybe_relevant"}:
        return None, [reason], []
    return None, [reason], []


def _user_reasons(
    *,
    bucket: str,
    matched_atoms: list[str],
    missing_atoms: list[str],
    conflict_atoms: list[str],
    fallback_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    if conflict_atoms:
        reasons.append("Есть обязательное несовпадение с товаром")
    if missing_atoms:
        reasons.append("В запросе есть требование, которого нет у товара")
    if matched_atoms:
        reasons.append("Совпали признаки товара и запроса")
    if bucket == "broad":
        reasons.append("Запрос слишком общий для точной оптимизации")
    if not reasons:
        if any("manual judgment" in item for item in fallback_reasons):
            reasons.append("Учтена ручная правка")
        elif bucket == "primary":
            reasons.append("Хорошее смысловое совпадение без конфликтов")
        elif bucket == "secondary":
            reasons.append("Запрос подходит, но не самый точный")
        elif bucket == "rejected":
            reasons.append("Смысл запроса слабо соответствует товару")
    return reasons


def _query_coverage_tags(item: MeaningAwareMatcherItem) -> list[str]:
    query = normalize_query_text(item.query)
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    if "пинтерест" in query or "pinterest" in query:
        add("style:pinterest")
    if "эстет" in query or "красив" in query:
        add("style:aesthetic")
    if "мил" in query or "няш" in query:
        add("style:cute")

    for atom in item.matched_atoms:
        parts = str(atom or "").split(":")
        if len(parts) < 2:
            continue
        if "motif" in parts:
            add(f"motif:{parts[-1]}")
        elif "expressive" in parts:
            add(f"expressive:{parts[-1]}")
        elif "recipient" in parts:
            add(f"recipient:{parts[-1]}")
        elif "occasion" in parts:
            add(f"occasion:{parts[-1]}")
    return tags


def _select_bucket_with_coverage(
    candidates: list[MeaningAwareMatcherItem],
    limit: int,
) -> list[MeaningAwareMatcherItem]:
    if len(candidates) <= limit:
        return candidates
    selected: list[MeaningAwareMatcherItem] = []
    selected_keys: set[tuple[str, int | None, str]] = set()
    tag_counts: dict[str, int] = {}
    coverage_budget = min(20, max(8, limit // 2))
    per_tag_limit = 3

    def key(item: MeaningAwareMatcherItem) -> tuple[str, int | None, str]:
        return (
            str(item.cluster_key or ""),
            item.query_meaning_id,
            normalize_query_text(item.query),
        )

    def add(item: MeaningAwareMatcherItem) -> bool:
        item_key = key(item)
        if item_key in selected_keys:
            return False
        selected.append(item)
        selected_keys.add(item_key)
        return True

    tag_items: dict[str, list[MeaningAwareMatcherItem]] = {}
    for item in candidates:
        for tag in _query_coverage_tags(item):
            tag_items.setdefault(tag, []).append(item)

    priority_tags = [
        "style:pinterest",
        "style:aesthetic",
        "style:cute",
        *sorted(tag for tag in tag_items if not tag.startswith("style:")),
    ]
    for tag in priority_tags:
        if len(selected) >= coverage_budget:
            break
        for item in tag_items.get(tag, []):
            if tag_counts.get(tag, 0) >= per_tag_limit or len(selected) >= coverage_budget:
                break
            if add(item):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    for item in candidates:
        if len(selected) >= limit:
            break
        add(item)
    return selected[:limit]


def _apply_atoms_gate(
    *,
    bucket: str,
    score: float,
    row: SeoQueryMeaning,
    query_display: str,
    ranking_value: float | None,
    sku_atoms: Any,
    query_atoms_payload: dict[str, Any] | None,
    category_profile: "CategoryProfile | None" = None,
) -> tuple[str, float, list[str], list[str], list[str], list[str]]:
    if sku_atoms is None or not query_atoms_payload:
        return bucket, score, [], [], [], ["atoms gate skipped: missing SKU or query atoms"]
    try:
        query_atoms = QueryAtoms.model_validate(query_atoms_payload)
        compatibility_reason = (
            (
                lambda query_type, sku_type: product_type_compatibility_reason(
                    query_type,
                    sku_type,
                    profile=category_profile,
                )
            )
            if category_profile is not None
            else None
        )
        atoms_result = match_atoms_v1(
            sku_atoms,
            query_atoms,
            query_text=query_display,
            cluster_key=str(row.cluster_key or ""),
            ranking_value_used=ranking_value,
            product_type_compatibility_reason=compatibility_reason,
        )
    except Exception as exc:
        return bucket, score, [], [], [], [f"atoms gate skipped: {type(exc).__name__}: {exc}"]

    gated_bucket = bucket
    gated_score = score
    if atoms_result.bucket == "rejected":
        gated_bucket = "rejected"
        gated_score = min(score, atoms_result.score, 0.05)
    elif atoms_result.bucket == "broad":
        if bucket in {"primary", "secondary"}:
            gated_bucket = "broad"
            gated_score = min(score, 0.45)
    elif atoms_result.bucket == "primary":
        if bucket in {"secondary", "broad"}:
            gated_bucket = "primary"
        gated_score = max(score, atoms_result.score)
    elif bucket == "primary" and atoms_result.bucket != "primary":
        gated_bucket = "secondary"
        gated_score = min(score, max(0.34, atoms_result.score))

    debug_reasons = [f"atoms bucket: {atoms_result.bucket}", *atoms_result.reasons]
    return (
        gated_bucket,
        round(max(0.0, min(1.0, gated_score)), 4),
        atoms_result.matched_atoms,
        atoms_result.missing_atoms,
        atoms_result.conflict_atoms,
        debug_reasons,
    )


__all__ = [
    "_apply_atoms_gate",
    "_frequency_boost",
    "_judgment_overrides_by_query",
    "_manual_bucket_override",
    "_overlap_score",
    "_query_display",
    "_ranking_by_cluster",
    "_select_bucket_with_coverage",
    "_user_reasons",
]
