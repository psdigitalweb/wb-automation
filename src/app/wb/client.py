import asyncio
import httpx
from typing import Any, Dict, List, Optional
from .. import settings

class WBClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.WB_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}" if self.token else ""}
        self.base_url = "https://suppliers-api.wildberries.ru"
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
        
        url = f"{self.base_url}/api/v1/warehouses"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers)
            if r and r.status_code == 200:
                data = r.json()
                # WB API может возвращать список или объект с данными
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, dict):
                    return [data]
                return []
            else:
                print(f"fetch_warehouses: failed with status {r.status_code if r else 'None'}")
                return []
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
        
        url = f"{self.base_url}/api/v1/supplies/stocks"
        params = {"date": date}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
            if r and r.status_code == 200:
                data = r.json()
                # WB API может возвращать список или объект с данными
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, dict) and "stocks" in data:
                    return data["stocks"]
                elif isinstance(data, dict):
                    return [data]
                return []
            else:
                print(f"fetch_stocks: failed with status {r.status_code if r else 'None'}")
                return []
        return []
