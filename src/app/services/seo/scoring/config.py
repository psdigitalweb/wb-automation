"""Centralized scoring configuration for SEO foundation."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app import settings


@dataclass(frozen=True)
class ScoreWeights:
    """Additive SEO scoring weights for foundation only."""

    semantic_similarity: float
    product_type_match: float
    attribute_match: float
    use_case_match: float
    behavior_score: float
    frequency_score: float
    product_type_mismatch: float
    attribute_mismatch: float
    cluster_mismatch: float
    competition_penalty: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def get_default_score_weights() -> ScoreWeights:
    """Load default weights from centralized settings."""

    return ScoreWeights(**settings.SEO_SCORING_DEFAULT_WEIGHTS)
