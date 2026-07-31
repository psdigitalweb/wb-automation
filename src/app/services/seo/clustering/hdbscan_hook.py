"""[FROZEN iter-1] HDBSCAN integration hook placeholder.

See ``app.services.seo.clustering.__init__`` for the deprecation banner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.seo._freeze import guard_frozen_module

guard_frozen_module(__name__)

from app.services.seo.clustering.representation import SkuRepresentation  # noqa: E402


@dataclass(frozen=True)
class HdbscanHookResult:
    """Placeholder result for future HDBSCAN integration."""

    cluster_labels: list[int]
    backend_status: str


def run_hdbscan_placeholder(representations: Sequence[SkuRepresentation]) -> HdbscanHookResult:
    """Return all noise labels until the real backend is implemented."""

    return HdbscanHookResult(cluster_labels=[-1 for _ in representations], backend_status="placeholder_noise_only")
