from app.services.wb_storefront_brands import (
    extract_frontend_brand_ids,
    extract_frontend_seller_id,
    extract_frontend_seller_url,
    extract_legacy_brand_id,
    extract_storefront_snapshot_scope,
    normalize_wb_seller_url,
    resolve_frontend_catalog_template,
)

import pytest

from app.ingest_frontend_prices import resolve_base_url


def test_normalize_wb_seller_url_extracts_id_and_canonicalizes_url():
    assert normalize_wb_seller_url("wildberries.ru/seller/4058267/") == (
        "https://www.wildberries.ru/seller/4058267",
        4058267,
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/seller/4058267",
        "https://wildberries.ru/catalog/4058267",
        "https://wildberries.ru/seller/not-a-number",
    ],
)
def test_normalize_wb_seller_url_rejects_invalid_links(value):
    with pytest.raises(ValueError):
        normalize_wb_seller_url(value)


def test_seller_configuration_takes_precedence_over_legacy_brands():
    settings = {
        "brand_id": 111,
        "frontend_prices": {
            "seller_url": "https://www.wildberries.ru/seller/4058267",
            "seller_id": 4058267,
            "brands": [{"brand_id": 222, "enabled": True}],
        },
    }

    assert extract_frontend_seller_id(settings) == 4058267
    assert extract_frontend_seller_url(settings) == "https://www.wildberries.ru/seller/4058267"
    assert extract_frontend_brand_ids(settings) == [4058267]


def test_resolve_base_url_supports_seller_template():
    template = "https://catalog.wb.ru/sellers/v4/catalog?supplier={seller_id}&page={page}"

    assert resolve_base_url(template, 4058267) == (
        "https://catalog.wb.ru/sellers/v4/catalog?supplier=4058267&page={page}"
    )


def test_seller_storefront_ignores_stale_saved_catalog_template():
    settings = {"frontend_prices": {"seller_id": 4058267}}

    resolved = resolve_frontend_catalog_template(
        settings,
        "https://catalog.wb.ru/sellers/v2/catalog?supplier={seller_id}&page={page}",
    )

    assert "/sellers/v4/catalog" in resolved


def test_extract_frontend_brand_ids_prefers_enabled_multi_brand_settings():
    settings = {
        "brand_id": 111,
        "frontend_prices": {
            "brands": [
                {"brand_id": 222, "enabled": True},
                {"brand_id": "333"},
                {"brand_id": 444, "enabled": False},
                {"brand_id": "bad"},
                {"brand_id": 222},
            ]
        },
    }

    assert extract_frontend_brand_ids(settings) == [222, 333]
    assert extract_legacy_brand_id(settings) == 111


def test_extract_frontend_brand_ids_falls_back_to_legacy_brand_id():
    settings = {"brand_id": "41189", "frontend_prices": {"brands": []}}

    assert extract_frontend_brand_ids(settings) == [41189]


def test_extract_frontend_brand_ids_returns_empty_without_valid_storefront_scope():
    settings = {"brand_id": 0, "frontend_prices": {"brands": [{"brand_id": -1}]}}

    assert extract_frontend_brand_ids(settings) == []


def test_seller_source_selects_seller_snapshot_scope():
    scope = extract_storefront_snapshot_scope(
        {
            "brand_id": 111,
            "frontend_prices": {
                "source_type": "seller",
                "seller_id": 4058267,
                "brands": [{"brand_id": 4058267, "enabled": True}],
            },
        }
    )

    assert scope.query_type == "seller"
    assert scope.query_values == ["4058267"]


def test_legacy_configuration_keeps_brand_snapshot_scope():
    scope = extract_storefront_snapshot_scope(
        {
            "brand_id": 111,
            "frontend_prices": {
                "brands": [{"brand_id": 222, "enabled": True}],
            },
        }
    )

    assert scope.query_type == "brand"
    assert scope.query_values == ["222"]
