from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.routers import project_proxy_settings as proxy_router
from app.utils import httpx_client


def _proxy_settings() -> dict:
    return {
        "enabled": True,
        "scheme": "https",
        "host": "proxy.example.test",
        "port": 443,
        "username": "user",
        "password_encrypted": "encrypted",
        "rotate_mode": "fixed",
        "test_url": "https://www.wildberries.ru",
    }


def test_proxy_check_uses_current_storefront_api_and_accepts_wb_rate_limit(monkeypatch) -> None:
    observed: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url: str):
            observed["url"] = url
            return SimpleNamespace(status_code=429)

    def fake_make_async_client(**kwargs):
        observed["client_kwargs"] = kwargs
        return FakeClient()

    monkeypatch.setattr(proxy_router, "get_project_proxy_settings", lambda project_id: _proxy_settings())
    monkeypatch.setattr(proxy_router, "get_project_frontend_brand_ids", lambda project_id: [4058267])
    monkeypatch.setattr(proxy_router, "decrypt_proxy_secret", lambda token: "password")
    monkeypatch.setattr(proxy_router, "make_async_client", fake_make_async_client)
    monkeypatch.setattr(proxy_router, "set_last_test", lambda **kwargs: observed.update(last_test=kwargs))

    result = asyncio.run(
        proxy_router.test_project_proxy_settings_endpoint(
            project_id=3,
            current_user={"id": 1},
            membership={"project_id": 3},
        )
    )

    assert result.ok is True
    assert result.status_code == 429
    assert "/sellers/v4/catalog" in observed["url"]
    assert "supplier=4058267" in observed["url"]
    assert observed["client_kwargs"]["headers"]["Accept"] == "application/json"
    assert observed["last_test"]["ok"] is True


def test_https_proxy_uses_ca_validated_context_without_alias_hostname_check(monkeypatch) -> None:
    observed: dict = {}

    def fake_proxy(url, *, ssl_context):
        observed["url"] = url
        observed["ssl_context"] = ssl_context
        return "proxy-config"

    def fake_client(**kwargs):
        observed["client_kwargs"] = kwargs
        return SimpleNamespace()

    monkeypatch.setattr(httpx_client.httpx, "Proxy", fake_proxy)
    monkeypatch.setattr(httpx_client.httpx, "AsyncClient", fake_client)

    httpx_client.make_async_client(
        proxy_url="https://user:password@proxy.example.test:443",
        timeout=SimpleNamespace(),
    )

    assert observed["client_kwargs"]["proxy"] == "proxy-config"
    assert observed["ssl_context"].check_hostname is False
    assert observed["ssl_context"].verify_mode != 0
