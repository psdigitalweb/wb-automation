from __future__ import annotations

import asyncio

from app import ingest_prices as ingest_prices_module


class _ScalarResult:
    def scalar_one_or_none(self):
        return None


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=None):
        return _ScalarResult()


class _Engine:
    def connect(self):
        return _Connection()


def test_ingest_prices_reports_rate_limit_as_failure(monkeypatch) -> None:
    class RateLimitedWBClient:
        def __init__(self, token: str) -> None:
            self.last_response_status = None
            self.last_error_text = None

        async def fetch_prices(self, **kwargs):
            self.last_response_status = 429
            self.last_error_text = "rate limited"
            return []

    monkeypatch.setattr(
        "app.utils.get_project_marketplace_token.get_wb_api_token_for_project",
        lambda project_id: "token",
    )
    monkeypatch.setattr(ingest_prices_module, "WBClient", RateLimitedWBClient)
    monkeypatch.setattr(ingest_prices_module, "engine", _Engine())

    result = asyncio.run(ingest_prices_module.ingest_prices(project_id=2, run_id=10))

    assert result == {
        "ok": False,
        "scope": "project",
        "project_id": 2,
        "domain": "prices",
        "reason": "wb_rate_limited",
        "http_status": 429,
        "error": "WB prices API request failed",
        "pages": 1,
        "inserted": 0,
    }
