"""Tests for WBAnalyticsClient. Mock httpx."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.wb.analytics_client import (
    WBAnalyticsClient,
    WBAnalyticsUnauthorizedError,
    WB_ANALYTICS_HEADER_NAME,
)


def test_client_builds_base_url():
    """Client uses seller-analytics base URL."""
    client = WBAnalyticsClient(token="test-token")
    assert "seller-analytics-api" in client.base_url or "analytics" in client.base_url


def test_client_header_name():
    """HeaderApiKey uses Authorization by default."""
    assert WB_ANALYTICS_HEADER_NAME == "Authorization"


def test_build_headers_raw_token():
    """Headers use raw token (no Bearer)."""
    client = WBAnalyticsClient(token="my-secret")
    headers = client._build_headers()
    assert headers.get(WB_ANALYTICS_HEADER_NAME) == "my-secret"
    assert "Bearer" not in headers.get(WB_ANALYTICS_HEADER_NAME, "")


def test_get_sales_funnel_history_mock():
    """get_sales_funnel_history returns parsed list."""
    sample = [
        {
            "product": {"nmId": 123},
            "history": [
                {
                    "date": "2024-10-23",
                    "openCount": 10,
                    "cartCount": 5,
                    "orderCount": 2,
                    "orderSum": 1000,
                }
            ],
            "currency": "RUB",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample

    async def fake_request(*_args, **_kwargs):
        return mock_resp

    async def _run():
        with patch.object(WBAnalyticsClient, "_request", fake_request):
            client = WBAnalyticsClient(token="x")
            return await client.get_sales_funnel_history(
                nm_ids=[123],
                date_from="2024-10-17",
                date_to="2024-10-23",
            )

    result = asyncio.run(_run())
    assert result == sample
    assert len(result) == 1
    assert result[0]["currency"] == "RUB"


def test_get_sales_funnel_history_mock_token_returns_empty():
    """MOCK token returns empty list."""
    async def _run():
        client = WBAnalyticsClient(token="MOCK")
        return await client.get_sales_funnel_history(
            nm_ids=[123],
            date_from="2024-10-17",
            date_to="2024-10-23",
        )
    result = asyncio.run(_run())
    assert result == []


def test_401_raises_unauthorized():
    """401 raises WBAnalyticsUnauthorizedError."""
    async def fake_request_401(*_args, **_kwargs):
        raise WBAnalyticsUnauthorizedError(401, "Unauthorized")

    async def _run():
        with patch.object(WBAnalyticsClient, "_request", fake_request_401):
            client = WBAnalyticsClient(token="bad")
            await client.get_sales_funnel_history(
                nm_ids=[1],
                date_from="2024-10-17",
                date_to="2024-10-23",
            )

    import pytest
    with pytest.raises(WBAnalyticsUnauthorizedError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 401
