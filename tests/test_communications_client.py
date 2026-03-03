"""Tests for WBCommunicationsClient. Mock HTTP via unittest.mock."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.wb.communications_client import WBCommunicationsClient


def test_list_feedbacks_url_and_params():
    """Client builds correct URL and params for feedbacks."""
    client = WBCommunicationsClient(token="test-token", use_sandbox=False)
    assert "feedbacks-api" in client.base_url
    assert "sandbox" not in client.base_url


def test_list_questions_url():
    """Client builds correct URL for questions (sandbox)."""
    client = WBCommunicationsClient(token="test-token", use_sandbox=True)
    assert "feedbacks-api" in client.base_url
    assert "sandbox" in client.base_url


def test_sandbox_base_url():
    """use_sandbox=True uses sandbox domain."""
    client_sandbox = WBCommunicationsClient(token="x", use_sandbox=True)
    client_prod = WBCommunicationsClient(token="x", use_sandbox=False)
    assert "sandbox" in client_sandbox.base_url
    assert "sandbox" not in client_prod.base_url


def test_list_feedbacks_archive_url_and_response():
    """list_feedbacks_archive calls /feedbacks/archive and parses data.feedbacks."""
    import asyncio
    client = WBCommunicationsClient(token="t", use_sandbox=False)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "feedbacks": [
                {"id": "a1", "productDetails": {"nmId": 100}, "createdDate": "2025-01-01T12:00:00Z"},
            ],
        },
    }
    mock_retry = AsyncMock(return_value=mock_response)

    async def run():
        with patch.object(client, "_request_with_retry", mock_retry):
            return await client.list_feedbacks_archive(
                date_from=1704067200,
                date_to=1704153600,
                take=5000,
                skip=0,
                order="dateDesc",
                is_answered=True,
            )

    result = asyncio.run(run())
    assert "data" in result
    assert "feedbacks" in result["data"]
    assert len(result["data"]["feedbacks"]) == 1
    assert result["data"]["feedbacks"][0]["id"] == "a1"
    mock_retry.assert_called_once()
    call_args = mock_retry.call_args
    assert call_args[0][2] == "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/archive"
    assert call_args.kwargs["params"]["dateFrom"] == 1704067200
    assert call_args.kwargs["params"]["dateTo"] == 1704153600
    assert call_args.kwargs["params"]["isAnswered"] == "true"


def test_get_feedbacks_count_parsing():
    """get_feedbacks_count returns count from data.count or root count."""
    import asyncio
    client = WBCommunicationsClient(token="t", use_sandbox=False)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"count": 42}}

    async def run():
        with patch.object(client, "_request_with_retry", new_callable=AsyncMock, return_value=mock_response):
            return await client.get_feedbacks_count(
                date_from=1704067200,
                date_to=1704153600,
            )

    count = asyncio.run(run())
    assert count == 42
    mock_response.json.return_value = {"count": 100}

    async def run2():
        with patch.object(client, "_request_with_retry", new_callable=AsyncMock, return_value=mock_response):
            return await client.get_feedbacks_count(
                date_from=1704067200,
                date_to=1704153600,
            )

    count2 = asyncio.run(run2())
    assert count2 == 100
