from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app import db_wb_catalog
from app.routers import wb_catalog as wb_catalog_router


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None, row=None):
        self._scalar = scalar
        self._rows = rows or []
        self._row = row or {}

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        return self._row


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        if len(self.calls) == 1:
            return _FakeResult(scalar=1)
        if len(self.calls) == 2:
            return _FakeResult(
                rows=[
                    {
                        "nm_id": 123,
                        "vendor_code": "SKU-123",
                        "title": "Тестовый товар",
                        "brand": "",
                        "subject_name": "Жакеты",
                        "sizes": [
                            {"chrtID": 7, "techSize": "M", "wbSize": "46", "skus": ["123"]},
                            {"chrtID": 8, "techSize": "L", "wbSize": "48", "skus": ["456"]},
                        ],
                        "main_photo_url": "https://example.test/photo.webp",
                        "is_active": True,
                        "showcase_price": Decimal("1490"),
                        "spp_percent": Decimal("17.5"),
                        "seller_discount_percent": Decimal("12"),
                        "rrp_price": Decimal("1990"),
                        "rating": Decimal("4.75"),
                        "reviews_count": 328,
                        "impressions": 12450,
                        "card_clicks": 1820,
                        "ctr_percent": Decimal("14.618"),
                        "opens": 2140,
                        "cart_count": 310,
                        "cart_rate": Decimal("0.14486"),
                        "order_count": 96,
                        "cart_to_order_rate": Decimal("0.30967"),
                        "order_sum": Decimal("84300"),
                        "buyout_count": 61,
                        "buyout_sum": Decimal("58700"),
                    }
                ]
            )
        return _FakeResult(
            row={
                "products_at": datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc),
                "showcase_at": datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc),
                "prices_at": datetime(2026, 7, 27, 20, 3, tzinfo=timezone.utc),
                "rrp_at": datetime(2026, 7, 26, 23, 0, tzinfo=timezone.utc),
                "analytics_through": date(2026, 7, 27),
                "ctr_through": date(2026, 7, 27),
                "reviews_at": datetime(2026, 7, 27, 11, 54, tzinfo=timezone.utc),
            }
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self):
        self.connection = _FakeConnection()

    def connect(self):
        return self.connection


def test_catalog_query_serializes_metrics_and_applies_project_filters(monkeypatch):
    fake_engine = _FakeEngine()
    monkeypatch.setattr(db_wb_catalog, "engine", fake_engine)

    payload = db_wb_catalog.list_wb_catalog(
        project_id=1,
        period_from=date(2026, 7, 1),
        period_to=date(2026, 7, 27),
        q="SKU-123",
        activity="active",
        sort="order_sum",
        order="desc",
        page=1,
        page_size=50,
        ctr_mode="quality_filtered",
    )

    assert payload["meta"] == {
        "page": 1,
        "page_size": 50,
        "total": 1,
        "pages": 1,
        "period_from": "2026-07-01",
        "period_to": "2026-07-27",
    }
    item = payload["items"][0]
    assert item["nm_id"] == 123
    assert item["is_active"] is True
    assert item["showcase_price"] == 1490.0
    assert item["brand"] == ""
    assert item["subject_name"] == "Жакеты"
    assert item["sizes"] == [
        {"chrt_id": 7, "tech_size": "M", "wb_size": "46", "skus": ["123"]},
        {"chrt_id": 8, "tech_size": "L", "wb_size": "48", "skus": ["456"]},
    ]
    assert item["seller_discount_percent"] == 12.0
    assert item["rrp_price"] == 1990.0
    assert item["ctr_percent"] == pytest.approx(14.618)
    assert item["cart_rate"] == pytest.approx(0.14486)
    assert item["cart_to_order_rate"] == pytest.approx(0.30967)
    assert payload["data_freshness"]["analytics_through"] == "2026-07-27"

    count_sql, count_params = fake_engine.connection.calls[0]
    items_sql, items_params = fake_engine.connection.calls[1]
    assert "p.project_id = :project_id" in count_sql
    assert "FROM marketplace_products mp" in count_sql
    assert "legacy_product_fallback AS" in count_sql
    assert "FROM product_source p" in count_sql
    assert "sp.is_active IS TRUE" in count_sql
    assert "ILIKE :q_pattern" in count_sql
    assert count_params["project_id"] == 1
    assert count_params["q_pattern"] == "%SKU-123%"
    assert "REPORTED_CTR_MISMATCH" in items_sql
    assert "p.marketplace_product_id" in items_sql
    assert "seller_discount.seller_discount_percent" in items_sql
    assert items_params["period_from"] == date(2026, 7, 1)


def test_catalog_sort_clause_uses_allowlist():
    assert db_wb_catalog._sort_clause("title", "asc").startswith(
        "LOWER(COALESCE(pb.title, '')) ASC"
    )
    assert db_wb_catalog._sort_clause("not-a-column", "desc").startswith(
        "COALESCE(stats.order_sum, 0) DESC"
    )


def test_catalog_exact_product_filter_does_not_use_fuzzy_search():
    where_sql, params = db_wb_catalog._catalog_filters(
        "ignored",
        "all",
        exact_nm_id=123,
    )

    assert "p.nm_id = :exact_nm_id" in where_sql
    assert "ILIKE" not in where_sql
    assert params == {"exact_nm_id": 123}


def test_catalog_default_period_uses_latest_continuous_fact_segment(monkeypatch):
    class DatesConnection:
        def execute(self, statement, params):
            return _FakeResult(
                rows=[date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 25), date(2026, 7, 26)]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DatesEngine:
        def connect(self):
            return DatesConnection()

    monkeypatch.setattr(db_wb_catalog, "engine", DatesEngine())

    assert db_wb_catalog.get_catalog_default_period(3) == (date(2026, 7, 25), date(2026, 7, 26))


def test_catalog_product_endpoint_returns_404_when_product_is_missing(monkeypatch):
    monkeypatch.setattr(wb_catalog_router, "enforce_report_period", lambda *_args: None)
    monkeypatch.setattr(
        wb_catalog_router,
        "get_wb_catalog_product",
        lambda **_kwargs: None,
    )

    with pytest.raises(HTTPException) as missing:
        asyncio.run(
            wb_catalog_router.get_wb_catalog_product_endpoint(
                project_id=1,
                nm_id=123,
                period_from=date(2026, 7, 1),
                period_to=date(2026, 7, 27),
                ctr_mode="quality_filtered",
                _membership={},
            )
        )

    assert missing.value.status_code == 404


def test_catalog_endpoint_uses_available_default_period(monkeypatch):
    captured = {}
    monkeypatch.setattr(wb_catalog_router, "enforce_report_period", lambda *_args: None)

    monkeypatch.setattr(
        wb_catalog_router,
        "get_catalog_default_period",
        lambda project_id: (date(2026, 6, 28), date(2026, 7, 27)),
    )

    def _list(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "meta": {
                "page": 1,
                "page_size": 50,
                "total": 0,
                "pages": 0,
                "period_from": "2026-06-28",
                "period_to": "2026-07-27",
            },
            "data_freshness": {},
        }

    monkeypatch.setattr(wb_catalog_router, "list_wb_catalog", _list)

    asyncio.run(
        wb_catalog_router.get_wb_catalog(
            project_id=1,
            q=None,
            period_from=None,
            period_to=None,
            activity="active",
            sort="order_sum",
            order="desc",
            page=1,
            page_size=50,
            ctr_mode="quality_filtered",
            _membership={"project_id": 1},
        )
    )

    assert captured["period_from"] == date(2026, 6, 28)
    assert captured["period_to"] == date(2026, 7, 27)
    assert captured["project_id"] == 1


def test_catalog_endpoint_rejects_partial_or_reversed_period():
    with pytest.raises(HTTPException) as partial:
        asyncio.run(
            wb_catalog_router.get_wb_catalog(
                project_id=1,
                q=None,
                period_from=date(2026, 7, 1),
                period_to=None,
                activity="active",
                sort="order_sum",
                order="desc",
                page=1,
                page_size=50,
                ctr_mode="quality_filtered",
                _membership={},
            )
        )
    assert partial.value.status_code == 400

    with pytest.raises(HTTPException) as reversed_period:
        asyncio.run(
            wb_catalog_router.get_wb_catalog(
                project_id=1,
                q=None,
                period_from=date(2026, 7, 28),
                period_to=date(2026, 7, 1),
                activity="active",
                sort="order_sum",
                order="desc",
                page=1,
                page_size=50,
                ctr_mode="quality_filtered",
                _membership={},
            )
        )
    assert reversed_period.value.status_code == 400
