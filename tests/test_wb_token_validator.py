from __future__ import annotations

import asyncio

from app.utils import wb_token_validator


class _FakeResponse:
    def __init__(self, status_code: int, detail: str | None = None) -> None:
        self.status_code = status_code
        self.text = detail or ""

    def json(self):
        if self.text:
            return {"detail": self.text}
        return {}


class _FakeAsyncClient:
    calls: list[dict[str, object]] = []
    statuses: list[int] = []

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, headers: dict[str, str], params=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        status = self.statuses.pop(0)
        detail = None
        if isinstance(status, tuple):
            status, detail = status
        return _FakeResponse(status, detail)


def test_validate_wb_token_uses_prices_bearer_header_first(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.statuses = [200]
    monkeypatch.setattr(wb_token_validator.httpx, "AsyncClient", _FakeAsyncClient)

    ok, error = asyncio.run(wb_token_validator.validate_wb_token("working-token"))

    assert ok is True
    assert error is None
    assert _FakeAsyncClient.calls[0]["headers"] == {"Authorization": "Bearer working-token"}
    assert _FakeAsyncClient.calls[0]["params"] == {"limit": 1, "offset": 0}


def test_validate_wb_token_falls_back_to_warehouses_after_prices_forbidden(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.statuses = [403, 200]
    monkeypatch.setattr(wb_token_validator.httpx, "AsyncClient", _FakeAsyncClient)

    ok, error = asyncio.run(wb_token_validator.validate_wb_token("warehouse-token"))

    assert ok is True
    assert error is None
    assert len(_FakeAsyncClient.calls) == 2
    assert _FakeAsyncClient.calls[0]["params"] == {"limit": 1, "offset": 0}
    assert _FakeAsyncClient.calls[1]["params"] is None


def test_validate_wb_token_accepts_token_value_with_bearer_prefix(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.statuses = [200]
    monkeypatch.setattr(wb_token_validator.httpx, "AsyncClient", _FakeAsyncClient)

    ok, error = asyncio.run(wb_token_validator.validate_wb_token("Bearer saved-token"))

    assert ok is True
    assert error is None
    assert _FakeAsyncClient.calls[0]["headers"] == {"Authorization": "Bearer saved-token"}


def test_validate_wb_token_returns_wb_unauthorized_detail(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.statuses = [
        (401, "access token expired"),
        (401, "access token expired"),
        (401, "access token expired"),
        (401, "access token expired"),
    ]
    monkeypatch.setattr(wb_token_validator.httpx, "AsyncClient", _FakeAsyncClient)

    ok, error = asyncio.run(wb_token_validator.validate_wb_token("expired-token"))

    assert ok is False
    assert error == "Invalid token: Unauthorized (401): access token expired"
