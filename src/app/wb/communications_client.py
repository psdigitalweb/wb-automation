"""WB Communications API client (feedbacks, questions). Read-only.

Base URL: prod https://feedbacks-api.wildberries.ru
         sandbox https://feedbacks-api-sandbox.wildberries.ru
Rate limit: 3 rps (burst 6).
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx


class WBCommunicationsClient:
    """Client for WB Feedbacks/Questions API. Read-only."""

    def __init__(self, token: str, use_sandbox: bool = False):
        self.token = token
        self.base_url = (
            "https://feedbacks-api-sandbox.wildberries.ru"
            if use_sandbox
            else "https://feedbacks-api.wildberries.ru"
        )
        self.headers = {"Authorization": f"Bearer {self.token}" if self.token else ""}
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 1.0
        self._min_interval_sec = 0.34  # 3 rps
        self._last_request_at: float = 0

    async def _throttle(self) -> None:
        """Enforce 3 rps rate limit."""
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self._min_interval_sec:
            await asyncio.sleep(self._min_interval_sec - elapsed)
        self._last_request_at = time.monotonic()

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> Optional[httpx.Response]:
        """Throttle + retry on 429/5xx (same logic as app.wb.client.WBClient)."""
        for attempt in range(self.max_retries):
            await self._throttle()
            try:
                response = await asyncio.wait_for(
                    client.request(method, url, **kwargs),
                    timeout=float(self.timeout) + 5.0,
                )
                if response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        delay = min(15 * (attempt + 1), 90)
                        await asyncio.sleep(delay)
                        continue
                    return response
                if response.status_code < 500:
                    return response
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                else:
                    raise
        return None

    async def list_feedbacks(
        self,
        date_from: int,
        date_to: int,
        take: int = 5000,
        skip: int = 0,
        order: str = "dateDesc",
        is_answered: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """GET /api/v1/feedbacks. Returns {"data": {"feedbacks": [...], ...}}."""
        params: Dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "take": take,
            "skip": skip,
            "order": order,
        }
        if is_answered is not None:
            params["isAnswered"] = str(is_answered).lower()
        url = f"{self.base_url}/api/v1/feedbacks"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
        if not r:
            return {"data": {"feedbacks": []}}
        if r.status_code != 200:
            return {"data": {"feedbacks": []}, "error": r.status_code}
        try:
            return r.json()
        except Exception:
            return {"data": {"feedbacks": []}}

    async def list_feedbacks_archive(
        self,
        date_from: int,
        date_to: int,
        take: int = 5000,
        skip: int = 0,
        order: str = "dateDesc",
        is_answered: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """GET /api/v1/feedbacks/archive. List of archived feedbacks.
        Params mirror /feedbacks; exact API contract not fully documented — assume same structure.
        Returns {"data": {"feedbacks": [...], ...}}.
        """
        params: Dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "take": take,
            "skip": skip,
            "order": order,
        }
        if is_answered is not None:
            params["isAnswered"] = str(is_answered).lower()
        url = f"{self.base_url}/api/v1/feedbacks/archive"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
        if not r:
            return {"data": {"feedbacks": []}}
        if r.status_code != 200:
            return {"data": {"feedbacks": []}, "error": r.status_code}
        try:
            return r.json()
        except Exception:
            return {"data": {"feedbacks": []}}

    async def get_feedbacks_count(
        self,
        date_from: int,
        date_to: int,
        is_answered: Optional[bool] = None,
    ) -> Optional[int]:
        """GET /api/v1/feedbacks/count. Returns total count for range (for skip limit check)."""
        params: Dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        if is_answered is not None:
            params["isAnswered"] = str(is_answered).lower()
        url = f"{self.base_url}/api/v1/feedbacks/count"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
        if not r or r.status_code != 200:
            return None
        try:
            data = r.json()
            if isinstance(data, dict):
                inner = data.get("data", data)
                if isinstance(inner, dict) and "count" in inner:
                    return int(inner["count"]) if inner["count"] is not None else None
                if "count" in data:
                    return int(data["count"]) if data["count"] is not None else None
            return None
        except Exception:
            return None

    async def list_questions(
        self,
        date_from: int,
        date_to: int,
        take: int = 5000,
        skip: int = 0,
        order: str = "dateDesc",
        is_answered: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """GET /api/v1/questions. Returns {"data": {"questions": [...], ...}}."""
        params: Dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "take": take,
            "skip": skip,
            "order": order,
        }
        if is_answered is not None:
            params["isAnswered"] = str(is_answered).lower()
        url = f"{self.base_url}/api/v1/questions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await self._request_with_retry(client, "GET", url, headers=self.headers, params=params)
        if not r:
            return {"data": {"questions": []}}
        if r.status_code != 200:
            return {"data": {"questions": []}, "error": r.status_code}
        try:
            return r.json()
        except Exception:
            return {"data": {"questions": []}}
