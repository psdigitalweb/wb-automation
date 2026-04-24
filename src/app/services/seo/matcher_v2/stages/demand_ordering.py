"""Stage 4 — demand ordering and per-bucket coverage selection.

Sorts items within a bucket and applies the coverage selection logic used by
the current matcher (style / motif / recipient / occasion tag coverage).
"""

from __future__ import annotations

import math
from typing import Iterable, TYPE_CHECKING

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.query_meaning_matcher.runtime_helpers import (
    _select_bucket_with_coverage,
)

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


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
    category_profile: "CategoryProfile",
) -> dict[str, list[MeaningAwareMatcherItem]]:
    """Split sorted items into per-bucket lists with coverage-aware selection."""
    cap = per_bucket_limit(limit)
    bucket_caps = category_profile.scoring.bucket_caps

    def bucket_limit(bucket: str) -> int:
        configured = int(bucket_caps.get(bucket, cap))
        return max(1, min(cap, configured))

    return {
        "primary": _select_bucket_with_coverage(
            [item for item in items if item.bucket == "primary"],
            bucket_limit("primary"),
        ),
        "secondary": _select_bucket_with_coverage(
            [item for item in items if item.bucket == "secondary"],
            bucket_limit("secondary"),
        ),
        "broad": [item for item in items if item.bucket == "broad"][
            : bucket_limit("broad")
        ],
        "rejected": [item for item in items if item.bucket == "rejected"][
            : bucket_limit("rejected")
        ],
    }


__all__ = ["per_bucket_limit", "sort_items", "partition_buckets"]
