"""Stage 3 — bucket + atoms gate.

Turns a soft score into a ``primary``/``secondary``/``broad``/``rejected``
bucket, then applies the atoms gate (preserved verbatim from the current
matcher) to cap the bucket when structured atom evidence disagrees with the
score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from app.models import SeoQueryMeaning
from app.services.seo.query_meaning_matcher.matcher import (
    _apply_atoms_gate,
    _bucket_for,
)

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


@dataclass
class BucketDecision:
    """Final bucket + cap explanation for one query meaning."""

    bucket: str
    score: float
    matched_atoms: list[str] = field(default_factory=list)
    missing_atoms: list[str] = field(default_factory=list)
    conflict_atoms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def decide_bucket(
    *,
    score: float,
    genericness: str,
    conflicts: list[str],
    semantic_similarity: float,
    expressive_overlap: list[str],
    audience_overlap: list[str],
    occasion_overlap: list[str],
    use_case_overlap: list[str],
    attribute_overlap: list[str],
    row: SeoQueryMeaning,
    query_display: str,
    ranking_value: float | None,
    sku_atoms: Any | None,
    query_atoms_payload: dict[str, Any] | None,
    category_profile: "CategoryProfile | None" = None,
) -> BucketDecision:
    """Bucket + atoms-gate application for a single eligible query.

    ``category_profile`` is threaded through so future iterations can read
    ``profile.bucket_cutoffs`` in place of the legacy constants without
    introducing new category-specific literals at this layer.
    """

    del category_profile  # reserved for iteration 3 — intentionally unused
    bucket = _bucket_for(
        score=score,
        genericness=genericness,
        conflicts=conflicts,
        semantic_similarity=semantic_similarity,
        expressive_overlap=expressive_overlap,
        audience_overlap=audience_overlap,
        occasion_overlap=occasion_overlap,
        use_case_overlap=use_case_overlap,
        attribute_overlap=attribute_overlap,
    )

    capped_bucket, capped_score, matched, missing, conflict, debug_reasons = _apply_atoms_gate(
        bucket=bucket,
        score=score,
        row=row,
        query_display=query_display,
        ranking_value=ranking_value,
        sku_atoms=sku_atoms,
        query_atoms_payload=query_atoms_payload,
    )

    return BucketDecision(
        bucket=capped_bucket,
        score=capped_score,
        matched_atoms=list(matched),
        missing_atoms=list(missing),
        conflict_atoms=list(conflict),
        reasons=list(debug_reasons),
    )


__all__ = ["BucketDecision", "decide_bucket"]
