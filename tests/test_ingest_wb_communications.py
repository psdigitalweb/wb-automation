"""Tests for ingest_wb_communications. Mock token, stock, client."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.ingest_wb_communications import _nm_id, ingest_wb_communications


def test_nm_id_safe():
    """_nm_id returns int or None, never raises."""
    assert _nm_id({"productDetails": {"nmId": 123}}) == 123
    assert _nm_id({"productDetails": {"nm_id": 456}}) == 456
    assert _nm_id({"productDetails": {}}) is None
    assert _nm_id({}) is None
    assert _nm_id({"productDetails": {"nmId": "bad"}}) is None


def test_early_exit_no_token():
    """ingest exits with skipped when no token."""
    with patch(
        "app.utils.get_project_marketplace_token.get_wb_token_for_project",
        return_value=None,
    ):
        with patch.dict("os.environ", {"WB_TOKEN": ""}):
            result = asyncio.run(ingest_wb_communications(project_id=1, run_id=1))
    assert result.get("ok") is True
    assert result.get("skipped") is True
    assert result.get("reason") == "no_token"


def test_early_exit_no_stock():
    """ingest exits with skipped when no active nm_ids."""
    with patch("app.utils.get_project_marketplace_token.get_wb_token_for_project", return_value="token"):
        with patch("app.ingest_wb_communications.get_active_fbs_nm_ids", return_value=[]):
            result = asyncio.run(ingest_wb_communications(project_id=1, run_id=1))
    assert result.get("ok") is True
    assert result.get("skipped") is True
    assert result.get("reason") == "no_in_stock_nm_ids"


def test_filtering_logic_unit():
    """_nm_id + active_nm_ids filter: only nm_id in set passes."""
    active = {123}
    items = [
        {"id": "f1", "productDetails": {"nmId": 123}},
        {"id": "f2", "productDetails": {"nmId": 999}},
    ]
    filtered = [x for x in items if _nm_id(x) is not None and _nm_id(x) in active]
    assert len(filtered) == 1
    assert filtered[0]["id"] == "f1"


def test_reviews_backfill_early_exit_no_project_nm_ids():
    """With mode=reviews_backfill and no project nm_ids, ingest skips with reason no_project_nm_ids."""
    with patch("app.utils.get_project_marketplace_token.get_wb_token_for_project", return_value="token"):
        with patch("app.ingest_wb_communications.get_wb_nm_ids_for_project", return_value=[]):
            result = asyncio.run(ingest_wb_communications(
                project_id=1,
                run_id=1,
                params={"mode": "reviews_backfill", "date_from": "2025-01-01", "date_to": "2025-01-02"},
            ))
    assert result.get("ok") is True
    assert result.get("skipped") is True
    assert result.get("reason") == "no_project_nm_ids"


def test_reviews_backfill_missing_date_range():
    """With mode=reviews_backfill and missing date_from/date_to, returns ok=False, reason=missing_date_range."""
    with patch("app.utils.get_project_marketplace_token.get_wb_token_for_project", return_value="token"):
        result = asyncio.run(ingest_wb_communications(
            project_id=1,
            run_id=1,
            params={"mode": "reviews_backfill"},
        ))
    assert result.get("ok") is False
    assert result.get("reason") == "missing_date_range"
