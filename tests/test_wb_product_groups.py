from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from app import api_wb_product_groups
from app.services import wb_product_groups as service
from app.services.ingest.registry import get_job_definition
from app.wb import product_groups_client


class _FakeResponse:
    status_code = 200

    def __init__(self, products: list[dict]) -> None:
        self._products = products

    def json(self) -> dict:
        return {"products": self._products}


class _FakeHttpClient:
    def __init__(self) -> None:
        self.batches: list[list[int]] = []

    async def get(self, _url: str, *, params: dict, headers: dict) -> _FakeResponse:
        assert headers["Referer"] == "https://www.wildberries.ru/"
        nm_ids = [int(value) for value in params["nm"].split(";")]
        self.batches.append(nm_ids)
        return _FakeResponse(
            [
                {"id": nm_id, "root": 1000 + (nm_id % 2)}
                for nm_id in nm_ids
            ]
            + [{"id": 999999999, "root": 1}]
        )


class _FakeClientContext:
    def __init__(self, client: _FakeHttpClient) -> None:
        self.client = client

    async def __aenter__(self) -> _FakeHttpClient:
        return self.client

    async def __aexit__(self, *_args) -> None:
        return None


def test_product_groups_client_batches_and_filters_unrequested_products(monkeypatch):
    fake_client = _FakeHttpClient()
    monkeypatch.setattr(
        product_groups_client,
        "make_async_client",
        lambda **_kwargs: _FakeClientContext(fake_client),
    )

    client = product_groups_client.WBProductGroupsClient(
        proxy_url="http://proxy.invalid:1234",
        batch_size=2,
    )
    mappings, batches_total = asyncio.run(client.fetch_memberships([10, 11, 12, 13, 14]))

    assert batches_total == 3
    assert fake_client.batches == [[10, 11], [12, 13], [14]]
    assert mappings == {10: 1000, 11: 1001, 12: 1000, 13: 1001, 14: 1000}


def test_product_groups_ingest_job_supports_manual_and_schedule():
    definition = get_job_definition("wb_product_groups")

    assert definition is not None
    assert definition["title"] == "Загрузка связок товаров WB"
    assert definition["supports_manual"] is True
    assert definition["supports_schedule"] is True


def test_product_groups_list_forwards_category_filter(monkeypatch):
    captured = {}

    def _list_product_groups(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "page": 1, "page_size": 50}

    monkeypatch.setattr(api_wb_product_groups, "list_product_groups", _list_product_groups)

    result = asyncio.run(
        api_wb_product_groups.list_product_groups_endpoint(
            project_id=1,
            search=None,
            category="Кружки",
            in_stock=True,
            page=1,
            page_size=50,
            min_members=2,
            _member={},
        )
    )

    assert result["total"] == 0
    assert captured["category"] == "Кружки"
    assert captured["in_stock"] is True


def test_product_groups_for_product_returns_current_memberships(monkeypatch):
    monkeypatch.setattr(
        api_wb_product_groups,
        "get_product_group_memberships",
        lambda project_id, nm_id: [
            {
                "wb_group_id": 77,
                "members_count": 3,
                "last_seen_at": "2026-07-27T12:00:00+00:00",
            }
        ],
    )

    result = asyncio.run(
        api_wb_product_groups.get_product_groups_for_product_endpoint(
            project_id=1,
            nm_id=123,
            _member={},
        )
    )

    assert result["items"][0]["wb_group_id"] == 77
    assert result["items"][0]["members_count"] == 3


def test_ingest_product_groups_returns_individual_membership_stats(monkeypatch):
    monkeypatch.setattr(service, "list_project_nm_ids", lambda _project_id: [101, 102, 103])
    monkeypatch.setattr(
        service,
        "_get_frontend_prices_proxy_config",
        lambda _project_id: ("http://proxy.invalid:1234", "http"),
    )

    class _Client:
        def __init__(self, **kwargs) -> None:
            assert kwargs["proxy_url"].startswith("http://")

        async def fetch_memberships(self, _nm_ids):
            return {101: 77, 102: 77}, 1

    monkeypatch.setattr(service, "WBProductGroupsClient", _Client)
    monkeypatch.setattr(
        service,
        "apply_membership_snapshot",
        lambda **_kwargs: {
            "memberships_created": 2,
            "memberships_changed": 0,
            "memberships_refreshed": 0,
            "memberships_marked_missing": 0,
            "memberships_closed": 0,
        },
    )

    result = asyncio.run(service.ingest_wb_product_groups(project_id=5, run_id=9))

    assert result["products_requested"] == 3
    assert result["products_returned"] == 2
    assert result["products_missing"] == 1
    assert result["groups_total"] == 1
    assert result["groups_multi_member"] == 1
    assert result["proxy_used"] is True


def test_comparison_endpoint_returns_members_without_group_metric_aggregation(monkeypatch):
    members = [
        {
            "nm_id": 1,
            "price": {"last": 100},
            "spp": {"last": 10},
            "funnel": {"orders": 3},
        },
        {
            "nm_id": 2,
            "price": {"last": 200},
            "spp": {"last": 20},
            "funnel": {"orders": 4},
        },
    ]
    monkeypatch.setattr(api_wb_product_groups, "get_group_comparison", lambda **_kwargs: members)

    result = asyncio.run(
        api_wb_product_groups.get_product_group_comparison_endpoint(
            project_id=1,
            wb_group_id=77,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
            _member={},
        )
    )

    assert result["members"] == members
    assert "summary" not in result
    assert result["members_count"] == 2


def test_series_endpoint_limits_visual_comparison_to_five_products(monkeypatch):
    monkeypatch.setattr(
        api_wb_product_groups,
        "get_group_members",
        lambda *_args: [{"nm_id": value} for value in range(1, 10)],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api_wb_product_groups.get_product_group_series_endpoint(
                project_id=1,
                wb_group_id=77,
                nm_ids=[1, 2, 3, 4, 5, 6],
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 31),
                _member={},
            )
        )

    assert exc.value.status_code == 400
