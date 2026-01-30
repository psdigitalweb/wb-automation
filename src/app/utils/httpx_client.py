"""httpx AsyncClient helpers with safe proxy support.

Goals:
- Support both `proxy=` and legacy `proxies=` depending on httpx version.
- Never leak proxy URL/credentials into exception messages we raise/log.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx


def make_async_client(
    *,
    proxy_url: Optional[str],
    timeout: httpx.Timeout,
    limits: Optional[httpx.Limits] = None,
    follow_redirects: bool = False,
    headers: Optional[dict[str, str]] = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    base_kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": follow_redirects,
        **kwargs,
    }
    if limits is not None:
        base_kwargs["limits"] = limits
    if headers is not None:
        base_kwargs["headers"] = headers

    if not proxy_url:
        return httpx.AsyncClient(**base_kwargs)

    # Prefer modern `proxy=` (httpx>=0.23), fallback to `proxies=` if needed.
    try:
        return httpx.AsyncClient(proxy=proxy_url, **base_kwargs)
    except TypeError:
        try:
            return httpx.AsyncClient(proxies=proxy_url, **base_kwargs)
        except TypeError:
            # Do not include proxy_url in exception details.
            raise RuntimeError("httpx proxy configuration failed (proxy enabled)") from None

