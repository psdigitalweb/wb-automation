from app.services.wb_storefront_brands import (
    extract_frontend_brand_ids,
    extract_legacy_brand_id,
)


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
