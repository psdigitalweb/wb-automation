"""[FROZEN iter-1] Rule-based pre-segmentation hook placeholder.

See ``app.services.seo.clustering.__init__`` for the deprecation banner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.seo._freeze import guard_frozen_module

guard_frozen_module(__name__)


@dataclass(frozen=True)
class PreSegment:
    """Placeholder pre-segmentation result."""

    segment_key: str
    sku_records: list[dict[str, Any]]


def presegment_skus(sku_records: Iterable[dict[str, Any]]) -> list[PreSegment]:
    """Return a single placeholder segment until real rules exist."""

    return [PreSegment(segment_key="default", sku_records=[dict(item) for item in sku_records])]
