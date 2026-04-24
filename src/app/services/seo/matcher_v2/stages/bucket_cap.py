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
from app.services.seo.category_profile_rules import get_bucket_cutoff
from app.services.seo.query_meaning_matcher.runtime_helpers import _apply_atoms_gate

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
    category_profile: "CategoryProfile",
) -> BucketDecision:
    """Bucket + atoms-gate application for a single eligible query.

    Step 9 reads bucket cutoffs from the active CategoryProfile instead of the
    legacy matcher constants.
    """
    primary_cutoff = get_bucket_cutoff(category_profile.scoring, "primary")
    secondary_cutoff = get_bucket_cutoff(category_profile.scoring, "secondary")
    broad_cutoff = get_bucket_cutoff(category_profile.scoring, "broad")
    has_specific_meaning_match = bool(
        expressive_overlap
        or audience_overlap
        or occasion_overlap
        or use_case_overlap
        or attribute_overlap
    )

    if conflicts or (score < min(secondary_cutoff, 0.28) and semantic_similarity < 0.42):
        bucket = "rejected"
    elif genericness == "generic" and not has_specific_meaning_match and score < primary_cutoff:
        bucket = "broad"
    elif (
        genericness == "broad"
        and not has_specific_meaning_match
        and semantic_similarity < 0.78
    ):
        bucket = "broad"
    elif (
        occasion_overlap
        and not expressive_overlap
        and not audience_overlap
        and not use_case_overlap
        and not attribute_overlap
    ):
        bucket = "secondary"
    elif score >= primary_cutoff and (
        expressive_overlap
        or audience_overlap
        or occasion_overlap
        or use_case_overlap
        or attribute_overlap
        or semantic_similarity >= 0.72
    ):
        bucket = "primary"
    elif score >= secondary_cutoff:
        bucket = "secondary"
    elif score >= broad_cutoff:
        bucket = "broad"
    else:
        bucket = "rejected"

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
