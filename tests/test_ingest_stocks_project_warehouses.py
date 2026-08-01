from __future__ import annotations

import asyncio

from app import ingest_stocks as ingest_stocks_module


def test_ingest_stocks_uses_project_token_and_accepts_empty_fbs_warehouses(monkeypatch) -> None:
    observed: dict[str, str] = {}

    class FakeWBClient:
        def __init__(self, token: str) -> None:
            observed["token"] = token
            self.last_response_status = 200

        async def fetch_warehouses(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(
        ingest_stocks_module,
        "get_wb_api_token_for_project",
        lambda project_id: "project-3-token" if project_id == 3 else None,
    )
    monkeypatch.setattr(ingest_stocks_module, "WBClient", FakeWBClient)
    monkeypatch.setattr(
        ingest_stocks_module.db_products,
        "get_chrt_ids",
        lambda project_id: (_ for _ in ()).throw(AssertionError("products must not be read without FBS warehouses")),
    )

    result = asyncio.run(ingest_stocks_module.ingest_stocks(project_id=3, run_id=42))

    assert observed == {"token": "project-3-token"}
    assert result == {
        "ok": True,
        "scope": "project",
        "project_id": 3,
        "domain": "stocks",
        "reason": "no_fbs_warehouses",
        "warehouses": 0,
        "api_records": 0,
        "inserted": 0,
    }


def test_ingest_stocks_does_not_treat_warehouse_api_error_as_empty_cabinet(monkeypatch) -> None:
    class ForbiddenWBClient:
        def __init__(self, token: str) -> None:
            self.last_response_status = 403

        async def fetch_warehouses(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(ingest_stocks_module, "get_wb_api_token_for_project", lambda project_id: "token")
    monkeypatch.setattr(ingest_stocks_module, "WBClient", ForbiddenWBClient)

    result = asyncio.run(ingest_stocks_module.ingest_stocks(project_id=3))

    assert result == {
        "ok": False,
        "scope": "project",
        "project_id": 3,
        "domain": "stocks",
        "reason": "failed_to_fetch_fbs_warehouses",
        "http_status": 403,
    }


def test_ingest_stocks_accepts_empty_stock_list_for_a_warehouse(monkeypatch) -> None:
    class EmptyMappingResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, statement, params=None):
            return EmptyMappingResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class EmptyStocksWBClient:
        def __init__(self, token: str) -> None:
            self.last_response_status = None
            self.last_error_text = None

        async def fetch_warehouses(self) -> list[dict[str, object]]:
            self.last_response_status = 200
            return [{"id": 123, "name": "Empty warehouse"}]

        async def fetch_stocks(self, warehouse_id: int, chrt_ids: list[int]) -> list[dict[str, object]]:
            self.last_response_status = 200
            self.last_error_text = None
            return []

    monkeypatch.setattr(ingest_stocks_module, "get_wb_api_token_for_project", lambda project_id: "token")
    monkeypatch.setattr(ingest_stocks_module, "WBClient", EmptyStocksWBClient)
    monkeypatch.setattr(ingest_stocks_module.db_products, "get_chrt_ids", lambda project_id: [456])
    monkeypatch.setattr(ingest_stocks_module, "engine", FakeEngine())

    result = asyncio.run(ingest_stocks_module.ingest_stocks(project_id=2))

    assert result == {
        "ok": True,
        "scope": "project",
        "project_id": 2,
        "domain": "stocks",
        "api_records": 0,
        "inserted": 0,
        "failed_chunks": 0,
        "empty_chunks": 1,
    }
