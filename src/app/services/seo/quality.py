"""Shared quality-mode framework for the SEO module (iteration 1).

Every decision-carrying row in the SEO pipeline (SKU meaning annotation,
matcher run, generation) stores a ``quality_mode`` and an optional list of
``degraded_reasons``. Those values are produced exclusively by
``infer_quality_mode`` so the logic is testable in one place and consistent
across layers.

See ``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
CD-3, CD-4 and ``05_backend_contract_changes.md`` section 4.

The function is deterministic and pure. Callers build a :class:`QualityState`
describing their current layer plus any upstream modes, and receive a
``(QualityMode, list[QualityReason])`` tuple that they persist on their row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class QualityMode(str, Enum):
    """Quality tier of a SEO decision row.

    Ordering (worst -> best): FALLBACK < DEGRADED < PREVIEW < FULL.
    """

    FULL = "full"
    PREVIEW = "preview"
    DEGRADED = "degraded"
    FALLBACK = "fallback"


_MODE_RANK: Dict[QualityMode, int] = {
    QualityMode.FALLBACK: 0,
    QualityMode.DEGRADED: 1,
    QualityMode.PREVIEW: 2,
    QualityMode.FULL: 3,
}


def _min_mode(a: QualityMode, b: QualityMode) -> QualityMode:
    return a if _MODE_RANK[a] <= _MODE_RANK[b] else b


# Bounded reason-code taxonomy. Callers should use these constants to keep the
# set tight. Any additional fields go under ``detail``.
REASON_EMBEDDING_PREVIEW_USED = "embedding_preview_used"
REASON_EMBEDDING_PROVIDER_MAX_MODE = "embedding_provider_max_mode"
REASON_UPSTREAM_MODE = "upstream_mode_min"
REASON_SKU_DRAFT_FALLBACK = "sku_draft_fallback"
REASON_ATOMS_EXTRACTION_FALLBACK = "atoms_extraction_fallback"
REASON_VISION_ABSENT = "vision_absent"
REASON_REVIEWS_ZERO = "reviews_zero"
REASON_LLM_CACHE_COLD = "llm_cache_cold"
REASON_READINESS_NOT_READY = "readiness_not_ready"


QualityReason = Dict[str, Any]
"""A structured reason entry. Shape: ``{"code": str, "detail": dict | None}``."""


def make_reason(code: str, detail: Optional[Mapping[str, Any]] = None) -> QualityReason:
    """Build a reason dict with a bounded code and optional detail payload."""

    payload: QualityReason = {"code": code}
    if detail:
        payload["detail"] = dict(detail)
    return payload


@dataclass
class QualityState:
    """Input to :func:`infer_quality_mode`.

    Fields are optional. The caller only populates what is relevant for its
    layer, and passes a dict of upstream modes keyed by upstream layer name so
    that the propagation rule (CD-3: layer mode = min(own, upstream)) can be
    applied.
    """

    # Hard ceiling from the embedding provider in use at this layer.
    embedding_provider_max_mode: QualityMode = QualityMode.FULL
    # Modes reported by upstream rows (e.g. {"sku_annotation": FALLBACK}).
    upstream_modes: Dict[str, QualityMode] = field(default_factory=dict)
    # Named evidence signals that are expected to be present. Missing signals
    # drop the layer to DEGRADED.
    evidence_signals: Dict[str, bool] = field(default_factory=dict)
    # Whether this layer took a product-data-only fallback path (forces FALLBACK).
    fallback_taken: bool = False
    # Extra reasons to attach regardless of the computed mode.
    extra_reasons: List[QualityReason] = field(default_factory=list)


def infer_quality_mode(state: QualityState) -> Tuple[QualityMode, List[QualityReason]]:
    """Deterministic quality-mode inference.

    Rules (applied in order):

    1. If ``state.fallback_taken`` is true, the mode is ``FALLBACK``; the
       function still returns any provided ``extra_reasons`` so callers can
       attach context (why we fell back).
    2. Otherwise the layer mode starts at ``FULL``. It is clamped down to the
       provider ceiling, to ``DEGRADED`` if any evidence signal is missing,
       and finally to the minimum of itself and any ``upstream_modes``.
    3. Each clamp appends a reason; duplicates are not de-duplicated because
       upstream context may produce distinct details.
    """

    reasons: List[QualityReason] = list(state.extra_reasons)

    if state.fallback_taken:
        return QualityMode.FALLBACK, reasons

    mode = QualityMode.FULL

    # Provider ceiling (e.g. LocalPreviewEmbeddingProvider forces PREVIEW).
    ceiling = state.embedding_provider_max_mode
    if _MODE_RANK[ceiling] < _MODE_RANK[mode]:
        mode = ceiling
        if ceiling == QualityMode.PREVIEW:
            reasons.append(make_reason(REASON_EMBEDDING_PREVIEW_USED))
        else:
            reasons.append(
                make_reason(
                    REASON_EMBEDDING_PROVIDER_MAX_MODE,
                    {"max_mode": ceiling.value},
                )
            )

    # Missing evidence signals drop us to DEGRADED (unless already lower).
    missing_signals = [name for name, present in state.evidence_signals.items() if not present]
    if missing_signals:
        mode = _min_mode(mode, QualityMode.DEGRADED)
        for name in missing_signals:
            # Emit a canonical reason when we can; fall back to a generic one.
            if name == "vision_present":
                reasons.append(make_reason(REASON_VISION_ABSENT))
            elif name == "reviews_present":
                reasons.append(make_reason(REASON_REVIEWS_ZERO))
            elif name == "llm_cache_warm":
                reasons.append(make_reason(REASON_LLM_CACHE_COLD))
            elif name == "readiness_ready":
                reasons.append(make_reason(REASON_READINESS_NOT_READY))
            else:
                reasons.append(make_reason("evidence_signal_missing", {"signal": name}))

    # Propagate minimum from upstream rows.
    for upstream_name, upstream_mode in state.upstream_modes.items():
        if _MODE_RANK[upstream_mode] < _MODE_RANK[mode]:
            mode = upstream_mode
            reasons.append(
                make_reason(
                    REASON_UPSTREAM_MODE,
                    {"upstream": upstream_name, "upstream_mode": upstream_mode.value},
                )
            )

    return mode, reasons


def coerce_mode(value: Any, *, default: QualityMode = QualityMode.FULL) -> QualityMode:
    """Best-effort coercion of a stored string/enum into a :class:`QualityMode`."""

    if isinstance(value, QualityMode):
        return value
    if value is None:
        return default
    try:
        return QualityMode(str(value).lower())
    except ValueError:
        return default


__all__ = [
    "QualityMode",
    "QualityReason",
    "QualityState",
    "infer_quality_mode",
    "make_reason",
    "coerce_mode",
    "REASON_EMBEDDING_PREVIEW_USED",
    "REASON_EMBEDDING_PROVIDER_MAX_MODE",
    "REASON_UPSTREAM_MODE",
    "REASON_SKU_DRAFT_FALLBACK",
    "REASON_ATOMS_EXTRACTION_FALLBACK",
    "REASON_VISION_ABSENT",
    "REASON_REVIEWS_ZERO",
    "REASON_LLM_CACHE_COLD",
    "REASON_READINESS_NOT_READY",
]
