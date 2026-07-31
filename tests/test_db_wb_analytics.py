"""Tests for db_wb_analytics."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.db_wb_analytics import (
    _chunked,
    get_funnel_signals_raw,
    get_wb_nm_ids_for_project,
    upsert_card_stats_daily,
)


def test_chunked():
    """_chunked yields batches of given size."""
    rows = list(range(10))
    batches = list(_chunked(rows, 3))
    assert len(batches) == 4
    assert batches[0] == [0, 1, 2]
    assert batches[1] == [3, 4, 5]
    assert batches[2] == [6, 7, 8]
    assert batches[3] == [9]


def test_get_wb_nm_ids_for_project_no_limit():
    """get_wb_nm_ids returns nm_ids from products."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(101,), (102,)]
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_wb_nm_ids_for_project(project_id=1)
    assert result == [101, 102]


def test_get_wb_nm_ids_for_project_with_limit():
    """get_wb_nm_ids with limit passes LIMIT to query."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(101,)]
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_wb_nm_ids_for_project(project_id=1, limit=100)
    assert result == [101]


def test_get_wb_nm_ids_empty():
    """Empty result returns []."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_wb_nm_ids_for_project(project_id=1)
    assert result == []


def test_card_stats_dual_write_marketplace_product_id():
    conn = MagicMock()
    with patch(
        "app.db_wb_analytics.resolve_marketplace_product_ids",
        return_value={"101": 9001},
    ):
        count = upsert_card_stats_daily(
            conn,
            project_id=1,
            ingest_run_id=7,
            rows=[{"nm_id": 101, "stat_date": date(2026, 7, 31)}],
        )

    sql, params = conn.execute.call_args.args
    assert "marketplace_product_id" in str(sql)
    assert params["marketplace_product_id"] == 9001
    assert count == 1


def test_get_funnel_signals_raw_opens_zero_rates_none():
    """When opens=0, cart_rate and order_rate are None."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (100, 0, 0, 0, 0, None, None, None, None),  # + vendor_code
        ]
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_funnel_signals_raw(
            project_id=1,
            period_from=date(2025, 1, 1),
            period_to=date(2025, 1, 31),
        )
    assert len(result) == 1
    assert result[0]["nm_id"] == 100
    assert result[0]["opens"] == 0
    assert result[0]["cart_rate"] is None
    assert result[0]["order_rate"] is None
    assert result[0]["cart_to_order"] is None
    assert result[0]["avg_check"] is None


def test_get_funnel_signals_raw_carts_zero_cart_to_order_none():
    """When carts=0, cart_to_order is None."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (101, 500, 0, 0, 0, None, None, None, None),  # + vendor_code
        ]
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_funnel_signals_raw(
            project_id=1,
            period_from=date(2025, 1, 1),
            period_to=date(2025, 1, 31),
        )
    assert len(result) == 1
    assert result[0]["carts"] == 0
    assert result[0]["cart_to_order"] is None
    assert result[0]["cart_rate"] == 0.0
    assert result[0]["order_rate"] == 0.0


def test_get_funnel_signals_uses_weighted_ctr_and_quality_filter_sql():
    """CTR must be SUM(clicks)/SUM(impressions), never AVG(reported_ctr)."""
    with patch("app.db_wb_analytics.engine") as mock_engine:
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (101, 500, 10, 2, 1000, None, None, None, None, None, 103, 15, 14.5631, 2, 1),
        ]
        mock_conn.execute.return_value = mock_result
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_conn
        mock_cm.__exit__.return_value = None
        mock_engine.connect.return_value = mock_cm

        result = get_funnel_signals_raw(
            project_id=1,
            period_from=date(2025, 1, 1),
            period_to=date(2025, 1, 31),
            ctr_mode="quality_filtered",
        )

    sql = str(mock_conn.execute.call_args.args[0])
    assert "SUM(card_clicks)" in sql
    assert "SUM(impressions)" in sql
    assert "AVG(reported_ctr)" not in sql
    assert "CLICKS_EXCEED_IMPRESSIONS" in sql
    assert result[0]["funnel_ctr_percent"] == pytest.approx(14.5631)
    assert result[0]["quality_excluded_rows"] == 1
