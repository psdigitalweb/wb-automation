from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app import ingest_supplier_stocks as ingest_module
from app.ingest_wb_analytics import _analytics_http_error_reason
from app.wb.client import WBClient


def test_fbo_client_uses_current_analytics_endpoint_and_preserves_http_error(monkeypatch) -> None:
    observed: dict[str, Any] = {}

    async def fake_request(self, client, method, url, **kwargs):
        observed.update({"method": method, "url": url, "json": kwargs.get("json")})
        return httpx.Response(403, json={"detail": "access denied"}, request=httpx.Request(method, url))

    monkeypatch.setattr(WBClient, "_request_with_retry", fake_request)
    client = WBClient("token")

    rows = asyncio.run(client.fetch_fbo_stocks_page(limit=100, offset=20))

    assert rows == []
    assert client.last_response_status == 403
    assert "access denied" in (client.last_error_text or "")
    assert observed == {
        "method": "POST",
        "url": "https://seller-analytics-api.wildberries.ru/api/analytics/v1/stocks-report/wb-warehouses",
        "json": {"nmIds": [], "chrtIds": [], "limit": 100, "offset": 20},
    }


def test_ingest_fbo_aggregates_sizes_and_saves_one_snapshot(monkeypatch) -> None:
    inserted_rows: list[dict[str, Any]] = []

    class FakeWBClient:
        def __init__(self, token: str) -> None:
            assert token == "project-token"
            self.last_response_status = 200
            self.last_error_text = None

        async def fetch_fbo_stocks_page(self, *, limit: int, offset: int):
            assert offset == 0
            return [
                {
                    "nmId": 101,
                    "chrtId": 1001,
                    "warehouseId": 7,
                    "warehouseName": "Коледино",
                    "regionName": "Центральный",
                    "quantity": 3,
                    "inWayToClient": 1,
                    "inWayFromClient": 0,
                },
                {
                    "nmId": 101,
                    "chrtId": 1002,
                    "warehouseId": 7,
                    "warehouseName": "Коледино",
                    "regionName": "Центральный",
                    "quantity": 4,
                    "inWayToClient": 2,
                    "inWayFromClient": 1,
                },
                {
                    "nmId": 202,
                    "chrtId": 2001,
                    "warehouseId": 8,
                    "warehouseName": "Казань",
                    "regionName": "Приволжский",
                    "quantity": 5,
                    "inWayToClient": 0,
                    "inWayFromClient": 0,
                },
            ]

    class FakeResult:
        rowcount = 2

    class FakeConnection:
        def execute(self, statement, rows):
            inserted_rows.extend(rows)
            return FakeResult()

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(ingest_module, "get_wb_api_token_for_project", lambda project_id: "project-token")
    monkeypatch.setattr(ingest_module, "WBClient", FakeWBClient)
    monkeypatch.setattr(ingest_module, "engine", FakeEngine())
    monkeypatch.setattr(
        ingest_module,
        "resolve_marketplace_product_ids",
        lambda **kwargs: {"101": 501, "202": 502},
    )

    result = asyncio.run(ingest_module.ingest_supplier_stocks(project_id=3, run_id=42))

    assert result["ok"] is True
    assert result["source"] == "wb_analytics"
    assert result["api_records"] == 3
    assert result["snapshot_rows"] == 2
    assert result["inserted"] == 2
    assert len(inserted_rows) == 2
    first = next(row for row in inserted_rows if row["nm_id"] == 101)
    assert first["quantity"] == 7
    assert first["in_way_to_client"] == 3
    assert first["in_way_from_client"] == 1
    assert first["marketplace_product_id"] == 501
    assert first["snapshot_at"] == first["last_change_date"]


def test_ingest_fbo_reports_api_failure_instead_of_success(monkeypatch) -> None:
    class ForbiddenWBClient:
        def __init__(self, token: str) -> None:
            self.last_response_status = 403
            self.last_error_text = "access denied"

        async def fetch_fbo_stocks_page(self, *, limit: int, offset: int):
            return []

    monkeypatch.setattr(ingest_module, "get_wb_api_token_for_project", lambda project_id: "token")
    monkeypatch.setattr(ingest_module, "WBClient", ForbiddenWBClient)

    result = asyncio.run(ingest_module.ingest_supplier_stocks(project_id=3))

    assert result == {
        "ok": False,
        "scope": "project",
        "project_id": 3,
        "domain": "supplier_stocks",
        "reason": "failed_to_fetch_fbo_stocks",
        "http_status": 403,
        "pages": 0,
        "api_records": 0,
    }


def test_analytics_rate_limit_has_a_specific_reason() -> None:
    assert _analytics_http_error_reason(429) == "wb_analytics_rate_limited"
    assert _analytics_http_error_reason(400) == "wb_analytics_bad_request"
