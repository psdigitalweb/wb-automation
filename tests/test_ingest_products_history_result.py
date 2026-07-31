from __future__ import annotations

import asyncio

from app.ingest_products import _to_row, fetch_page
from app.services.ingest import registry


def test_wrap_ingest_products_preserves_history_stats(monkeypatch):
    async def fake_ingest(project_id: int, loop_delay_s: float, run_id: int):
        return {
            "ok": True,
            "cards_seen": 10,
            "cards_changed": 2,
            "versions_created": 2,
        }

    monkeypatch.setattr(registry, "_ingest_products", fake_ingest)
    monkeypatch.setattr(
        "app.services.ingest.runs.has_active_run",
        lambda **kwargs: True,
    )

    class _Result:
        def scalar(self):
            return 0

    class _Connection:
        def execute(self, *args, **kwargs):
            return _Result()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class _Engine:
        def connect(self):
            return _Connection()

    monkeypatch.setattr("app.db.engine", _Engine())

    result = asyncio.run(registry._wrap_ingest_products(project_id=1, run_id=22))

    assert result["ok"] is True
    assert result["cards_seen"] == 10
    assert result["cards_changed"] == 2
    assert result["versions_created"] == 2
    assert "finished_at" in result


def test_product_mapper_preserves_sizes_and_raw_payload():
    row = _to_row(
        {
            "nmID": 123,
            "title": "Товар",
            "sizes": [{"chrtID": 7, "techSize": "M", "skus": ["123456789"]}],
            "photos": [{"big": "https://basket-01.wbbasket.ru/main.jpg"}],
            "updatedAt": "2026-07-27T12:00:00Z",
        }
    )

    assert '"chrtID": 7' in row["sizes"]
    assert '"updatedAt": "2026-07-27T12:00:00Z"' in row["raw"]


def test_mock_fetch_page_always_returns_cursor_total_tuple():
    class _Client:
        headers = {"Authorization": "MOCK"}

    items, cursor, cursor_total = asyncio.run(
        fetch_page(_Client(), "https://example.invalid", None, 2)
    )

    assert len(items) == 2
    assert cursor == "mock_page_1"
    assert cursor_total == 2
