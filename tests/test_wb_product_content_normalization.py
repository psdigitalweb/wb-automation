from __future__ import annotations

from copy import deepcopy

from app.services.wb_product_content.normalization import (
    build_content_diff,
    content_hash,
    main_photo_url,
    normalize_wb_card_content,
)


def _card() -> dict:
    return {
        "nmID": 123,
        "vendorCode": "  SKU-1 ",
        "title": "  Тестовый   товар ",
        "brand": "Brand",
        "subjectID": 42,
        "subjectName": "Футболки",
        "description": "Строка 1\r\nСтрока   2",
        "dimensions": {"width": 10, "height": 20},
        "characteristics": [
            {"id": 2, "name": "Материал", "value": ["хлопок"]},
            {"id": 1, "name": "Цвет", "value": ["белый"]},
        ],
        "sizes": [
            {
                "chrtID": 777,
                "techSize": "M",
                "wbSize": "44",
                "skus": ["BARCODE-MUST-NOT-BE-VERSIONED"],
            }
        ],
        "photos": [
            {"big": "https://basket-01.wbbasket.ru/a.jpg"},
            {"big": "https://basket-01.wbbasket.ru/b.jpg"},
        ],
        "needKiz": False,
        "updatedAt": "2026-07-27T12:00:00Z",
        "price": 100,
        "rating": 5,
    }


def test_hash_ignores_characteristic_order_barcodes_prices_and_metadata():
    first = _card()
    second = deepcopy(first)
    second["characteristics"].reverse()
    second["sizes"][0]["skus"] = ["OTHER"]
    second["price"] = 999
    second["rating"] = 1
    second["updatedAt"] = "2026-07-28T12:00:00Z"

    assert content_hash(normalize_wb_card_content(first)) == content_hash(
        normalize_wb_card_content(second)
    )


def test_photo_order_changes_hash_and_reports_main_change():
    first = normalize_wb_card_content(_card())
    changed_card = _card()
    changed_card["photos"].reverse()
    second = normalize_wb_card_content(changed_card)

    changes, change_types = build_content_diff(first, second)

    assert content_hash(first) != content_hash(second)
    assert changes["photos"]["mainChanged"] is True
    assert changes["photos"]["orderChanged"] is True
    assert change_types == ["media"]


def test_text_is_normalized_and_main_photo_uses_largest_known_url():
    content = normalize_wb_card_content(_card())

    assert content["title"] == "Тестовый товар"
    assert content["description"] == "Строка 1\nСтрока 2"
    assert content["sizes"] == [{"chrtID": 777, "techSize": "M", "wbSize": "44"}]
    assert main_photo_url(content) == "https://basket-01.wbbasket.ru/a.jpg"


def test_change_diff_classifies_content_and_dimensions():
    first = normalize_wb_card_content(_card())
    changed_card = _card()
    changed_card["title"] = "Другое название"
    changed_card["dimensions"]["width"] = 11
    second = normalize_wb_card_content(changed_card)

    changes, change_types = build_content_diff(first, second)

    assert set(changes) == {"title", "dimensions"}
    assert change_types == ["content", "dimensions"]
