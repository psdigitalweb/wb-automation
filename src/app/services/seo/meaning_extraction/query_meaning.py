"""QueryMeaning formalization layer (Meaning Extraction MVP).

This module is intentionally a thin mapping layer over the existing query pipeline.
It does NOT change query ingestion/pruning/clustering/hybrid/profile extraction logic.

MVP boundary:
- `language_markers -> QueryMeaning.expressive.vibes` is a **proxy mapping**, not a final expressive truth.
- No embeddings, no LLM, no product-side dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.seo.meaning_extraction.types import QueryExpressiveIntent, QueryFunctionalIntent, QueryMeaning
from app.services.seo.query_pipeline.diagnostics import ExtractedClusterProfile, QueryProfileMarker


@dataclass(frozen=True)
class QueryMeaningBuildFlags:
    """Minimal flags for debug exposure (Task 05)."""

    expressive_vibes_are_mvp_proxy: bool = True
    expressive_vibes_source: str = "language_markers"

    def to_dict(self) -> dict[str, Any]:
        return {
            "expressive_vibes_are_mvp_proxy": bool(self.expressive_vibes_are_mvp_proxy),
            "expressive_vibes_source": str(self.expressive_vibes_source),
        }


def _dedupe_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _sort_markers(markers: list[QueryProfileMarker]) -> list[QueryProfileMarker]:
    return sorted(
        markers,
        key=lambda marker: (
            -float(marker.weighted_support or 0.0),
            -int(marker.support_query_count or 0),
            str(marker.normalized_value or marker.value or ""),
        ),
    )


def _marker_values(markers: list[QueryProfileMarker], *, limit: int | None = None) -> list[str]:
    ordered = _sort_markers(markers)
    values = [str(marker.normalized_value or marker.value or "").strip() for marker in ordered]
    deduped = _dedupe_ordered(values)
    if limit is None:
        return deduped
    return deduped[: max(0, int(limit))]


def formalize_query_meaning(
    profile: ExtractedClusterProfile,
    *,
    project_id: int,
    category_id: int,
    product_type_limit: int = 1,
    use_case_limit: int = 10,
    attribute_limit: int = 20,
    vibe_limit: int = 10,
) -> tuple[QueryMeaning, QueryMeaningBuildFlags]:
    """Build canonical QueryMeaning for one extracted cluster profile."""

    product_types = _marker_values(profile.product_type_markers, limit=product_type_limit)
    use_cases = _marker_values(profile.use_case_markers, limit=use_case_limit)
    attributes = _marker_values(profile.attribute_markers, limit=attribute_limit)

    # MVP proxy mapping: language markers are treated as expressive vibes.
    vibes = _marker_values(profile.language_markers, limit=vibe_limit)

    meaning = QueryMeaning(
        project_id=int(project_id),
        category_id=int(category_id),
        cluster_key=str(profile.cluster_key),
        functional=QueryFunctionalIntent(
            product_type=product_types[0] if product_types else None,
            use_cases=use_cases,
            attributes=attributes,
        ).normalized(),
        expressive=QueryExpressiveIntent(vibes=vibes).normalized(),
    ).normalized()

    flags = QueryMeaningBuildFlags()
    return meaning, flags

