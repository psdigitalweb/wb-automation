"""Stage 4 — demand ordering and per-bucket coverage selection.

Sorts items within a bucket and applies the coverage selection logic used by
the current matcher (style / motif / recipient / occasion tag coverage).
"""

from __future__ import annotations

import math
from typing import Iterable

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem

# Reuse the current matcher's coverage-aware selection helper. No logic change
# in iteration 1.
from app.services.seo.query_meaning_matcher.matcher import _select_bucket_with_coverage


def per_bucket_limit(limit: int) -> int:
    """Per-bucket cap derived from the caller's top-N limit."""
    return max(10, min(100, math.ceil(max(1, int(limit)) / 4)))


def sort_items(items: Iterable[MeaningAwareMatcherItem]) -> list[MeaningAwareMatcherItem]:
    """Sort items by (-score, -ranking, query) — same as the current matcher."""
    return sorted(
        list(items),
        key=lambda item: (-item.score, -(item.ranking_value_used or 0), item.query),
    )


def partition_buckets(
    items: list[MeaningAwareMatcherItem],
    *,
    limit: int,
) -> dict[str, list[MeaningAwareMatcherItem]]:
    """Split sorted items into per-bucket lists with coverage-aware selection."""
    cap = per_bucket_limit(limit)
    return {
        "primary": _select_bucket_with_coverage(
            [item for item in items if item.bucket == "primary"], cap
        ),
        "secondary": _select_bucket_with_coverage(
            [item for item in items if item.bucket == "secondary"], cap
        ),
        "broad": [item for item in items if item.bucket == "broad"][:cap],
        "rejected": [item for item in items if item.bucket == "rejected"][:cap],
    }


__all__ = ["per_bucket_limit", "sort_items", "partition_buckets"]
