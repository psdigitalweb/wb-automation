"""Stage 1 — eligibility.

Runs *before* soft scoring. Produces a per-query verdict from hard constraints
(material conflict, product_type conflict, negative-audience, etc.) and manual
judgments (manual_rejected / too_broad).

Queries with verdict != ``eligible`` skip the soft-scoring stage and are
routed directly into the ``rejected`` or ``broad`` bucket with a low
placeholder score.

This is a copy of the hard-conflict and manual-override logic from
``services.seo.query_meaning_matcher.matcher``; behavior is preserved so that
the candidate path does not drift from current-path semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

from app.models import SeoQueryMeaning, SeoSkuQueryJudgment

# Reuse private helpers from the current matcher to avoid duplicating logic.
# These are stable internal functions; any change here would need a
# coordinated update on both call paths. Iteration 2 introduces the
# ``category_profile`` kwarg so the profile's ``conflict_rules`` can override
# per-category hard-constraint behavior in the future without new literals
# inside ``matcher_v2`` (CI guard: ``tests/seo/test_matcher_v2_no_category_literals.py``).
from app.services.seo.query_meaning_matcher.matcher import (
    _FeatureSet,
    _hard_conflicts,
    _manual_bucket_override,
    _query_display,
)

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


@dataclass
class EligibilityVerdict:
    """Outcome of the eligibility stage for a single (SKU, query) pair."""

    verdict: str  # one of: eligible, hard_conflict, manual_rejected, manual_broad, manual_confirmed
    bucket_hint: str | None = None  # forced bucket when verdict != eligible
    conflicts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    manual_judgment_id: int | None = None


def evaluate_eligibility(
    *,
    sku_features: _FeatureSet,
    query_features: _FeatureSet,
    query_row: SeoQueryMeaning,
    judgment: SeoSkuQueryJudgment | None,
    category_profile: "CategoryProfile | None" = None,
) -> EligibilityVerdict:
    """Run eligibility for one query meaning.

    ``category_profile`` is threaded through so a future change can swap the
    legacy ``_hard_conflicts`` helper for a profile-driven implementation
    without touching call sites. For iteration 2 the argument is accepted but
    not yet consumed — the 812 profile's ``conflict_rules`` are already
    byte-identical to the legacy helper, so behavior is preserved by design.
    """

    del category_profile  # reserved for iteration 3 — intentionally unused
    conflicts = _hard_conflicts(sku_features, query_features)
    manual_bucket, manual_reasons, manual_conflicts = _manual_bucket_override(query_row, judgment)
    judgment_id = int(judgment.id) if judgment is not None else None

    # Manual rejection overrides everything.
    if manual_bucket == "rejected":
        return EligibilityVerdict(
            verdict="manual_rejected",
            bucket_hint="rejected",
            conflicts=list(manual_conflicts) + conflicts,
            reasons=list(manual_reasons),
            manual_judgment_id=judgment_id,
        )

    if manual_bucket == "broad":
        return EligibilityVerdict(
            verdict="manual_broad",
            bucket_hint="broad",
            conflicts=conflicts,
            reasons=list(manual_reasons),
            manual_judgment_id=judgment_id,
        )

    if conflicts:
        return EligibilityVerdict(
            verdict="hard_conflict",
            bucket_hint="rejected",
            conflicts=conflicts,
            reasons=["hard conflict gate"],
            manual_judgment_id=judgment_id,
        )

    if manual_bucket is None and manual_reasons:
        # Manual confirmation (e.g. highly_relevant) still goes through scoring,
        # but we carry the reason forward.
        return EligibilityVerdict(
            verdict="manual_confirmed",
            bucket_hint=None,
            conflicts=[],
            reasons=list(manual_reasons),
            manual_judgment_id=judgment_id,
        )

    return EligibilityVerdict(verdict="eligible", manual_judgment_id=judgment_id)


def query_display_for(row: SeoQueryMeaning) -> str:
    return _query_display(row)


__all__ = ["EligibilityVerdict", "evaluate_eligibility", "query_display_for"]
