import asyncio
import httpx
from typing import Any, Dict, List, Optional
from .. import settings

class WBClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.WB_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}" if self.token else ""}
        # Use content-api.wildberries.ru for products
        # For warehouses/stocks, use marketplace-api.wildberries.ru (according to WB docs)
        # For Statistics API (Reports), use statistics-api.wildberries.ru
        self.base_url = "https://content-api.wildberries.ru"
        self.marketplace_base_url = "https://marketplace-api.wildberries.ru"
        self.statistics_base_url = "https://statistics-api.wildberries.ru"
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1.0

    async def _request_with_retry(
        self, 
        client: httpx.AsyncClient, 
        method: str, 
        url: str, 
        **kwargs
    ) -> Optional[httpx.Response]:
        """Make HTTP request with retries and exponential backoff."""
        for attempt in range(self.max_retries):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code < 500:  # Don't retry on 4xx errors
                    return response
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Request failed with {response.status_code}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Request exception: {e}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
                else:
                    print(f"Request failed after {self.max_retries} attempts: {e}")
                    return None
        return None

    async def get_prices(self, nm_ids: list[int]) -> dict[int, dict]:
        # Если токен == "MOCK", вернём фейковые данные
        if (self.token or "").upper() == "MOCK":
            return {nm: {"price": 1290, "discount": 15} for nm in nm_ids}

        # Временно опрашиваем по одному nm_id. Потом переделаем на батчи и правильный эндпоинт.
        result: dict[int, dict] = {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for nm in nm_ids:
                url = f"{self.base_url}/public/api/v1/info?nmId={nm}"
                r = await self._request_with_retry(client, "GET", url, headers=self.headers)
                if r and r.status_code == 200:
                    result[nm] = r.json()
        return result

    async def fetch_warehouses(self) -> List[Dict[str, Any]]:
        """Fetch warehouses/offices list from WB API."""
        if (self.token or "").upper() == "MOCK":
            print("fetch_warehouses: MOCK mode, returning empty list")
            return []
        
        # According to WB API docs, warehouses are in marketplace-api v3
        # Correct endpoint: GET /api/v3/warehouses
        url = f"{self.marketplace_base_url}/api/v3/warehouses"
        
        print(f"fetch_warehouses: URL: {url}")
        print(f"fetch_warehouses: method=GET, headers={{'Authorization': 'Bearer <token_present>' if self.token else 'None'}}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await self._request_with_retry(client, "GET", url, headers=self.headers)
                if r:
                    print(f"fetch_warehouses: HTTP status={r.status_code}")
                    response_text = r.text[:500] if r.text else "(empty)"
                    print(f"fetch_warehouses: response preview (first 500 chars): {response_text}")
                    
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            print(f"fetch_warehouses: response type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}")
                            
                            # WB API возвращает список складов
                            if isinstance(data, list):
                                if len(data) == 0:
                                    print("fetch_warehouses: WB API returned empty list")
                                else:
                                    print(f"fetch_warehouses: WB API returned {len(data)} warehouses")
                                return data
                            elif isinstance(data, dict) and "data" in data:
                                result = data["data"]
                                if len(result) == 0:
                                    print("fetch_warehouses: WB API returned empty list in data field")
                                return result
                            elif isinstance(data, dict):
                                print("fetch_warehouses: WB API returned single dict, wrapping in list")
                                return [data]
                            print("fetch_warehouses: WB API returned unexpected format")
                            return []
                        except Exception as e:
                            print(f"fetch_warehouses: JSON parse error: {e}")
                            return []
                    elif r.status_code == 401:
                        print("fetch_warehouses: HTTP 401 Unauthorized - check token validity and permissions")
                        return []
                    elif r.status_code == 403:
                        print("fetch_warehouses: HTTP 403 Forbidden - token may lack required scopes/permissions (need 'Маркетплейс' category)")
                        return []
                    else:
                        print(f"fetch_warehouses: HTTP {r.status_code} error")
                        return []
                else:
                    print("fetch_warehouses: request returned None (no response)")
            except Exception as e:
                print(f"fetch_warehouses: exception during request: {type(e).__name__}: {e}")
        
        return []

    async def fetch_stocks(self, warehouse_id: int, chrt_ids: List[int]) -> List[Dict[str, Any]]:
        """Fetch stock balances for given chrtIds on a specific warehouse.

        According to WB API docs, stocks endpoint is POST /api/v3/stocks/{warehouseId}
        and requires:
        - warehouseId (path)
        - body: {"chrtIds": [ ... ]}
        """
        if (self.token or "").upper() == "MOCK":
            print("fetch_stocks: MOCK mode, returning empty list")
            return []

        if not chrt_ids:
            print(f"fetch_stocks: empty chrt_ids for warehouse {warehouse_id}, skipping request")
            return []

        url = f"{self.marketplace_base_url}/api/v3/stocks/{warehouse_id}"
        body = {"chrtIds": chrt_ids}

        print(f"fetch_stocks: URL={url}, warehouse_id={warehouse_id}")
        print(f"fetch_stocks: method=POST, body.chrtIds.len={len(chrt_ids)}")
        print(
            f"fetch_stocks: headers={{'Authorization': 'Bearer <token_present>' if self.token else 'None'}}"
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await self._request_with_retry(
                    client, "POST", url, headers=self.headers, json=body
                )
                if not r:
                    print("fetch_stocks: request returned None (no response)")
                    return []

                print(f"fetch_stocks: HTTP status={r.status_code}")
                response_text = r.text[:500] if r.text else "(empty)"
                print(
                    f"fetch_stocks: response preview (first 500 chars): {response_text}"
                )

                if r.status_code == 200:
                    try:
                        data = r.json()
                        print(
                            "fetch_stocks: response type="
                            f"{type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}"
                        )

                        # WB API возвращает {"stocks": [...]} или список напрямую
                        if isinstance(data, list):
                            if len(data) == 0:
                                print(
                                    f"fetch_stocks: WB API returned empty list for warehouse {warehouse_id}"
                                )
                            else:
                                print(
                                    f"fetch_stocks: WB API returned {len(data)} stock records for warehouse {warehouse_id}"
                                )
                            return data
                        elif isinstance(data, dict) and "stocks" in data:
                            result = data["stocks"]
                            if len(result) == 0:
                                print(
                                    f"fetch_stocks: WB API returned empty list in stocks field for warehouse {warehouse_id}"
                                )
                            else:
                                print(
                                    f"fetch_stocks: WB API returned {len(result)} stock records for warehouse {warehouse_id}"
                                )
                            return result
                        elif isinstance(data, dict) and "data" in data:
                            result = data["data"]
                            if len(result) == 0:
                                print(
                                    f"fetch_stocks: WB API returned empty list in data field for warehouse {warehouse_id}"
                                )
                            return result
                        elif isinstance(data, dict):
                            return [data]

                        print("fetch_stocks: WB API returned unexpected format")
                        return []
                    except Exception as e:
                        print(f"fetch_stocks: JSON parse error: {e}")
                        return []
                elif r.status_code == 401:
                    print(
                        "fetch_stocks: HTTP 401 Unauthorized - check token validity and permissions"
                    )
                    return []
                elif r.status_code == 403:
                    print(
                        "fetch_stocks: HTTP 403 Forbidden - token may lack required scopes/permissions (need 'Маркетплейс' category)"
                    )
                    return []
                elif r.status_code == 400:
                    print(
                        f"fetch_stocks: HTTP 400 Bad Request - check chrtIds/body for warehouse {warehouse_id}"
                    )
                    return []
                else:
                    print(f"fetch_stocks: HTTP {r.status_code} error")
                    return []
            except Exception as e:
                print(f"fetch_stocks: exception during request: {type(e).__name__}: {e}")
                return []

    async def fetch_supplier_stocks(self, date_from: str) -> List[Dict[str, Any]]:
        """Fetch supplier stock balances from WB Statistics API (Reports).
        
        Endpoint: GET https://statistics-api.wildberries.ru/api/v1/supplier/stocks
        Requires: dateFrom parameter (RFC3339 format, e.g., "2019-06-20T00:00:00Z")
        
        Rate limit: 1 request per minute per account.
        Response limit: ~60,000 rows per request.
        Pagination: use lastChangeDate from last row as next dateFrom.
        
        Args:
            date_from: RFC3339 formatted date string (e.g., "2019-06-20T00:00:00Z")
        
        Returns:
            List of stock records. Empty list if no data or error.
        """
        if (self.token or "").upper() == "MOCK":
            print("fetch_supplier_stocks: MOCK mode, returning empty list")
            return []
        
        url = f"{self.statistics_base_url}/api/v1/supplier/stocks"
        params = {"dateFrom": date_from}
        
        # Statistics API uses ApiKey header (not Bearer)
        # But according to WB docs, it's still Authorization: Bearer <token>
        # Let's use the same header format for now
        headers = {"Authorization": f"Bearer {self.token}" if self.token else ""}
        
        print(f"fetch_supplier_stocks: URL={url}")
        print(f"fetch_supplier_stocks: method=GET, dateFrom={date_from}")
        print(f"fetch_supplier_stocks: headers={{'Authorization': 'Bearer <token_present>' if self.token else 'None'}}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await self._request_with_retry(
                    client, "GET", url, headers=headers, params=params
                )
                if not r:
                    print("fetch_supplier_stocks: request returned None (no response)")
                    return []
                
                print(f"fetch_supplier_stocks: HTTP status={r.status_code}")
                response_text = r.text[:500] if r.text else "(empty)"
                print(f"fetch_supplier_stocks: response preview (first 500 chars): {response_text}")
                
                if r.status_code == 200:
                    try:
                        data = r.json()
                        print(f"fetch_supplier_stocks: response type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}")
                        
                        # WB Statistics API returns list directly
                        if isinstance(data, list):
                            if len(data) == 0:
                                print("fetch_supplier_stocks: WB API returned empty list (pagination complete)")
                            else:
                                print(f"fetch_supplier_stocks: WB API returned {len(data)} stock records")
                            return data
                        elif isinstance(data, dict) and "data" in data:
                            result = data["data"]
                            if len(result) == 0:
                                print("fetch_supplier_stocks: WB API returned empty list in data field")
                            else:
                                print(f"fetch_supplier_stocks: WB API returned {len(result)} stock records")
                            return result
                        elif isinstance(data, dict):
                            print("fetch_supplier_stocks: WB API returned single dict, wrapping in list")
                            return [data]
                        
                        print("fetch_supplier_stocks: WB API returned unexpected format")
                        return []
                    except Exception as e:
                        print(f"fetch_supplier_stocks: JSON parse error: {e}")
                        return []
                elif r.status_code == 401:
                    print("fetch_supplier_stocks: HTTP 401 Unauthorized - check token validity and permissions (need 'Статистика' category)")
                    return []
                elif r.status_code == 403:
                    print("fetch_supplier_stocks: HTTP 403 Forbidden - token may lack required scopes/permissions (need 'Статистика' category)")
                    return []
                elif r.status_code == 429:
                    print("fetch_supplier_stocks: HTTP 429 Too Many Requests - rate limit exceeded (1 req/min), need backoff")
                    return []
                elif r.status_code >= 500:
                    print(f"fetch_supplier_stocks: HTTP {r.status_code} server error - will retry")
                    return []
                else:
                    print(f"fetch_supplier_stocks: HTTP {r.status_code} error")
                    return []
            except Exception as e:
                print(f"fetch_supplier_stocks: exception during request: {type(e).__name__}: {e}")
                return []
