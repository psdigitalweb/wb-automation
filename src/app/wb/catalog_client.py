"""Lightweight HTTP client for Wildberries public catalog API (catalog.wb.ru).

This client fetches public catalog data without authentication.
Used for scraping frontend prices for comparison/validation.
"""

import asyncio
import random
import httpx
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app import settings
from app.utils.httpx_client import make_async_client


class CatalogClient:
    """Client for WB public catalog API."""
    
    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        proxy_scheme: str | None = None,
        http_min_retries: Optional[int] = None,
        http_timeout_jitter_sec: Optional[Union[int, float]] = None,
    ):
        base_timeout = getattr(settings, "FRONTEND_PRICES_HTTP_TIMEOUT", 30)
        # With proxy, latency is higher; use at least 60s to reduce ReadTimeout.
        self.timeout = max(base_timeout, 60) if proxy_url else base_timeout
        # With rotating proxy: each attempt can use a new IP. Prefer UI/project setting over env.
        if proxy_url and http_min_retries is not None:
            self.max_retries = max(3, int(http_min_retries))
        else:
            min_retries = getattr(settings, "FRONTEND_PRICES_HTTP_MIN_RETRIES", 10)
            self.max_retries = max(3, min_retries) if proxy_url else 3
        self.retry_delay = 1.0
        if http_timeout_jitter_sec is not None:
            self.timeout_jitter = float(http_timeout_jitter_sec)
        else:
            self.timeout_jitter = getattr(settings, "FRONTEND_PRICES_HTTP_TIMEOUT_JITTER", 10)
        self.last_request_meta: Dict[str, Any] = {}
        self.proxy_url: str | None = proxy_url
        if proxy_scheme is not None and str(proxy_scheme).strip():
            self.proxy_scheme: str | None = str(proxy_scheme).strip().lower()
        else:
            self.proxy_scheme = None
            if proxy_url:
                try:
                    self.proxy_scheme = urlparse(str(proxy_url)).scheme or None
                except Exception:
                    self.proxy_scheme = None
        
        # Headers as in Apps Script / browser DevTools
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.wildberries.ru/",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _proxy_meta(self) -> Dict[str, Any]:
        used = bool(self.proxy_url)
        return {
            "proxy_used": used,
            "proxy_scheme": (self.proxy_scheme if used else None),
        }
    
    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs
    ) -> Optional[httpx.Response]:
        """Make HTTP request with retries and exponential backoff.
        
        Retries on:
        - 429 (rate limit) - with longer backoff
        - 5xx (server errors)
        - Network exceptions
        """
        print(f"catalog_client._request_with_retry: starting, method={method}, url={url[:100]}")
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(self.max_retries):
            try:
                # Per-attempt timeout with jitter so we don't kill requests too early (proxy/rotating IP).
                timeout_this = float(self.timeout) + random.uniform(0, float(self.timeout_jitter))
                print(
                    f"catalog_client._request_with_retry: attempt {attempt + 1}/{self.max_retries} "
                    f"timeout={timeout_this:.1f}s"
                )
                response = await asyncio.wait_for(
                    client.request(method, url, **kwargs),
                    timeout=timeout_this,
                )
                last_status = response.status_code if response else None
                last_error = None
                print(f"catalog_client._request_with_retry: status={last_status}")
                self.last_request_meta = {
                    **self._proxy_meta(),
                    "ok": True,
                    "status_code": last_status,
                    "attempt": attempt + 1,
                }
                
                # Handle 429 rate limit with longer backoff
                if response.status_code == 429:
                    # Do not sleep/retry here: the caller should apply heartbeat-aware backoff
                    # to avoid "running forever" and to keep ingest_runs heartbeat/stats updated.
                    print(
                        f"catalog_client: HTTP 429 Too Many Requests; returning to caller "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    return response
                
                # Don't retry on other 4xx errors
                if response.status_code < 500:
                    return response
                
                # Retry on 5xx errors
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt) * (0.8 + 0.4 * random.random())
                    print(
                        f"catalog_client: HTTP {response.status_code}; next_step=sleep; sleep_s={delay:.1f}; "
                        f"attempt={attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(delay)
            except Exception as e:
                last_error = type(e).__name__
                self.last_request_meta = {
                    **self._proxy_meta(),
                    "ok": False,
                    "status_code": last_status,
                    "error": last_error,
                    "attempt": attempt + 1,
                }
                if attempt < self.max_retries - 1:
                    # Connection problems are common here; be more patient to improve completeness.
                    delay = min(10 * (attempt + 1), 60) * (0.8 + 0.4 * random.random())  # 10s, 20s, ... capped 60s + jitter
                    print(
                        f"catalog_client: exception={type(e).__name__}; next_step=sleep; sleep_s={delay:.1f}; "
                        f"attempt={attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(
                        f"catalog_client: failed after {self.max_retries} attempts; "
                        f"last_status={last_status}; last_error={last_error}"
                    )
                    return None
        return None
    
    def _replace_page_in_url(self, url: str, page: int) -> str:
        """Replace or add page parameter in URL."""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params['page'] = [str(page)]
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    
    async def fetch_brand_catalog_page(
        self,
        brand_id: int,
        page: int,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> Dict[str, Any]:
        """Fetch a single page from WB catalog API.
        
        Args:
            brand_id: Brand ID (for logging)
            page: Page number (1-based)
            base_url: Full URL with page=1, will be replaced with actual page
        
        Returns:
            Parsed JSON response. Empty dict if error.
        """
        url = self._replace_page_in_url(base_url, page)
        self.last_request_meta = {**self._proxy_meta(), "page": page}
        
        print(f"catalog_client: URL={url}")
        print(f"catalog_client: method=GET, brand_id={brand_id}, page={page}")

        async def _handle_with_client(http_client: httpx.AsyncClient) -> Dict[str, Any]:
            try:
                r = await self._request_with_retry(
                    http_client, "GET", url, headers=self.headers
                )

                if not r:
                    print("catalog_client: request returned None (no response)")
                    self.last_request_meta = {
                        **(self.last_request_meta or {}),
                        "ok": False,
                        "status_code": None,
                        "result": "no_response",
                    }
                    return {}

                print(f"catalog_client: HTTP status={r.status_code}")

                if r.status_code == 200:
                    try:
                        data = r.json()
                        self.last_request_meta = {
                            **(self.last_request_meta or {}),
                            "ok": True,
                            "status_code": 200,
                            "result": "ok",
                        }
                        return data
                    except Exception as e:
                        print(f"catalog_client: JSON parse error: {type(e).__name__}: {e}")
                        self.last_request_meta = {
                            **(self.last_request_meta or {}),
                            "ok": False,
                            "status_code": 200,
                            "result": "json_parse_error",
                            "error": type(e).__name__,
                        }
                        return {}
                elif r.status_code == 429:
                    print("catalog_client: HTTP 429 Too Many Requests - rate limit exceeded, need backoff")
                    self.last_request_meta = {
                        **(self.last_request_meta or {}),
                        "ok": False,
                        "status_code": 429,
                        "result": "rate_limited",
                    }
                    return {}
                elif r.status_code >= 500:
                    print(f"catalog_client: HTTP {r.status_code} server error - will retry")
                    self.last_request_meta = {
                        **(self.last_request_meta or {}),
                        "ok": False,
                        "status_code": int(r.status_code),
                        "result": "server_error",
                    }
                    return {}
                else:
                    print(f"catalog_client: HTTP {r.status_code} error")
                    self.last_request_meta = {
                        **(self.last_request_meta or {}),
                        "ok": False,
                        "status_code": int(r.status_code),
                        "result": "http_error",
                    }
                    return {}
            except Exception as e:
                # Do not print exception message here: it may contain proxy URL/credentials (httpx ProxyError, etc.)
                print(f"catalog_client: exception during request: {type(e).__name__}")
                self.last_request_meta = {
                    **(self.last_request_meta or {}),
                    "ok": False,
                    "status_code": None,
                    "result": "exception",
                    "error": type(e).__name__,
                }
                return {}

        # Prefer reusing a shared AsyncClient (connection pooling / keep-alive).
        if client is not None:
            return await _handle_with_client(client)

        print(f"catalog_client: creating AsyncClient, timeout={self.timeout}")
        timeout_cfg = httpx.Timeout(
            float(self.timeout),
            # Connect timeouts were the main failure mode; keep it same as overall timeout.
            connect=float(self.timeout),
            read=float(self.timeout),
            write=float(self.timeout),
            pool=float(self.timeout),
        )
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0)
        async with make_async_client(proxy_url=self.proxy_url, timeout=timeout_cfg, limits=limits) as http_client:
            return await _handle_with_client(http_client)

