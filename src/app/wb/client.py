import asyncio
import httpx
from typing import Any, Dict, List, Optional
from .. import settings

class WBClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.WB_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}" if self.token else ""}
        # Use content-api.wildberries.ru (same as products ingestion)
        # suppliers-api.wildberries.ru DNS does not resolve
        self.base_url = "https://content-api.wildberries.ru"
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
        
        # According to WB API docs, warehouses might be in different endpoints
        # Try multiple possible endpoints and base URLs
        possible_urls = [
            f"{self.base_url}/api/v1/warehouses",
            f"{self.base_url}/api/v2/warehouses",
            f"https://api.wildberries.ru/api/v1/warehouses",
            f"https://api.wildberries.ru/api/v2/warehouses",
        ]
        
        for url in possible_urls:
            print(f"fetch_warehouses: trying URL: {url}")
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
                                
                                # WB API может возвращать список или объект с данными
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
                            print("fetch_warehouses: HTTP 403 Forbidden - token may lack required scopes/permissions")
                            return []
                        elif r.status_code == 404:
                            print(f"fetch_warehouses: HTTP 404 Not Found - endpoint {url} does not exist")
                            continue  # Try next URL
                        else:
                            print(f"fetch_warehouses: HTTP {r.status_code} error")
                            return []
                    else:
                        print("fetch_warehouses: request returned None (no response)")
                except Exception as e:
                    print(f"fetch_warehouses: exception during request: {type(e).__name__}: {e}")
                    continue  # Try next URL
        
        print("fetch_warehouses: all endpoints failed, returning empty list")
        return []

    async def fetch_stocks(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch stock balances from WB API.
        
        Args:
            date: Date in format YYYY-MM-DD, if None uses current date
        """
        if (self.token or "").upper() == "MOCK":
            print("fetch_stocks: MOCK mode, returning empty list")
            return []
        
        # WB API для остатков обычно требует дату
        if not date:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")
        
        # According to WB API docs, stocks endpoint might be different
        # Try multiple possible endpoints and base URLs
        possible_urls = [
            f"{self.base_url}/api/v1/supplies/stocks",
            f"{self.base_url}/api/v2/supplies/stocks",
            f"https://api.wildberries.ru/api/v1/supplies/stocks",
            f"https://api.wildberries.ru/api/v2/supplies/stocks",
        ]
        
        params = {"date": date}
        
        for url in possible_urls:
            print(f"fetch_stocks: trying URL: {url}")
            print(f"fetch_stocks: method=GET, params={params}")
            print(f"fetch_stocks: headers={{'Authorization': 'Bearer <token_present>' if self.token else 'None'}}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
                    if r:
                        print(f"fetch_stocks: HTTP status={r.status_code}")
                        response_text = r.text[:500] if r.text else "(empty)"
                        print(f"fetch_stocks: response preview (first 500 chars): {response_text}")
                        
                        if r.status_code == 200:
                            try:
                                data = r.json()
                                print(f"fetch_stocks: response type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}")
                                
                                # WB API может возвращать список или объект с данными
                                if isinstance(data, list):
                                    if len(data) == 0:
                                        print("fetch_stocks: WB API returned empty list")
                                    else:
                                        print(f"fetch_stocks: WB API returned {len(data)} stock records")
                                    return data
                                elif isinstance(data, dict) and "data" in data:
                                    result = data["data"]
                                    if len(result) == 0:
                                        print("fetch_stocks: WB API returned empty list in data field")
                                    return result
                                elif isinstance(data, dict) and "stocks" in data:
                                    result = data["stocks"]
                                    if len(result) == 0:
                                        print("fetch_stocks: WB API returned empty list in stocks field")
                                    return result
                                elif isinstance(data, dict):
                                    print("fetch_stocks: WB API returned single dict, wrapping in list")
                                    return [data]
                                print("fetch_stocks: WB API returned unexpected format")
                                return []
                            except Exception as e:
                                print(f"fetch_stocks: JSON parse error: {e}")
                                return []
                        elif r.status_code == 401:
                            print("fetch_stocks: HTTP 401 Unauthorized - check token validity and permissions")
                            return []
                        elif r.status_code == 403:
                            print("fetch_stocks: HTTP 403 Forbidden - token may lack required scopes/permissions")
                            return []
                        elif r.status_code == 404:
                            print(f"fetch_stocks: HTTP 404 Not Found - endpoint {url} does not exist")
                            continue  # Try next URL
                        else:
                            print(f"fetch_stocks: HTTP {r.status_code} error")
                            return []
                    else:
                        print("fetch_stocks: request returned None (no response)")
                except Exception as e:
                    print(f"fetch_stocks: exception during request: {type(e).__name__}: {e}")
                    continue  # Try next URL
        
        print("fetch_stocks: all endpoints failed, returning empty list")
        return []
