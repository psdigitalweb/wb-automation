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
        self.base_url = "https://content-api.wildberries.ru"
        self.marketplace_base_url = "https://marketplace-api.wildberries.ru"
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

    async def fetch_stocks(self, warehouse_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch stock balances from WB API.
        
        According to WB API docs, stocks endpoint is POST /api/v3/stocks/{warehouseId}
        and requires warehouseId and array of chrtIds. For full ingestion, we need to:
        1. Get list of warehouses
        2. For each warehouse, get stocks
        
        Args:
            warehouse_id: Specific warehouse ID. If None, fetches stocks for all warehouses.
        """
        if (self.token or "").upper() == "MOCK":
            print("fetch_stocks: MOCK mode, returning empty list")
            return []
        
        all_stocks = []
        
        # If warehouse_id not specified, get all warehouses first
        if warehouse_id is None:
            warehouses = await self.fetch_warehouses()
            if not warehouses:
                print("fetch_stocks: no warehouses found, cannot fetch stocks")
                return []
            
            print(f"fetch_stocks: found {len(warehouses)} warehouses, fetching stocks for each")
            # Fetch stocks for each warehouse
            for wh in warehouses:
                wh_id = wh.get("id") or wh.get("officeId")
                if wh_id:
                    stocks = await self._fetch_stocks_for_warehouse(wh_id)
                    all_stocks.extend(stocks)
        else:
            stocks = await self._fetch_stocks_for_warehouse(warehouse_id)
            all_stocks.extend(stocks)
        
        if len(all_stocks) == 0:
            print("fetch_stocks: WB API returned empty list for all warehouses")
        else:
            print(f"fetch_stocks: WB API returned {len(all_stocks)} total stock records")
        
        return all_stocks
    
    async def _fetch_stocks_for_warehouse(self, warehouse_id: int) -> List[Dict[str, Any]]:
        """Fetch stocks for a specific warehouse.
        
        Note: WB API requires POST with chrtIds array. Without chrtIds, we may get empty result.
        This is a limitation - we need to know chrtIds to get stocks.
        """
        # According to WB API docs: POST /api/v3/stocks/{warehouseId}
        # Requires body with chrtIds array. Without it, returns empty or error.
        url = f"{self.marketplace_base_url}/api/v3/stocks/{warehouse_id}"
        
        # Try with empty chrtIds array first (may return all or nothing)
        # In real scenario, you'd need to get chrtIds from products first
        body = {"chrtIds": []}
        
        print(f"fetch_stocks: URL: {url}, warehouse_id={warehouse_id}")
        print(f"fetch_stocks: method=POST, body={{'chrtIds': []}} (empty - may need actual chrtIds)")
        print(f"fetch_stocks: headers={{'Authorization': 'Bearer <token_present>' if self.token else 'None'}}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await self._request_with_retry(client, "POST", url, headers=self.headers, json=body)
                if r:
                    print(f"fetch_stocks: HTTP status={r.status_code}")
                    response_text = r.text[:500] if r.text else "(empty)"
                    print(f"fetch_stocks: response preview (first 500 chars): {response_text}")
                    
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            print(f"fetch_stocks: response type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}")
                            
                            if isinstance(data, list):
                                if len(data) == 0:
                                    print(f"fetch_stocks: WB API returned empty list for warehouse {warehouse_id} (may need chrtIds)")
                                else:
                                    print(f"fetch_stocks: WB API returned {len(data)} stock records for warehouse {warehouse_id}")
                                # Add warehouse_id to each stock record
                                for stock in data:
                                    stock["warehouseId"] = warehouse_id
                                return data
                            elif isinstance(data, dict) and "data" in data:
                                result = data["data"]
                                if len(result) == 0:
                                    print(f"fetch_stocks: WB API returned empty list in data field for warehouse {warehouse_id}")
                                for stock in result:
                                    stock["warehouseId"] = warehouse_id
                                return result
                            elif isinstance(data, dict):
                                data["warehouseId"] = warehouse_id
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
                        print("fetch_stocks: HTTP 403 Forbidden - token may lack required scopes/permissions (need 'Маркетплейс' category)")
                        return []
                    elif r.status_code == 400:
                        print(f"fetch_stocks: HTTP 400 Bad Request - may need to provide chrtIds array (warehouse {warehouse_id})")
                        return []
                    else:
                        print(f"fetch_stocks: HTTP {r.status_code} error")
                        return []
                else:
                    print("fetch_stocks: request returned None (no response)")
            except Exception as e:
                print(f"fetch_stocks: exception during request: {type(e).__name__}: {e}")
        
        return []
