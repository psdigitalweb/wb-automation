from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services import wb_storefront_resolver as resolver


class _RowsConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params):
        assert params == {"project_id": 2}
        return [(101,), (202,), (303,)]


class _Engine:
    def connect(self):
        return _RowsConnection()


class _ClientContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url: str):
        assert "supplier=4058267" in url
        return self.response


def test_resolver_verifies_seller_and_calculates_token_catalog_overlap(monkeypatch) -> None:
    payload = {
        "products": [
            {"id": 101, "supplierId": 4058267, "supplier": "Seller LLC", "name": "One", "brand": "Brand"},
            {"id": 202, "supplierId": 4058267, "supplier": "Seller LLC", "name": "Two", "brand": ""},
            {"id": 999, "supplierId": 4058267, "supplier": "Seller LLC", "name": "Three", "brand": "Brand"},
        ]
    }
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    observed = {}
    monkeypatch.setattr(resolver, "get_frontend_prices_proxy_config", lambda project_id: ("https://secret-proxy", "https"))
    monkeypatch.setattr(
        resolver,
        "make_async_client",
        lambda **kwargs: observed.setdefault("client", _ClientContext(response)),
    )
    monkeypatch.setattr(resolver, "engine", _Engine())

    result = asyncio.run(
        resolver.resolve_wb_storefront(
            project_id=2,
            seller_url="wildberries.ru/seller/4058267/",
        )
    )

    assert result["verified"] is True
    assert result["seller_url"] == "https://www.wildberries.ru/seller/4058267"
    assert result["seller_name"] == "Seller LLC"
    assert result["storefront_products_count"] == 3
    assert result["cabinet_products_count"] == 3
    assert result["matched_products_count"] == 2
    assert result["coverage_percent"] == 66.7
    assert result["proxy_configured"] is True
    assert len(result["sample_products"]) == 3


def test_resolver_requires_proxy_when_wb_rejects_direct_request(monkeypatch) -> None:
    response = SimpleNamespace(status_code=403)
    monkeypatch.setattr(resolver, "get_frontend_prices_proxy_config", lambda project_id: (None, None))
    monkeypatch.setattr(resolver, "make_async_client", lambda **kwargs: _ClientContext(response))

    result = asyncio.run(
        resolver.resolve_wb_storefront(
            project_id=2,
            seller_url="https://www.wildberries.ru/seller/4058267",
        )
    )

    assert result["verified"] is False
    assert result["error_code"] == "proxy_required"
    assert result["proxy_configured"] is False
    assert result["http_status"] == 403


def test_resolver_rejects_payload_from_another_seller(monkeypatch) -> None:
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"products": [{"id": 101, "supplierId": 999, "name": "Wrong"}]},
    )
    monkeypatch.setattr(resolver, "get_frontend_prices_proxy_config", lambda project_id: ("http://proxy", "http"))
    monkeypatch.setattr(resolver, "make_async_client", lambda **kwargs: _ClientContext(response))

    result = asyncio.run(
        resolver.resolve_wb_storefront(
            project_id=2,
            seller_url="https://www.wildberries.ru/seller/4058267",
        )
    )

    assert result["verified"] is False
    assert result["error_code"] == "seller_id_mismatch"


def test_resolver_uses_project_snapshot_when_live_check_is_rate_limited(monkeypatch) -> None:
    class SnapshotResult:
        def mappings(self):
            return self

        def all(self):
            return [
                {
                    "raw": {
                        "id": 101,
                        "supplierId": 4058267,
                        "supplier": "Seller LLC",
                        "name": "Cached product",
                    },
                    "snapshot_at": "2026-08-01T10:00:00+00:00",
                }
            ]

    class SnapshotConnection(_RowsConnection):
        def execute(self, statement, params):
            if "seller_id" in params:
                return SnapshotResult()
            return super().execute(statement, params)

    class SnapshotEngine:
        def connect(self):
            return SnapshotConnection()

    response = SimpleNamespace(status_code=429)
    monkeypatch.setattr(resolver, "get_frontend_prices_proxy_config", lambda project_id: ("http://proxy", "http"))
    monkeypatch.setattr(resolver, "make_async_client", lambda **kwargs: _ClientContext(response))
    monkeypatch.setattr(resolver, "engine", SnapshotEngine())

    result = asyncio.run(
        resolver.resolve_wb_storefront(
            project_id=2,
            seller_url="https://www.wildberries.ru/seller/4058267",
        )
    )

    assert result["verified"] is True
    assert result["verification_source"] == "cached_snapshot"
    assert result["verified_at"] == "2026-08-01T10:00:00+00:00"
    assert result["http_status"] == 429
