from __future__ import annotations

import asyncio

from app.services.ingest import registry


def test_wrap_ingest_prices_preserves_failure_result(monkeypatch):
    async def fake_ingest_prices(project_id: int, run_id: int):
        return {
            "ok": False,
            "scope": "project",
            "project_id": project_id,
            "domain": "prices",
            "reason": "wb_token_unauthorized",
            "http_status": 401,
        }

    monkeypatch.setattr(registry, "_ingest_prices", fake_ingest_prices)

    result = asyncio.run(registry._wrap_ingest_prices(project_id=1, run_id=10))

    assert result["ok"] is False
    assert result["reason"] == "wb_token_unauthorized"
    assert result["http_status"] == 401
    assert "finished_at" in result


def test_frontend_prices_recognizes_rate_limited_admin_price_refresh():
    result = {
        "status": "failed",
        "detail": "wb_rate_limited",
        "stats": {"reason": "wb_rate_limited"},
    }

    assert registry._prices_refresh_failure_reason(result) == "wb_rate_limited"
