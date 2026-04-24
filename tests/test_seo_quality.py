"""Unit tests for ``services.seo.quality.infer_quality_mode``."""

from __future__ import annotations

from app.services.seo.quality import (
    REASON_EMBEDDING_PREVIEW_USED,
    REASON_UPSTREAM_MODE,
    REASON_VISION_ABSENT,
    QualityMode,
    QualityState,
    infer_quality_mode,
    make_reason,
)


def _reason_codes(reasons):
    return [r["code"] for r in reasons]


def test_full_mode_when_all_signals_healthy():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.FULL,
        evidence_signals={"vision_present": True, "reviews_present": True},
    )
    mode, reasons = infer_quality_mode(state)
    assert mode == QualityMode.FULL
    assert reasons == []


def test_preview_ceiling_enforced_by_provider():
    state = QualityState(embedding_provider_max_mode=QualityMode.PREVIEW)
    mode, reasons = infer_quality_mode(state)
    assert mode == QualityMode.PREVIEW
    assert REASON_EMBEDDING_PREVIEW_USED in _reason_codes(reasons)


def test_missing_evidence_signal_downgrades_to_degraded():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.FULL,
        evidence_signals={"vision_present": False, "reviews_present": True},
    )
    mode, reasons = infer_quality_mode(state)
    assert mode == QualityMode.DEGRADED
    assert REASON_VISION_ABSENT in _reason_codes(reasons)


def test_fallback_overrides_everything():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.FULL,
        evidence_signals={"vision_present": True},
        fallback_taken=True,
        extra_reasons=[make_reason("sku_draft_fallback")],
    )
    mode, reasons = infer_quality_mode(state)
    assert mode == QualityMode.FALLBACK
    assert _reason_codes(reasons) == ["sku_draft_fallback"]


def test_upstream_mode_propagates_as_floor():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.FULL,
        upstream_modes={"sku_annotation": QualityMode.FALLBACK},
    )
    mode, reasons = infer_quality_mode(state)
    assert mode == QualityMode.FALLBACK
    codes = _reason_codes(reasons)
    assert REASON_UPSTREAM_MODE in codes
    detail = next(r["detail"] for r in reasons if r["code"] == REASON_UPSTREAM_MODE)
    assert detail["upstream"] == "sku_annotation"
    assert detail["upstream_mode"] == "fallback"


def test_upstream_better_than_layer_does_not_affect_layer_mode():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.PREVIEW,
        upstream_modes={"sku_annotation": QualityMode.FULL},
    )
    mode, _ = infer_quality_mode(state)
    assert mode == QualityMode.PREVIEW


def test_combined_preview_ceiling_and_missing_evidence_yields_min():
    state = QualityState(
        embedding_provider_max_mode=QualityMode.PREVIEW,
        evidence_signals={"reviews_present": False},
    )
    mode, reasons = infer_quality_mode(state)
    # DEGRADED is worse than PREVIEW, so we land on DEGRADED.
    assert mode == QualityMode.DEGRADED
    codes = _reason_codes(reasons)
    assert REASON_EMBEDDING_PREVIEW_USED in codes
    assert "reviews_zero" in codes
