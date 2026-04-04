"""HDBSCAN integration hook placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.seo.clustering.representation import SkuRepresentation


@dataclass(frozen=True)
class HdbscanHookResult:
    """Placeholder result for future HDBSCAN integration."""

    cluster_labels: list[int]
    backend_status: str


def run_hdbscan_placeholder(representations: Sequence[SkuRepresentation]) -> HdbscanHookResult:
    """Return all noise labels until the real backend is implemented."""

    return HdbscanHookResult(cluster_labels=[-1 for _ in representations], backend_status="placeholder_noise_only")
