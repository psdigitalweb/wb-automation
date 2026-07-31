from __future__ import annotations

from typing import Any

from app.services.seo.providers import http_client


def test_openrouter_http_client_uses_scoped_proxy(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setenv("OPENROUTER_PROXY_URL", "socks5://host.docker.internal:10880")
    monkeypatch.setattr(http_client.httpx, "Client", fake_client)

    result = http_client.build_openrouter_http_client(timeout_seconds=60.0)

    assert result is sentinel
    assert captured == {
        "timeout": 60.0,
        "proxy": "socks5://host.docker.internal:10880",
    }


def test_openrouter_http_client_stays_direct_without_proxy(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.delenv("OPENROUTER_PROXY_URL", raising=False)
    monkeypatch.setattr(http_client.httpx, "Client", fake_client)

    result = http_client.build_openrouter_http_client(timeout_seconds=30.0)

    assert result is sentinel
    assert captured == {"timeout": 30.0}
