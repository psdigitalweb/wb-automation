from __future__ import annotations

import asyncio
from datetime import date

from app import ingest_wb_stock_total_daily as module


class _Result:
    def mappings(self):
        return self

    def one(self):
        return {"rows_written": 37, "products_in_stock": 2, "qty_total": 7}


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params):
        assert params == {"project_id": 2, "snapshot_date": date(2026, 8, 1), "run_id": 42}
        return _Result()


class _Engine:
    def begin(self):
        return _Connection()


def test_build_daily_stock_total_writes_all_catalog_products(monkeypatch) -> None:
    monkeypatch.setattr(module, "engine", _Engine())

    result = asyncio.run(
        module.build_wb_stock_total_daily(
            project_id=2,
            run_id=42,
            params={"snapshot_date": "2026-08-01"},
        )
    )

    assert result == {
        "ok": True,
        "scope": "project",
        "project_id": 2,
        "domain": "wb_stock_total_daily",
        "snapshot_date": "2026-08-01",
        "rows_written": 37,
        "products_in_stock": 2,
        "qty_total": 7,
    }
