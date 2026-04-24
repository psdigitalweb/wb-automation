"""Stage 2 — soft scoring.

Computes the continuous 0..1 score plus per-component overlaps used by the
bucket decision. This is a thin wrapper around the private scoring helpers in
``services.seo.query_meaning_matcher.matcher`` so current-path behavior is
preserved exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.seo.query_meaning_matcher.profile_matcher import (
    _FeatureSet,
    _product_type_score,
)
from app.services.seo.query_meaning_matcher.runtime_helpers import (
    _frequency_boost,
    _overlap_score,
)

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


@dataclass
class SoftScoreResult:
    """Continuous score + overlap details for a single (SKU, query) pair."""

    score: float
    semantic_similarity: float
    genericness: str
    product_score: float
    expressive_overlap: list[str] = field(default_factory=list)
    use_case_overlap: list[str] = field(default_factory=list)
    attribute_overlap: list[str] = field(default_factory=list)
    audience_overlap: list[str] = field(default_factory=list)
    occasion_overlap: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)


def compute_soft_score(
    *,
    sku_features: _FeatureSet,
    query_features: _FeatureSet,
    semantic_similarity: float,
    genericness: str,
    ranking_value: float | None,
    has_conflicts: bool,
    category_profile: "CategoryProfile",
) -> SoftScoreResult:
    """Run the soft-scoring stage for a single query meaning.

    The caller is still responsible for applying conflict / manual penalties
    before bucketing (see ``stages/bucket_cap.py``). Step 9 reads overlap and
    product-type weights from the active CategoryProfile.
    """
    reasons: list[str] = []
    matched: list[str] = []
    weights = category_profile.scoring.weights

    product_score, product_reasons = _product_type_score(
        sku_features,
        query_features,
        profile=category_profile,
    )
    reasons.extend(product_reasons)

    expressive_score, expressive_overlap, expressive_reasons = _overlap_score(
        "expressive",
        sku_features.expressive_terms,
        query_features.expressive_terms,
        float(weights.get("expressive_overlap", 0.22)),
    )
    use_case_score, use_case_overlap, use_case_reasons = _overlap_score(
        "use_case",
        sku_features.use_case_terms,
        query_features.use_case_terms,
        float(weights.get("use_case_overlap", 0.14)),
    )
    attribute_score, attribute_overlap, attribute_reasons = _overlap_score(
        "attribute",
        sku_features.attribute_terms,
        query_features.attribute_terms,
        float(weights.get("attribute_overlap", 0.08)),
    )
    audience_score, audience_overlap, audience_reasons = _overlap_score(
        "audience",
        sku_features.audience_terms,
        query_features.audience_terms,
        float(weights.get("audience_overlap", 0.12)),
    )
    occasion_score, occasion_overlap, occasion_reasons = _overlap_score(
        "occasion",
        sku_features.occasion_terms,
        query_features.occasion_terms,
        float(weights.get("occasion_overlap", 0.05)),
    )
    reasons.extend(
        expressive_reasons
        + use_case_reasons
        + attribute_reasons
        + audience_reasons
        + occasion_reasons
    )
    matched.extend(
        expressive_overlap
        + use_case_overlap
        + attribute_overlap
        + audience_overlap
        + occasion_overlap
    )

    specificity_bonus = (
        float(weights.get("specificity_bonus", 0.08))
        if genericness == "specific"
        else 0.0
    )
    genericness_penalty = (
        float(weights.get("genericness_generic_penalty", 0.18))
        if genericness == "generic"
        else (
            float(weights.get("genericness_broad_penalty", 0.09))
            if genericness == "broad"
            else 0.0
        )
    )
    conflict_penalty = (
        float(weights.get("conflict_penalty", 0.55)) if has_conflicts else 0.0
    )
    frequency = _frequency_boost(ranking_value, allow=not has_conflicts and genericness == "specific")

    raw_score = (
        0.34 * semantic_similarity
        + product_score
        + expressive_score
        + use_case_score
        + attribute_score
        + audience_score
        + occasion_score
        + specificity_bonus
        + frequency
        - genericness_penalty
        - conflict_penalty
    )
    score = round(max(0.0, min(1.0, raw_score)), 4)

    if frequency:
        reasons.append("frequency boosts already relevant candidate")
    if genericness in {"generic", "broad"}:
        reasons.append(f"downgraded by genericness: {genericness}")

    components = {
        "semantic_similarity": round(semantic_similarity, 4),
        "product_score": round(product_score, 4),
        "expressive_score": round(expressive_score, 4),
        "use_case_score": round(use_case_score, 4),
        "attribute_score": round(attribute_score, 4),
        "audience_score": round(audience_score, 4),
        "occasion_score": round(occasion_score, 4),
        "specificity_bonus": round(specificity_bonus, 4),
        "genericness_penalty": round(genericness_penalty, 4),
        "conflict_penalty": round(conflict_penalty, 4),
        "frequency_boost": round(frequency, 4),
    }

    return SoftScoreResult(
        score=score,
        semantic_similarity=semantic_similarity,
        genericness=genericness,
        product_score=product_score,
        expressive_overlap=expressive_overlap,
        use_case_overlap=use_case_overlap,
        attribute_overlap=attribute_overlap,
        audience_overlap=audience_overlap,
        occasion_overlap=occasion_overlap,
        matched_terms=matched,
        reasons=reasons,
        components=components,
    )


__all__ = ["SoftScoreResult", "compute_soft_score"]
