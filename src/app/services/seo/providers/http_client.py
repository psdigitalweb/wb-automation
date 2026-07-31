"""HTTP client construction for OpenRouter-backed SEO services."""

from __future__ import annotations

import os

import httpx


def build_openrouter_http_client(*, timeout_seconds: float) -> httpx.Client:
    """Return an HTTPX client with the optional OpenRouter-only proxy."""

    proxy_url = os.getenv("OPENROUTER_PROXY_URL", "").strip()
    kwargs: dict[str, object] = {"timeout": timeout_seconds}
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)
