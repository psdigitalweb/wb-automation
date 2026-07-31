"""Client for Wildberries Finances API v5 (project-level, uses project token)."""

import asyncio
from typing import Any, Dict, Optional

import httpx


class WBFinancesClient:
    """Client for WB Finances API v5.
    
    Uses project-level token (not service token) for accessing supplier financial reports.
    Base URL: https://statistics-api.wildberries.ru (or supplier-api.wildberries.ru based on endpoint)
    """

    def __init__(self, token: str):
        """Initialize client with project WB token.
        
        Args:
            token: WB API token from project marketplace settings.
        """
        self.token = token
        # Finances API endpoint based on documentation
        # reportDetailByPeriod is on supplier API
        self.base_url = "https://statistics-api.wildberries.ru"
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1.0

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with Authorization token."""
        # WB v5 uses Authorization header with token (not Bearer)
        return {"Authorization": self.token} if self.token else {}

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[httpx.Response]:
        """Make HTTP request with retries, including handling 429 rate limits."""
        url = f"{self.base_url}{path}"
        headers = self._build_headers()

        for attempt in range(self.max_retries):
            try:
                print(f"WBFinancesClient request: {method} {url} params={params}")
                print(
                    "WBFinancesClient headers: "
                    "{'Authorization': '<token_present>'}" if headers.get("Authorization") else "{}"
                )
                response = await client.request(method, url, params=params, headers=headers)
                status = response.status_code

                # Handle rate limiting explicitly
                if status == 429:
                    retry_after = response.headers.get("Retry-After")
                    if attempt < self.max_retries - 1:
                        try:
                            delay = float(retry_after) if retry_after else self.retry_delay * (2**attempt)
                        except (TypeError, ValueError):
                            delay = self.retry_delay * (2**attempt)
                        print(
                            f"WBFinancesClient: 429 Too Many Requests, retrying in {delay}s "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    print("WBFinancesClient: giving up after 429 and retries")
                    return response

                # Do not retry on other 4xx
                if status < 500:
                    return response

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    print(
                        f"WBFinancesClient: HTTP {status}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(
                        f"WBFinancesClient: HTTP {status}, max retries reached, giving up"
                    )
                    return response
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    print(
                        f"WBFinancesClient: exception {type(e).__name__}: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(
                        f"WBFinancesClient: exception {type(e).__name__}: {e}, "
                        f"max retries reached, giving up"
                    )
                    return None

        return None

    async def fetch_report_detail_by_period(
        self,
        date_from: str,
        date_to: str,
        rrdid: Optional[int] = None,
        limit: int = 100000,
    ) -> Dict[str, Any]:
        """Fetch reportDetailByPeriod from WB Finances API v5.
        
        Endpoint: GET /api/v5/supplier/reportDetailByPeriod
        Documentation: https://dev.wildberries.ru/swagger/finances
        
        Args:
            date_from: Start date in format YYYY-MM-DD
            date_to: End date in format YYYY-MM-DD
            rrdid: Cursor for pagination. Pass max(rrd_id) from previous batch for next page.
                   Start with 0 for first page. API returns 204 when no more data.
            limit: Max rows per request (default 100000, WB max).
            
        Returns:
            Dict with http_status, payload (list or None), headers, text
        """
        if (self.token or "").upper() == "MOCK":
            print("WBFinancesClient.fetch_report_detail_by_period: MOCK mode, returning empty payload")
            return {"http_status": 200, "payload": [], "headers": {}, "text": ""}

        path = "/api/v5/supplier/reportDetailByPeriod"
        params: Dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": min(limit, 100000),
        }
        # rrdid: 0 for first page, then max(rrd_id) from last batch
        params["rrdid"] = rrdid if rrdid is not None else 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request(client, "GET", path, params=params)
            if not response:
                print(f"WBFinancesClient: request to {path} returned no response")
                return {"http_status": 0, "payload": None, "headers": {}, "text": ""}

            status = response.status_code
            headers = dict(response.headers)
            text_preview = (response.text or "")[:500]
            print(
                f"WBFinancesClient: {path} HTTP {status}, "
                f"x-request-id={headers.get('X-Request-Id') or headers.get('x-request-id')}, "
                f"len={len(response.content) if response.content is not None else 0}"
            )
            if status != 204:
                print(f"WBFinancesClient: response preview: {text_preview}")

            payload: Any
            if status == 204:
                # No more data (empty response)
                payload = []
            else:
                try:
                    payload = response.json()
                except Exception as e:
                    print(
                        f"WBFinancesClient: JSON parse error for {path}: "
                        f"{type(e).__name__}: {e}"
                    )
                    payload = None

            return {
                "http_status": status,
                "payload": payload,
                "headers": headers,
                "text": response.text or "",
            }
