import os
import time
import json
import logging
import random
from datetime import date
from typing import Any, Dict, List, Optional

import httpx


class WbApiClient:
    # Explicit endpoint URLs
    OFFICES_URL = "https://marketplace-api.wildberries.ru/api/v3/offices"
    SELLER_WAREHOUSES_URL = "https://marketplace-api.wildberries.ru/api/v3/warehouses"

    def __init__(
        self,
        token: Optional[str] = None,
        min_interval: Optional[float] = None,
        max_retries: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.token = token or os.getenv("WB_API_TOKEN") or os.getenv("WB_TOKEN")
        self.min_interval = (
            float(min_interval)
            if min_interval is not None
            else float(os.getenv("WB_API_MIN_INTERVAL", "0.2"))
        )
        self.max_retries = int(max_retries) if max_retries is not None else int(os.getenv("WB_API_MAX_RETRIES", "3"))
        self.timeout_seconds = (
            float(timeout_seconds) if timeout_seconds is not None else float(os.getenv("WB_API_TIMEOUT", "15"))
        )
        self.logger = logger or logging.getLogger("wb.api")
        self._last_request_ts: float = 0.0

        if not self.token:
            raise ValueError("WB_API_TOKEN is not set")

        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json"
            },
            timeout=self.timeout_seconds,
        )

    def _sleep_for_rps(self) -> float:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        sleep_needed = max(0.0, self.min_interval - elapsed)
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        return sleep_needed

    def _request_json(self, url: str) -> Dict[str, Any] | List[Any]:
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            sleep_delay = self._sleep_for_rps()
            self.logger.info("GET %s try=%s/%s", url, attempt, self.max_retries)

            try:
                response = self._client.get(url)
            except Exception as exc:
                last_exception = exc
                if attempt == self.max_retries:
                    raise
                backoff = min(2 ** (attempt - 1), 30) + random.uniform(0, 1)
                self.logger.info("retry in %ss status=exc", round(backoff, 2))
                time.sleep(backoff)
                continue

            self._last_request_ts = time.monotonic()

            status = response.status_code
            if status == 401:
                raise PermissionError("Check WB_API_TOKEN")
            if status == 403:
                raise PermissionError("Check WB_API_TOKEN")
            if status == 404:
                self.logger.error("404 Not Found: %s", url)
                response.raise_for_status()

            if 200 <= status < 300:
                data = response.json()
                try:
                    payload_len = len(json.dumps(data).encode("utf-8"))
                except Exception:
                    payload_len = 0
                self.logger.info("OK %s bytes=%s", url, payload_len)
                return data  # type: ignore[return-value]

            # Retry on 429/409/5xx
            if status in [429, 409] or 500 <= status < 600:
                if attempt == self.max_retries:
                    response.raise_for_status()
                backoff = min(2 ** (attempt - 1), 30) + random.uniform(0, 1)
                self.logger.info("retry in %ss status=%s", round(backoff, 2), status)
                time.sleep(backoff)
                continue

            # Other unexpected errors: raise immediately
            response.raise_for_status()

        # Should not reach here
        if last_exception:
            raise last_exception
        raise RuntimeError("Request failed without exception")

    def get_offices(self) -> List[Dict[str, Any]]:
        """GET offices data from WB API"""
        return self._request_json(self.OFFICES_URL)  # type: ignore[return-value]

    def get_seller_warehouses(self) -> List[Dict[str, Any]]:
        """GET seller warehouses data from WB API"""
        return self._request_json(self.SELLER_WAREHOUSES_URL)  # type: ignore[return-value]

    # Legacy methods for tariffs (keeping for backward compatibility)
    def get_tariffs_commission(self) -> Dict[str, Any]:
        return self._request_json("https://common-api.wildberries.ru/api/v1/tariffs/commission")  # type: ignore[return-value]

    def get_tariffs_box(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Ensure date parameter is present for /tariffs/box
        if params is None:
            params = {}
        
        if "date" not in params:
            params = params.copy()
            params["date"] = date.today().isoformat()
        
        self.logger.info("Using date parameter: %s", params["date"])
        # Note: tariffs endpoints need different handling for params
        url = "https://common-api.wildberries.ru/api/v1/tariffs/box"
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        return self._request_json(url)  # type: ignore[return-value]

    def get_tariffs_pallet(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Ensure date parameter is present for /tariffs/pallet
        if params is None:
            params = {}
        
        if "date" not in params:
            params = params.copy()
            params["date"] = date.today().isoformat()
        
        self.logger.info("Using date parameter for pallet: %s", params["date"])
        url = "https://common-api.wildberries.ru/api/v1/tariffs/pallet"
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        return self._request_json(url)  # type: ignore[return-value]

    def get_tariffs_return(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Ensure date parameter is present for /tariffs/return
        if params is None:
            params = {}
        
        if "date" not in params:
            params = params.copy()
            params["date"] = date.today().isoformat()
        
        self.logger.info("Using date parameter for return: %s", params["date"])
        url = "https://common-api.wildberries.ru/api/v1/tariffs/return"
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        return self._request_json(url)  # type: ignore[return-value]