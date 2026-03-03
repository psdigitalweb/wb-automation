"""Tests for ingest_wb_analytics. Mock token, DB, client."""
from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock

from app.ingest_wb_analytics import (
    _parse_funnel_item,
    _parse_sales_funnel_products_item,
    _rows_from_products_chunk,
    _build_extra,
    _extract_search_text,
    _cursor_for_json,
    ingest_wb_card_stats_daily,
    ingest_wb_search_queries_daily,
)


def test_parse_sales_funnel_products_item():
    """_parse_sales_funnel_products_item maps sales-funnel/products API to one row."""
    item = {
        "product": {"nmId": 456, "title": "Test", "stocks": {"wb": 10, "mp": 5}},
        "statistic": {
            "selected": {
                "period": {"start": "2025-02-01", "end": "2025-02-01"},
                "openCount": 10,
                "cartCount": 5,
                "orderCount": 2,
                "orderSum": 500,
                "buyoutCount": 2,
                "buyoutSum": 500,
                "buyoutPercent": 40,
                "addToWishlist": 20,
                "cancelCount": 0,
                "cancelSum": 0,
                "avgPrice": 250,
                "conversions": {"addToCartPercent": 50, "cartToOrderPercent": 40, "buyoutPercent": 40},
            }
        },
    }
    row = _parse_sales_funnel_products_item(item, "RUB", date(2025, 2, 1))
    assert row["nm_id"] == 456
    assert row["stat_date"] == date(2025, 2, 1)
    assert row["currency"] == "RUB"
    assert row["open_count"] == 10
    assert row["cart_count"] == 5
    assert row["order_count"] == 2
    assert row["order_sum"] == 500
    assert row["add_to_wishlist_count"] == 20
    assert row["add_to_cart_conversion"] == 50
    assert row["cart_to_order_conversion"] == 40
    assert row["buyout_percent"] == 40
    assert row["extra"].get("cancelCount") == 0
    assert row["extra"].get("avgPrice") == 250
    assert row["extra"].get("stocks") == {"wb": 10, "mp": 5}


def test_rows_from_products_chunk_zero_fill():
    """_rows_from_products_chunk adds zero rows for requested nm_ids not in response."""
    products = [
        {
            "product": {"nmId": 1},
            "statistic": {"selected": {"openCount": 1, "cartCount": 0, "orderCount": 0, "orderSum": 0, "buyoutCount": 0, "buyoutSum": 0, "addToWishlist": 0, "conversions": {}}},
        },
    ]
    requested = [1, 2, 3]
    stat_date = date(2025, 2, 1)
    rows = _rows_from_products_chunk(products, requested, stat_date, "RUB")
    assert len(rows) == 3
    nm_ids = {r["nm_id"] for r in rows}
    assert nm_ids == {1, 2, 3}
    row_1 = next(r for r in rows if r["nm_id"] == 1)
    assert row_1["open_count"] == 1
    row_2 = next(r for r in rows if r["nm_id"] == 2)
    assert row_2["open_count"] == 0
    assert row_2["order_sum"] == 0


def test_parse_funnel_item():
    """_parse_funnel_item maps API fields to rows."""
    item = {
        "product": {"nmId": 123},
        "history": [
            {
                "date": "2024-10-23",
                "openCount": 45,
                "cartCount": 34,
                "orderCount": 19,
                "orderSum": 1262,
                "buyoutCount": 19,
                "buyoutSum": 1262,
                "buyoutPercent": 35,
                "addToCartConversion": 43,
                "cartToOrderConversion": 0,
                "addToWishlistCount": 10,
            }
        ],
        "currency": "RUB",
    }
    rows = _parse_funnel_item(item, 123, "RUB")
    assert len(rows) == 1
    r = rows[0]
    assert r["nm_id"] == 123
    assert r["stat_date"].isoformat() == "2024-10-23"
    assert r["currency"] == "RUB"
    assert r["open_count"] == 45
    assert r["cart_count"] == 34
    assert r["order_count"] == 19
    assert r["order_sum"] == 1262
    assert r["add_to_wishlist_count"] == 10


def test_extract_search_text():
    """_extract_search_text returns searchText or text."""
    assert _extract_search_text({"searchText": "foo"}) == "foo"
    assert _extract_search_text({"text": "bar"}) == "bar"
    assert _extract_search_text({}) is None
    assert _extract_search_text({"other": "x"}) is None


def test_build_extra_funnel():
    """extra contains only unknown keys."""
    obj = {"openCount": 1, "unknownField": 2}
    known = {"openCount"}
    extra = _build_extra(obj, known)
    assert extra == {"unknownField": 2}


def test_cursor_for_json_serializable():
    """_cursor_for_json returns JSON-serializable cursor (date -> ISO string) for set_run_progress."""
    from datetime import date as date_type
    # Cursor with date object (as after _parse_params) must serialize
    c = {"date": date_type(2026, 2, 23), "nm_offset": 920}
    out = _cursor_for_json(c)
    assert out == {"date": "2026-02-23", "nm_offset": 920}
    json.dumps(out)
    # None cursor
    assert _cursor_for_json(None) is None
    # String date is kept as string
    out2 = _cursor_for_json({"date": "2026-02-24", "nm_offset": 0})
    assert out2["date"] == "2026-02-24"
    json.dumps(out2)


def test_ingest_card_stats_no_token():
    """ingest exits when no analytics token."""
    with patch(
        "app.ingest_wb_analytics.get_wb_analytics_token_for_project",
        return_value=None,
    ):
        result = asyncio.run(ingest_wb_card_stats_daily(project_id=1, run_id=1))
    assert result.get("ok") is False
    assert result.get("reason") == "no_analytics_token"


def test_ingest_card_stats_no_nm_ids():
    """ingest succeeds with 0 rows when project has no known nm_ids."""
    with patch(
        "app.ingest_wb_analytics.get_wb_analytics_token_for_project",
        return_value="token",
    ):
        with patch(
            "app.ingest_wb_analytics.get_wb_nm_ids_for_project",
            return_value=[],
        ):
            result = asyncio.run(ingest_wb_card_stats_daily(project_id=1, run_id=1))
    assert result.get("ok") is True
    assert result.get("rows_upserted") == 0
    assert result.get("reason") == "no_nm_ids"


def test_ingest_card_stats_daily_uses_all_known_nm_ids():
    """Daily mode must use all known project nm_ids, not current active stock."""
    with patch(
        "app.ingest_wb_analytics.get_wb_analytics_token_for_project",
        return_value="token",
    ):
        with patch(
            "app.ingest_wb_analytics.get_wb_nm_ids_for_project",
            return_value=[101, 202],
        ) as get_nm_ids:
            with patch("app.ingest_wb_analytics.WBAnalyticsClient") as client_cls:
                with patch("app.ingest_wb_analytics.engine.begin", return_value=nullcontext(MagicMock())):
                    with patch("app.ingest_wb_analytics.upsert_card_stats_daily", return_value=0):
                        client = MagicMock()
                        client.get_sales_funnel_history = AsyncMock(return_value=[])
                        client_cls.return_value = client
                        result = asyncio.run(ingest_wb_card_stats_daily(project_id=1, run_id=1))

    assert result.get("ok") is True
    assert result.get("nm_ids_total") == 2
    assert result.get("rows_upserted") == 0
    get_nm_ids.assert_called_once_with(1)


def test_ingest_search_no_token():
    """Search ingest exits when no analytics token."""
    with patch(
        "app.ingest_wb_analytics.get_wb_analytics_token_for_project",
        return_value=None,
    ):
        result = asyncio.run(ingest_wb_search_queries_daily(project_id=1, run_id=1))
    assert result.get("ok") is False
    assert result.get("reason") == "no_analytics_token"


def test_ingest_search_no_nm_ids():
    """Search ingest succeeds with 0 when no nm_ids."""
    with patch(
        "app.ingest_wb_analytics.get_wb_analytics_token_for_project",
        return_value="token",
    ):
        with patch(
            "app.ingest_wb_analytics.get_wb_nm_ids_for_project",
            return_value=[],
        ):
            result = asyncio.run(ingest_wb_search_queries_daily(project_id=1, run_id=1))
    assert result.get("ok") is True
    assert result.get("terms_upserted") == 0
    assert result.get("daily_upserted") == 0
