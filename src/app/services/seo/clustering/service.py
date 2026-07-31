"""[FROZEN iter-1] SKU clustering skeleton with explicit noise-handling placeholders.

See ``app.services.seo.clustering.__init__`` for the deprecation banner.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.services.seo._freeze import guard_frozen_module

guard_frozen_module(__name__)

from app.services.seo.clustering.hdbscan_hook import run_hdbscan_placeholder  # noqa: E402
from app.services.seo.clustering.presegmentation import presegment_skus  # noqa: E402
from app.services.seo.clustering.representation import build_sku_representation  # noqa: E402


def cluster_skus_placeholder(sku_records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a placeholder-safe clustering plan without production logic."""

    segments = presegment_skus(sku_records)
    clusters: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []

    for segment in segments:
        representations = [build_sku_representation(record) for record in segment.sku_records]
        hook_result = run_hdbscan_placeholder(representations)
        other_cluster_key = f"{segment.segment_key}:other"
        clusters.append(
            {
                "cluster_key": other_cluster_key,
                "segment_key": segment.segment_key,
                "is_other": True,
                "is_noise_bucket": True,
                "manual_review_required": True,
            }
        )
        for representation, label in zip(representations, hook_result.cluster_labels):
            assignments.append(
                {
                    "nm_id": representation.nm_id,
                    "cluster_key": other_cluster_key if label == -1 else f"{segment.segment_key}:{label}",
                    "assignment_source": "other_cluster" if label == -1 else "direct_cluster",
                    "manual_review_required": True if label == -1 else representation.manual_review_required,
                    "trust_state": representation.trust_state,
                    "nearest_cluster_fallback": {
                        "status": "todo_placeholder",
                        "reason": "HDBSCAN noise points must be handled explicitly in a later phase",
                    },
                }
            )

    return {
        "status": "placeholder",
        "segments": [{"segment_key": segment.segment_key, "sku_count": len(segment.sku_records)} for segment in segments],
        "clusters": clusters,
        "assignments": assignments,
        "noise_strategy": {
            "nearest_cluster_fallback": "todo_placeholder",
            "other_cluster": "enabled",
            "manual_review_required": True,
        },
    }
