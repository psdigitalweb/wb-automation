"""Trust-aware SKU representation placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkuRepresentation:
    """Minimal SKU representation for later clustering phases."""

    nm_id: int
    tokens: list[str]
    trust_state: str
    manual_review_required: bool


def build_sku_representation(sku_record: dict[str, Any]) -> SkuRepresentation:
    """Build a conservative placeholder representation without semantic inference."""

    title = str(sku_record.get("title") or sku_record.get("name") or "").strip()
    attributes = sku_record.get("attributes") or {}
    if not isinstance(attributes, dict):
        attributes = {}
    attribute_tokens = [f"{key}:{value}" for key, value in sorted(attributes.items()) if value not in (None, "")]
    cleaned_reviews = int(sku_record.get("cleaned_review_count") or 0)
    meaningful_reviews = int(sku_record.get("meaningful_review_count") or 0)
    trust_state = "reviews_enriched" if cleaned_reviews >= 15 and meaningful_reviews >= 8 else "attribute_cluster_fallback"
    return SkuRepresentation(
        nm_id=int(sku_record["nm_id"]),
        tokens=[token for token in [title, *attribute_tokens] if token],
        trust_state=trust_state,
        manual_review_required=not bool(title),
    )
