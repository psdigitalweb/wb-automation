import asyncio
from typing import Any, Dict, Optional, List

import httpx

from app import settings


class WBCommonApiClient:
    """Client for Wildberries Common API (tariffs and other global endpoints).

    Uses a service-level token (`WB_SERVICE_TOKEN`) so that marketplace-level data
    (e.g. tariffs) can be shared across all projects and is not tied to any project.
    """

    def __init__(self, token: str | None = None):
        # Tariffs API uses HeaderApiKey; in practice this is usually passed via Authorization header without Bearer.
        self.token = token or settings.WB_SERVICE_TOKEN
        self.base_url = "https://common-api.wildberries.ru"
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1.0

    def _build_headers(self) -> Dict[str, str]:
        # For Tariffs API we send raw token as Authorization header (HeaderApiKey)
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
                print(f"WBCommonApiClient request: {method} {url} params={params}")
                print(
                    "WBCommonApiClient headers: "
                    "{'Authorization': '<token_present>'}" if headers.get("Authorization") else "{}"
                )
                response = await client.request(method, url, params=params, headers=headers)
                status = response.status_code

                # Handle rate limiting explicitly
                if status == 429:
                    retry_after = response.headers.get("Retry-After")
                    if attempt < self.max_retries - 1:
                        try:
                            delay = float(retry_after)
                        except (TypeError, ValueError):
                            delay = self.retry_delay * (2**attempt)
                        print(
                            f"WBCommonApiClient: 429 Too Many Requests, retrying in {delay}s "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    print("WBCommonApiClient: giving up after 429 and retries")
                    return response

                # Do not retry on other 4xx
                if status < 500:
                    return response

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    print(
                        f"WBCommonApiClient: HTTP {status}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(
                        f"WBCommonApiClient: HTTP {status}, max retries reached, giving up"
                    )
                    return response
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    print(
                        f"WBCommonApiClient: exception {type(e).__name__}: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(
                        f"WBCommonApiClient: exception {type(e).__name__}: {e}, "
                        f"max retries reached, giving up"
                    )
                    return None

        return None

    async def _get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Helper to perform GET request and parse JSON with logging."""
        if (self.token or "").upper() == "MOCK":
            print(f"WBCommonApiClient({path}): MOCK mode, returning empty payload")
            return {"http_status": 200, "payload": None, "headers": {}, "text": ""}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request(client, "GET", path, params=params)
            if not response:
                print(f"WBCommonApiClient: request to {path} returned no response")
                return {"http_status": 0, "payload": None, "headers": {}, "text": ""}

            status = response.status_code
            headers = dict(response.headers)
            text_preview = (response.text or "")[:500]
            print(
                f"WBCommonApiClient: {path} HTTP {status}, "
                f"x-request-id={headers.get('X-Request-Id') or headers.get('x-request-id')}, "
                f"len={len(response.content) if response.content is not None else 0}"
            )
            print(f"WBCommonApiClient: response preview: {text_preview}")

            payload: Any
            try:
                payload = response.json()
            except Exception as e:
                print(
                    f"WBCommonApiClient: JSON parse error for {path}: "
                    f"{type(e).__name__}: {e}"
                )
                payload = None

            return {
                "http_status": status,
                "payload": payload,
                "headers": headers,
                "text": response.text or "",
            }

    async def fetch_commission(self, locale: str = "ru") -> Dict[str, Any]:
        """GET /api/v1/tariffs/commission?locale=..."""
        params = {"locale": locale}
        return await self._get_json("/api/v1/tariffs/commission", params=params)

    async def fetch_box_tariffs(self, date: str) -> Dict[str, Any]:
        """GET /api/v1/tariffs/box?date=YYYY-MM-DD"""
        params = {"date": date}
        return await self._get_json("/api/v1/tariffs/box", params=params)

    async def fetch_pallet_tariffs(self, date: str) -> Dict[str, Any]:
        """GET /api/v1/tariffs/pallet?date=YYYY-MM-DD"""
        params = {"date": date}
        return await self._get_json("/api/v1/tariffs/pallet", params=params)

    async def fetch_return_tariffs(self, date: str) -> Dict[str, Any]:
        """GET /api/v1/tariffs/return?date=YYYY-MM-DD"""
        params = {"date": date}
        return await self._get_json("/api/v1/tariffs/return", params=params)

    async def fetch_acceptance_coefficients(
        self, warehouse_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """GET /api/tariffs/v1/acceptance/coefficients[?warehouseIDs=...]"""
        params: Dict[str, Any] = {}
        if warehouse_ids:
            # WB API expects comma-separated list
            params["warehouseIDs"] = ",".join(str(w) for w in warehouse_ids)
        return await self._get_json(
            "/api/tariffs/v1/acceptance/coefficients", params=params or None
        )

