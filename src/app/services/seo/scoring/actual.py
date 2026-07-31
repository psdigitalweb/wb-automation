"""Deterministic explainable scoring built on top of scoring preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.seo.query_pipeline.diagnostics import _serialize_value
from app.services.seo.scoring.preparation import (
    AttributeMatchResult,
    ClusterScoringPreparation,
    PreparationFlags,
    QueryScoringPreparationResult,
    ReadinessStatus,
    ScoringPreparationMarkerEvaluation,
    UseCaseMatchResult,
    run_query_scoring_preparation,
)

_PRODUCT_TYPE_SCORES = {
    "matched": 1.0,
    "not_matched": -1.0,
    "unknown": 0.0,
}

_USE_CASE_MARKER_SCORES = {
    "matched": 0.3,
    "missed": -0.1,
    "unknown": 0.0,
}

_ATTRIBUTE_MARKER_SCORES = {
    "matched": 0.2,
    "missed": -0.05,
    "conflicting": -0.3,
    "unknown": 0.0,
}

_PROFILE_STRENGTH_MULTIPLIERS = {
    "strong": 1.0,
    "medium": 0.85,
    "weak": 0.6,
    "empty": 0.2,
}

_READINESS_MULTIPLIERS: dict[ReadinessStatus, float] = {
    "ready": 1.0,
    "partial": 0.75,
    "poor": 0.3,
}

_FLAG_PENALTIES = {
    "conflicting_profile_markers": -0.2,
    "missing_product_type": -0.5,
    "insufficient_sku_data": -0.5,
}

_WEAK_USE_CASE_TOKENS = {
    "любимого",
    "любимой",
    "любимому",
    "любимая",
    "любимый",
    "любимую",
    "любимых",
    "мужа",
    "жены",
    "маме",
    "мамы",
    "папы",
    "подруги",
    "подруге",
    "друга",
    "другу",
    "парня",
    "девушки",
    "подарка",
    "подарок",
}
_WEAK_USE_CASE_PHRASES = (
    "для любимого",
    "для любимой",
    "для любимых",
    "для мужа",
    "для жены",
    "для мамы",
    "для папы",
    "для подруги",
    "для друга",
    "для девушки",
    "для парня",
)


def _round_score(value: float) -> float:
    return round(float(value), 4)


def _round_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _format_signed(value: float) -> str:
    rounded = _round_score(value)
    sign = "+" if rounded >= 0 else ""
    return f"{sign}{rounded:.4f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class QueryActualScoringModifiers:
    profile_strength: str
    profile_strength_multiplier: float
    readiness_for_scoring: ReadinessStatus
    readiness_multiplier: float
    combined_multiplier: float

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryActualScoringPenalty:
    name: str
    value: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryActualScoringItem:
    cluster_key: str
    profile_label_candidate: str
    final_score: float
    base_score: float
    weighted_score: float
    product_type_score: float
    use_case_score: float
    attribute_score: float
    modifiers: QueryActualScoringModifiers
    penalties: list[QueryActualScoringPenalty] = field(default_factory=list)
    penalties_total: float = 0.0
    readiness_for_scoring: ReadinessStatus = "partial"
    preparation_flags: PreparationFlags = field(default_factory=PreparationFlags)
    ranking_eligible: bool = False
    generation_eligible: bool = False
    generation_guardrail_reason: str | None = None
    final_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryActualScoringDiagnostics:
    project_id: int
    category_id: int
    nm_id: int
    total_clusters_scored: int = 0
    avg_score: float = 0.0
    top_score: float = 0.0
    bottom_score: float = 0.0
    positive_score_count: int = 0
    neutral_score_count: int = 0
    negative_score_count: int = 0
    positive_score_share: float = 0.0
    neutral_score_share: float = 0.0
    negative_score_share: float = 0.0
    avg_product_type_score: float = 0.0
    avg_use_case_score: float = 0.0
    avg_attribute_score: float = 0.0
    top_clusters: list[QueryActualScoringItem] = field(default_factory=list)
    bottom_clusters: list[QueryActualScoringItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryActualScoringResult:
    project_id: int
    category_id: int
    nm_id: int
    preparation_result: QueryScoringPreparationResult
    scores: list[QueryActualScoringItem]
    diagnostics: QueryActualScoringDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


def _is_weak_use_case_marker(marker: ScoringPreparationMarkerEvaluation) -> bool:
    normalized = (marker.normalized_value or "").strip().lower()
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _WEAK_USE_CASE_PHRASES):
        return True
    tokens = [token for token in normalized.split(" ") if token]
    if "для" in tokens and any(token in _WEAK_USE_CASE_TOKENS for token in tokens):
        return True
    return False


def _score_use_case(match: UseCaseMatchResult) -> tuple[float, list[str]]:
    markers: list[tuple[ScoringPreparationMarkerEvaluation, str]] = (
        [(marker, "matched") for marker in match.matched_markers]
        + [(marker, "missed") for marker in match.missed_markers]
        + [(marker, "unknown") for marker in match.unknown_markers]
    )
    total_markers = len(markers)
    if total_markers <= 0:
        return 0.0, []

    raw_sum = 0.0
    weak_markers: list[str] = []
    for marker, status in markers:
        if _is_weak_use_case_marker(marker):
            weak_markers.append(marker.normalized_value or marker.value)
            if status == "matched":
                raw_sum += 0.05
            elif status == "missed":
                raw_sum += 0.0
            else:
                raw_sum += 0.0
            continue
        raw_sum += _USE_CASE_MARKER_SCORES[status]
    return _round_score(raw_sum / total_markers), weak_markers


def _score_attributes(match: AttributeMatchResult) -> float:
    return _round_score(
        len(match.matched_markers) * _ATTRIBUTE_MARKER_SCORES["matched"]
        + len(match.missed_markers) * _ATTRIBUTE_MARKER_SCORES["missed"]
        + len(match.conflicting_markers) * _ATTRIBUTE_MARKER_SCORES["conflicting"]
        + len(match.unknown_markers) * _ATTRIBUTE_MARKER_SCORES["unknown"]
    )


def _build_penalties(flags: PreparationFlags) -> list[QueryActualScoringPenalty]:
    penalties: list[QueryActualScoringPenalty] = []
    for name, value in _FLAG_PENALTIES.items():
        if getattr(flags, name, False):
            penalties.append(
                QueryActualScoringPenalty(
                    name=name,
                    value=_round_score(value),
                    reason=name,
                )
            )
    return penalties


def _build_reason(
    preparation: ClusterScoringPreparation,
    *,
    product_type_score: float,
    use_case_score: float,
    attribute_score: float,
    modifiers: QueryActualScoringModifiers,
    penalties: list[QueryActualScoringPenalty],
    weak_use_case_markers: list[str],
    ranking_eligible: bool,
    generation_eligible: bool,
    generation_guardrail_reason: str | None,
    final_score: float,
) -> str:
    use_case_counts = (
        len(preparation.use_case_match.matched_markers),
        len(preparation.use_case_match.missed_markers),
        len(preparation.use_case_match.unknown_markers),
    )
    attribute_counts = (
        len(preparation.attribute_match.matched_markers),
        len(preparation.attribute_match.conflicting_markers),
        len(preparation.attribute_match.missed_markers),
        len(preparation.attribute_match.unknown_markers),
    )
    parts = [
        f"product_type {preparation.product_type_match.status} ({_format_signed(product_type_score)})",
        (
            "use_case "
            f"m={use_case_counts[0]}/x={use_case_counts[1]}/u={use_case_counts[2]} "
            f"({_format_signed(use_case_score)})"
        ),
        (
            "attributes "
            f"m={attribute_counts[0]}/c={attribute_counts[1]}/x={attribute_counts[2]}/u={attribute_counts[3]} "
            f"({_format_signed(attribute_score)})"
        ),
        f"{modifiers.profile_strength} profile ×{modifiers.profile_strength_multiplier:.2f}",
        f"{modifiers.readiness_for_scoring} readiness ×{modifiers.readiness_multiplier:.2f}",
    ]
    if weak_use_case_markers:
        parts.append(f"weak_use_case_marker downweighted: {', '.join(sorted(set(weak_use_case_markers)))}")
    if penalties:
        penalty_summary = ", ".join(f"{item.name} ({_format_signed(item.value)})" for item in penalties)
        parts.append(f"penalties {penalty_summary}")
    parts.append(f"ranking_eligible={str(ranking_eligible).lower()}")
    parts.append(
        "generation_eligible="
        f"{str(generation_eligible).lower()}"
        + (f" ({generation_guardrail_reason})" if generation_guardrail_reason else "")
    )
    parts.append(f"final {_round_score(final_score):.4f}".rstrip("0").rstrip("."))
    return ", ".join(parts)


def _build_generation_guardrail(
    preparation: ClusterScoringPreparation,
    *,
    final_score: float,
    weak_use_case_markers: list[str],
) -> tuple[bool, str | None]:
    if preparation.preparation_flags.empty_profile:
        return False, "empty_profile"
    if preparation.preparation_flags.missing_product_type:
        return False, "missing_product_type"
    if preparation.product_type_match.status != "matched":
        return False, "product_type_not_matched"
    if preparation.readiness_for_scoring == "poor":
        return False, "poor_readiness"
    matched_non_weak_use_case_count = sum(
        1
        for marker in preparation.use_case_match.matched_markers
        if not _is_weak_use_case_marker(marker)
    )
    no_conflicts = not preparation.preparation_flags.conflicting_profile_markers and not preparation.attribute_match.conflicting_markers
    has_strong_compensator = (
        _score_attributes(preparation.attribute_match) > 0
        or matched_non_weak_use_case_count > 0
        or (final_score >= 1.2 and no_conflicts)
    )
    if weak_use_case_markers and not has_strong_compensator:
        return False, "weak_semantic_use_case"
    if preparation.preparation_flags.conflicting_profile_markers:
        return False, "conflicting_profile_markers"
    if final_score < 0.8:
        return False, "low_score"
    return True, None


def _score_preparation(preparation: ClusterScoringPreparation) -> QueryActualScoringItem:
    product_type_score = _round_score(_PRODUCT_TYPE_SCORES[preparation.product_type_match.status])
    use_case_score, weak_use_case_markers = _score_use_case(preparation.use_case_match)
    attribute_score = _score_attributes(preparation.attribute_match)
    base_score = _round_score(product_type_score + use_case_score + attribute_score)

    strength_multiplier = _PROFILE_STRENGTH_MULTIPLIERS.get(preparation.profile_strength, 1.0)
    readiness_multiplier = _READINESS_MULTIPLIERS.get(preparation.readiness_for_scoring, 1.0)
    combined_multiplier = _round_score(strength_multiplier * readiness_multiplier)
    modifiers = QueryActualScoringModifiers(
        profile_strength=preparation.profile_strength,
        profile_strength_multiplier=_round_score(strength_multiplier),
        readiness_for_scoring=preparation.readiness_for_scoring,
        readiness_multiplier=_round_score(readiness_multiplier),
        combined_multiplier=combined_multiplier,
    )

    weighted_score = _round_score(base_score * combined_multiplier)
    penalties = _build_penalties(preparation.preparation_flags)
    penalties_total = _round_score(sum(item.value for item in penalties))
    final_score = _round_score(weighted_score + penalties_total)
    ranking_eligible = final_score > 0 and preparation.product_type_match.status == "matched"
    generation_eligible, generation_guardrail_reason = _build_generation_guardrail(
        preparation,
        final_score=final_score,
        weak_use_case_markers=weak_use_case_markers,
    )

    return QueryActualScoringItem(
        cluster_key=preparation.cluster_key,
        profile_label_candidate=preparation.profile_label_candidate,
        final_score=final_score,
        base_score=base_score,
        weighted_score=weighted_score,
        product_type_score=product_type_score,
        use_case_score=use_case_score,
        attribute_score=attribute_score,
        modifiers=modifiers,
        penalties=penalties,
        penalties_total=penalties_total,
        readiness_for_scoring=preparation.readiness_for_scoring,
        preparation_flags=preparation.preparation_flags,
        ranking_eligible=ranking_eligible,
        generation_eligible=generation_eligible,
        generation_guardrail_reason=generation_guardrail_reason,
        final_reason=_build_reason(
            preparation,
            product_type_score=product_type_score,
            use_case_score=use_case_score,
            attribute_score=attribute_score,
            modifiers=modifiers,
            penalties=penalties,
            weak_use_case_markers=weak_use_case_markers,
            ranking_eligible=ranking_eligible,
            generation_eligible=generation_eligible,
            generation_guardrail_reason=generation_guardrail_reason,
            final_score=final_score,
        ),
    )


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    scores: list[QueryActualScoringItem],
    top_limit: int,
) -> QueryActualScoringDiagnostics:
    total = len(scores)
    if total <= 0:
        return QueryActualScoringDiagnostics(
            project_id=project_id,
            category_id=category_id,
            nm_id=nm_id,
            total_clusters_scored=0,
        )

    avg_score = _round_score(sum(item.final_score for item in scores) / total)
    avg_product_type = _round_score(sum(item.product_type_score for item in scores) / total)
    avg_use_case = _round_score(sum(item.use_case_score for item in scores) / total)
    avg_attribute = _round_score(sum(item.attribute_score for item in scores) / total)
    positive_count = sum(1 for item in scores if item.final_score > 0.2)
    neutral_count = sum(1 for item in scores if -0.2 <= item.final_score <= 0.2)
    negative_count = sum(1 for item in scores if item.final_score < -0.2)
    sorted_desc = sorted(scores, key=lambda item: (-float(item.final_score), item.cluster_key))
    sorted_asc = sorted(scores, key=lambda item: (float(item.final_score), item.cluster_key))
    sample_limit = max(1, int(top_limit))

    return QueryActualScoringDiagnostics(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        total_clusters_scored=total,
        avg_score=avg_score,
        top_score=_round_score(sorted_desc[0].final_score),
        bottom_score=_round_score(sorted_asc[0].final_score),
        positive_score_count=positive_count,
        neutral_score_count=neutral_count,
        negative_score_count=negative_count,
        positive_score_share=_round_ratio(positive_count, total),
        neutral_score_share=_round_ratio(neutral_count, total),
        negative_score_share=_round_ratio(negative_count, total),
        avg_product_type_score=avg_product_type,
        avg_use_case_score=avg_use_case,
        avg_attribute_score=avg_attribute,
        top_clusters=sorted_desc[:sample_limit],
        bottom_clusters=sorted_asc[:sample_limit],
    )


def run_query_actual_scoring(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    top_limit: int = 20,
) -> QueryActualScoringResult:
    """Rank cluster profiles for one SKU using deterministic explainable scoring."""

    sample_limit = max(1, int(top_limit))
    preparation_result = run_query_scoring_preparation(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        top_limit=sample_limit,
        samples_limit=sample_limit,
        refresh_hybrid=True,
    )
    scores = [_score_preparation(preparation) for preparation in preparation_result.preparations]
    scores.sort(
        key=lambda item: (
            -float(item.final_score),
            -float(item.product_type_score),
            -float(item.use_case_score),
            -float(item.attribute_score),
            item.cluster_key,
        )
    )
    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        scores=scores,
        top_limit=sample_limit,
    )
    return QueryActualScoringResult(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        preparation_result=preparation_result,
        scores=scores,
        diagnostics=diagnostics,
    )
