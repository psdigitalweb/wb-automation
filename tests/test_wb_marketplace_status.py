from __future__ import annotations

import asyncio
from datetime import datetime

from app.routers import marketplaces as marketplaces_router


def test_wb_status_v2_token_without_brand_is_configured_but_not_storefront(monkeypatch):
    monkeypatch.setattr(
        marketplaces_router,
        "get_marketplace_by_code",
        lambda code: {"id": 1, "code": code},
    )
    monkeypatch.setattr(
        marketplaces_router,
        "get_project_marketplace",
        lambda project_id, marketplace_id: {
            "is_enabled": True,
            "api_token_encrypted": "encrypted",
            "settings_json": {},
            "updated_at": datetime(2026, 1, 1),
        },
    )

    result = asyncio.run(
        marketplaces_router.get_wb_marketplace_status_v2_endpoint(
            project_id=1,
            current_user={"id": 1},
            membership={"project_id": 1},
        )
    )

    assert result.is_enabled is True
    assert result.is_configured is True
    assert result.credentials.api_token is True
    assert result.storefront_configured is False
    assert result.storefront_brand_ids == []


def test_wb_status_v2_reports_enabled_storefront_brands(monkeypatch):
    monkeypatch.setattr(
        marketplaces_router,
        "get_marketplace_by_code",
        lambda code: {"id": 1, "code": code},
    )
    monkeypatch.setattr(
        marketplaces_router,
        "get_project_marketplace",
        lambda project_id, marketplace_id: {
            "is_enabled": True,
            "api_token_encrypted": "encrypted",
            "settings_json": {
                "brand_id": 100,
                "frontend_prices": {
                    "brands": [
                        {"brand_id": 200, "enabled": True},
                        {"brand_id": 300, "enabled": False},
                    ]
                },
            },
            "updated_at": datetime(2026, 1, 1),
        },
    )

    result = asyncio.run(
        marketplaces_router.get_wb_marketplace_status_v2_endpoint(
            project_id=1,
            current_user={"id": 1},
            membership={"project_id": 1},
        )
    )

    assert result.is_configured is True
    assert result.settings.brand_id == 100
    assert result.legacy_brand_id == 100
    assert result.storefront_configured is True
    assert result.storefront_brand_ids == [200]


def test_wb_token_validation_reports_missing_token(monkeypatch):
    monkeypatch.setattr(marketplaces_router, "get_wb_token_for_project", lambda project_id: None)

    result = asyncio.run(
        marketplaces_router.validate_wb_marketplace_token_endpoint(
            project_id=1,
            current_user={"id": 1},
            membership={"project_id": 1},
        )
    )

    assert result.valid is False
    assert result.has_token is False
    assert "not saved" in result.message


def test_wb_token_validation_calls_wb_validator(monkeypatch):
    async def fake_validate(token: str):
        assert token == "saved-token"
        return True, None

    monkeypatch.setattr(
        marketplaces_router, "get_wb_token_for_project", lambda project_id: "saved-token"
    )
    monkeypatch.setattr(marketplaces_router, "validate_wb_token", fake_validate)

    result = asyncio.run(
        marketplaces_router.validate_wb_marketplace_token_endpoint(
            project_id=1,
            current_user={"id": 1},
            membership={"project_id": 1},
        )
    )

    assert result.valid is True
    assert result.has_token is True
    assert result.message is None


def test_wb_token_validation_returns_validator_error(monkeypatch):
    async def fake_validate(token: str):
        return False, "Invalid token: Unauthorized (401)"

    monkeypatch.setattr(
        marketplaces_router, "get_wb_token_for_project", lambda project_id: "bad-token"
    )
    monkeypatch.setattr(marketplaces_router, "validate_wb_token", fake_validate)

    result = asyncio.run(
        marketplaces_router.validate_wb_marketplace_token_endpoint(
            project_id=1,
            current_user={"id": 1},
            membership={"project_id": 1},
        )
    )

    assert result.valid is False
    assert result.has_token is True
    assert result.message == "Invalid token: Unauthorized (401)"
