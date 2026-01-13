"""Lightweight HTTP client for Wildberries public catalog API (catalog.wb.ru).

This client fetches public catalog data without authentication.
Used for scraping frontend prices for comparison/validation.
"""

import asyncio
import httpx
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


class CatalogClient:
    """Client for WB public catalog API."""
    
    def __init__(self):
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # Headers as in Apps Script / browser DevTools
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.wildberries.ru/",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    
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
                    print(f"catalog_client: request failed with {response.status_code}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"catalog_client: request exception: {e}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
                else:
                    print(f"catalog_client: request failed after {self.max_retries} attempts: {e}")
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
        base_url: str
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
        
        print(f"catalog_client: URL={url}")
        print(f"catalog_client: method=GET, brand_id={brand_id}, page={page}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                r = await self._request_with_retry(
                    client, "GET", url, headers=self.headers
                )
                
                if not r:
                    print("catalog_client: request returned None (no response)")
                    return {}
                
                print(f"catalog_client: HTTP status={r.status_code}")
                response_text = r.text[:500] if r.text else "(empty)"
                print(f"catalog_client: response preview (first 500 chars): {response_text}")
                
                if r.status_code == 200:
                    try:
                        data = r.json()
                        print(f"catalog_client: response type={type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'list'}")
                        return data
                    except Exception as e:
                        print(f"catalog_client: JSON parse error: {type(e).__name__}: {e}")
                        return {}
                elif r.status_code == 429:
                    print("catalog_client: HTTP 429 Too Many Requests - rate limit exceeded, need backoff")
                    return {}
                elif r.status_code >= 500:
                    print(f"catalog_client: HTTP {r.status_code} server error - will retry")
                    return {}
                else:
                    print(f"catalog_client: HTTP {r.status_code} error")
                    return {}
            except Exception as e:
                print(f"catalog_client: exception during request: {type(e).__name__}: {e}")
                return {}
        
        return {}

