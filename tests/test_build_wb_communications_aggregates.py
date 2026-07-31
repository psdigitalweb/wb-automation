"""Tests for build_wb_communications_daily_aggregates."""
from __future__ import annotations

import pytest

from app.ingest_wb_communications import build_wb_communications_daily_aggregates


@pytest.mark.skipif(
    True,
    reason="Requires DB with wb_feedback_snapshots, wb_question_snapshots; run manually",
)
def test_daily_aggregates_correctness():
    """With test data in snapshots, daily tables have correct aggregates."""
    result = build_wb_communications_daily_aggregates(project_id=1, run_id=1)
    assert result.get("ok") is True
    assert result.get("domain") == "build_wb_communications_aggregates"
