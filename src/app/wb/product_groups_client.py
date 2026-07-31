"""Client for WB storefront product grouping data."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from app.utils.httpx_client import make_async_client


_DETAIL_URL = "https://card.wb.ru/cards/v4/detail"


class WBProductGroupsError(RuntimeError):
    """Raised when a complete product-group crawl cannot be produced."""


class WBProductGroupsClient:
    def __init__(
        self,
        *,
        proxy_url: str | None,
        batch_size: int = 100,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.proxy_url = proxy_url
        self.batch_size = max(1, min(int(batch_size), 100))
        self.timeout_seconds = max(10.0, float(timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://www.wildberries.ru/",
        }

    @staticmethod
    def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

    async def _fetch_batch(self, client: httpx.AsyncClient, nm_ids: list[int]) -> list[dict[str, Any]]:
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "spp": "30",
            "ab_testing": "false",
            "nm": ";".join(str(value) for value in nm_ids),
        }
        last_error = "unknown_error"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(_DETAIL_URL, params=params, headers=self.headers)
                if response.status_code == 200:
                    payload = response.json()
                    products = payload.get("products") if isinstance(payload, dict) else None
                    if not isinstance(products, list):
                        raise WBProductGroupsError("invalid_products_payload")
                    return [item for item in products if isinstance(item, dict)]
                last_error = f"http_status_{response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break
            except WBProductGroupsError:
                raise
            except Exception as exc:
                last_error = type(exc).__name__
            if attempt < self.max_retries:
                await asyncio.sleep(min(float(attempt), 3.0))
        raise WBProductGroupsError(f"batch_fetch_failed:{last_error}")

    async def fetch_memberships(self, nm_ids: list[int]) -> tuple[dict[int, int], int]:
        requested = list(dict.fromkeys(int(value) for value in nm_ids if int(value) > 0))
        if not requested:
            return {}, 0

        timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=self.timeout_seconds,
            read=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )
        mappings: dict[int, int] = {}
        batches_total = 0
        async with make_async_client(
            proxy_url=self.proxy_url,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            for batch in self._chunks(requested, self.batch_size):
                batches_total += 1
                products = await self._fetch_batch(client, batch)
                requested_batch = set(batch)
                for product in products:
                    try:
                        nm_id = int(product.get("id"))
                        group_id = int(product.get("root"))
                    except (TypeError, ValueError):
                        continue
                    if nm_id in requested_batch and nm_id > 0 and group_id > 0:
                        mappings[nm_id] = group_id
        return mappings, batches_total
