"""WB Analytics API client (sales funnel, search-report).

Base URL: https://seller-analytics-api.wildberries.ru
Auth: HeaderApiKey — имя заголовка из swagger securitySchemes.HeaderApiKey.name.
      По умолчанию "Authorization", значение — raw token (без Bearer).
Rate limit: 3 req/min, interval 20s.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app import settings

logger = logging.getLogger(__name__)


class WBAnalyticsUnauthorizedError(Exception):
    """401/403 from WB Analytics API: unauthorized or forbidden."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail or f"WB Analytics API: {'unauthorized' if status_code == 401 else 'forbidden'}"
        super().__init__(self.detail)


class WBAnalyticsBadRequestError(Exception):
    """4xx (e.g. 400) from WB Analytics API: bad request with status and response body."""

    def __init__(self, status_code: int, detail: str, request_summary: Dict[str, Any]):
        self.status_code = status_code
        self.detail = detail
        self.request_summary = request_summary
        super().__init__(f"WB Analytics API: {status_code} {detail[:200]}")


class WBAnalyticsNetworkError(Exception):
    """Network/transport error after retries (ConnectTimeout, ReadTimeout, ConnectError, RemoteProtocolError)."""

    def __init__(self, message: str, request_context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.request_context = request_context or {}
        super().__init__(message)


# Header name from swagger HeaderApiKey.name — verify against swagger at impl time
WB_ANALYTICS_HEADER_NAME = "Authorization"

# Network errors we retry with backoff (3 attempts: 1s, 3s, 7s + jitter)
NETWORK_RETRIES = 3
NETWORK_BACKOFF_SEC = [1.0, 3.0, 7.0]
NETWORK_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


class WBAnalyticsClient:
    """Client for WB Analytics API (sales funnel, search-report)."""

    def __init__(
        self,
        token: str,
        semaphore: Optional[asyncio.Semaphore] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize client.

        Args:
            token: WB Analytics API token (raw, no Bearer).
            semaphore: Optional Semaphore(1) for serializing requests within a job.
                      If None, creates one internally.
            base_url: Override base URL (default from settings).
        """
        self.token = token
        self.base_url = base_url or settings.WB_ANALYTICS_BASE_URL
        self._semaphore = semaphore or asyncio.Semaphore(1)
        # Connect 30s to tolerate slow WB; read from settings (e.g. 60s).
        self._timeout = httpx.Timeout(
            connect=30.0,
            read=float(settings.WB_ANALYTICS_TIMEOUT_SEC),
            write=10.0,
            pool=10.0,
        )
        self.max_retries = settings.WB_ANALYTICS_MAX_RETRIES
        self._request_interval_sec = settings.WB_ANALYTICS_REQUEST_INTERVAL_SEC
        self._last_request_at: float = 0

    def _build_headers(self) -> Dict[str, str]:
        """HeaderApiKey: raw token in Authorization (no Bearer)."""
        return {
            WB_ANALYTICS_HEADER_NAME: self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        } if self.token else {}

    async def _throttle(self) -> None:
        """Min interval between requests (rate limit)."""
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self._request_interval_sec:
            await asyncio.sleep(self._request_interval_sec - elapsed)
        self._last_request_at = time.monotonic()

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Make request with semaphore, throttle, retry on network (3x backoff), then on 429/5xx."""
        async with self._semaphore:
            await self._throttle()
            url = f"{self.base_url}{path}"
            headers = self._build_headers()
            selected_period = None
            if json_body and isinstance(json_body.get("selectedPeriod"), dict):
                selected_period = json_body["selectedPeriod"]

            for attempt in range(self.max_retries):
                response = None
                for net_attempt in range(NETWORK_RETRIES):
                    try:
                        response = await client.request(
                            method,
                            url,
                            json=json_body,
                            headers=headers,
                            timeout=self._timeout,
                        )
                        break
                    except NETWORK_EXCEPTIONS as e:
                        logger.warning(
                            "WB Analytics network attempt %s/%s failed: exc=%s path=%s timeout_connect=%s timeout_read=%s selectedPeriod=%s",
                            net_attempt + 1,
                            NETWORK_RETRIES,
                            type(e).__name__,
                            path,
                            self._timeout.connect,
                            self._timeout.read,
                            selected_period,
                        )
                        if net_attempt >= NETWORK_RETRIES - 1:
                            raise WBAnalyticsNetworkError(
                                str(e) or type(e).__name__,
                                request_context={"path": path, "selectedPeriod": selected_period},
                            ) from e
                        delay = NETWORK_BACKOFF_SEC[net_attempt] + random.uniform(0, 0.3)
                        await asyncio.sleep(delay)

                if response is None:
                    continue
                status = response.status_code

                if status in (401, 403):
                    raise WBAnalyticsUnauthorizedError(status, response.text[:500])

                if status == 429:
                    retry_after = response.headers.get("Retry-After")
                    if attempt < self.max_retries - 1:
                        delay_default = [1.0, 2.0, 4.0][min(attempt, 2)]
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except (TypeError, ValueError):
                                delay = delay_default
                        else:
                            delay = delay_default
                        await asyncio.sleep(delay)
                        continue
                    return response

                if status < 500:
                    return response

                if attempt < self.max_retries - 1:
                    delay = 1.0 * (2**attempt)
                    await asyncio.sleep(delay)
            return response

    async def get_sales_funnel_history(
        self,
        nm_ids: List[int],
        date_from: str,
        date_to: str,
        aggregation_level: str = "day",
        skip_deleted_nm: bool = True,
    ) -> List[Dict[str, Any]]:
        """POST /api/analytics/v3/sales-funnel/products/history.

        Args:
            nm_ids: 1..20 nmIds.
            date_from: YYYY-MM-DD.
            date_to: YYYY-MM-DD.
            aggregation_level: "day" | "week".
            skip_deleted_nm: Skip deleted items.

        Returns:
            List of {product, history: [...], currency}.
        """
        if (self.token or "").upper() == "MOCK":
            return []

        # WB API expects YYYY-MM-DD only; ISO datetime causes 400 "parsing time ... extra text"
        body = {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": nm_ids[:20],
            "skipDeletedNm": skip_deleted_nm,
            "aggregationLevel": aggregation_level,
        }
        payload_log = {
            "selectedPeriod_start": date_from,
            "selectedPeriod_end": date_to,
            "aggregationLevel": aggregation_level,
            "nmIds_count": len(body["nmIds"]),
            "nmIds_first3": list(body["nmIds"][:3]),
        }
        logger.info(
            "WB sales-funnel request: %s",
            payload_log,
        )
        async with httpx.AsyncClient() as client:
            r = await self._request(
                client,
                "POST",
                "/api/analytics/v3/sales-funnel/products/history",
                json_body=body,
            )
        if r.status_code >= 400:
            request_summary: Dict[str, Any] = {
                "selectedPeriod": {"start": date_from, "end": date_to},
                "aggregationLevel": aggregation_level,
                "nmIds_count": len(body["nmIds"]),
                "nmIds_first3": list(body["nmIds"][:3]),
            }
            error_text = (r.text or "")[:2000]
            error_preview = (r.text or "")[:500]
            logger.warning(
                "WB sales-funnel API error: status_code=%s response_text_preview=%s request_payload=%s",
                r.status_code,
                error_preview,
                payload_log,
            )
            raise WBAnalyticsBadRequestError(r.status_code, error_text, request_summary)
        if r.status_code != 200:
            return []
        try:
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def get_sales_funnel_products(
        self,
        date_from: str,
        date_to: str,
        nm_ids: List[int],
        offset: int = 0,
        limit: int = 1000,
        skip_deleted_nm: bool = False,
    ) -> Dict[str, Any]:
        """POST /api/analytics/v3/sales-funnel/products (single page).

        Returns raw response shape: {"data": {"products": [...], "currency": "RUB"}} or empty.
        Use get_sales_funnel_products_all_pages for full chunk with pagination.
        """
        if (self.token or "").upper() == "MOCK":
            return {"data": {"products": [], "currency": None}}

        chunk = nm_ids[:limit]
        body = {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": chunk,
            "skipDeletedNm": skip_deleted_nm,
            "limit": limit,
            "offset": offset,
        }
        payload_log = {
            "selectedPeriod_start": date_from,
            "selectedPeriod_end": date_to,
            "nmIds_count": len(body["nmIds"]),
            "offset": offset,
            "limit": limit,
        }
        logger.info("WB sales-funnel/products request: %s", payload_log)
        async with httpx.AsyncClient() as client:
            r = await self._request(
                client,
                "POST",
                "/api/analytics/v3/sales-funnel/products",
                json_body=body,
            )
        if r.status_code >= 400:
            request_summary: Dict[str, Any] = {
                "selectedPeriod": {"start": date_from, "end": date_to},
                "nmIds_count": len(body["nmIds"]),
                "offset": offset,
                "limit": limit,
            }
            raise WBAnalyticsBadRequestError(
                r.status_code, (r.text or "")[:2000], request_summary
            )
        if r.status_code != 200:
            return {"data": {"products": [], "currency": None}}
        try:
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                return data
            return {"data": {"products": [], "currency": None}}
        except Exception:
            return {"data": {"products": [], "currency": None}}

    async def get_sales_funnel_products_all_pages(
        self,
        date_from: str,
        date_to: str,
        nm_ids: List[int],
        limit: int = 1000,
        skip_deleted_nm: bool = False,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch all pages for one chunk of nm_ids. Returns (products, currency).

        Zero-fill in ingest must happen only after this returns (full chunk response).
        """
        all_products: List[Dict[str, Any]] = []
        currency: Optional[str] = None
        offset = 0
        page_count = 0
        while True:
            resp = await self.get_sales_funnel_products(
                date_from=date_from,
                date_to=date_to,
                nm_ids=nm_ids,
                offset=offset,
                limit=limit,
                skip_deleted_nm=skip_deleted_nm,
            )
            data = resp.get("data") or {}
            products = data.get("products")
            if not isinstance(products, list):
                products = []
            if currency is None and data.get("currency") is not None:
                currency = str(data["currency"])
            page_count += 1
            fetched = len(products)
            all_products.extend(products)
            total_collected = len(all_products)
            logger.info(
                "WB sales-funnel/products pagination offset=%s fetched_count=%s total_collected=%s page_count=%s",
                offset,
                fetched,
                total_collected,
                page_count,
            )
            if fetched < limit or fetched == 0:
                break
            offset += limit
        return (all_products, currency)

    async def get_search_texts(
        self,
        nm_id: int,
        date_from: str,
        date_to: str,
        limit: int = 1000,
        top_order_by: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """POST /api/v2/search-report/product/search-texts.

        Returns list of search query items for the product.
        """
        if (self.token or "").upper() == "MOCK":
            return []

        body: Dict[str, Any] = {
            "nmId": nm_id,
            "currentPeriod": {"start": date_from, "end": date_to},
            "limit": limit,
        }
        if top_order_by:
            body["topOrderBy"] = top_order_by
        async with httpx.AsyncClient() as client:
            r = await self._request(
                client,
                "POST",
                "/api/v2/search-report/product/search-texts",
                json_body=body,
            )
        if r.status_code != 200:
            return []
        try:
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                items = data.get("data") or data.get("searchTexts")
                return items if isinstance(items, list) else []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def get_search_orders(
        self,
        nm_id: int,
        texts: List[str],
        date_from: str,
        date_to: str,
    ) -> List[Dict[str, Any]]:
        """POST /api/v2/search-report/product/orders.

        Returns orders/positions by search texts.
        """
        if (self.token or "").upper() == "MOCK":
            return []

        body = {
            "nmId": nm_id,
            "searchTexts": texts,
            "currentPeriod": {"start": date_from, "end": date_to},
        }
        async with httpx.AsyncClient() as client:
            r = await self._request(
                client,
                "POST",
                "/api/v2/search-report/product/orders",
                json_body=body,
            )
        if r.status_code != 200:
            return []
        try:
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                items = data.get("data") or data.get("orders")
                return items if isinstance(items, list) else []
            return data if isinstance(data, list) else []
        except Exception:
            return []
