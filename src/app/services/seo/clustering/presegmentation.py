"""Rule-based pre-segmentation hook placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PreSegment:
    """Placeholder pre-segmentation result."""

    segment_key: str
    sku_records: list[dict[str, Any]]


def presegment_skus(sku_records: Iterable[dict[str, Any]]) -> list[PreSegment]:
    """Return a single placeholder segment until real rules exist."""

    return [PreSegment(segment_key="default", sku_records=[dict(item) for item in sku_records])]
