"""Helpers for project-scoped WB storefront brand configuration."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.db import engine


def _coerce_positive_int(value: Any) -> int | None:
    try:
        brand_id = int(value)
    except (TypeError, ValueError):
        return None
    return brand_id if brand_id > 0 else None


def normalize_settings_json(settings: Any) -> dict[str, Any]:
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except (TypeError, ValueError):
            return {}
    return settings if isinstance(settings, dict) else {}


def extract_frontend_brand_ids(settings: Any) -> list[int]:
    """Return enabled storefront brand ids, preferring multi-brand settings.

    Legacy ``settings_json.brand_id`` remains supported as a fallback only when
    ``frontend_prices.brands`` has no enabled valid brand ids.
    """
    settings_dict = normalize_settings_json(settings)
    frontend_prices = settings_dict.get("frontend_prices")
    brand_ids: list[int] = []

    if isinstance(frontend_prices, dict) and isinstance(frontend_prices.get("brands"), list):
        seen: set[int] = set()
        for brand in frontend_prices["brands"]:
            if not isinstance(brand, dict) or brand.get("enabled", True) is False:
                continue
            brand_id = _coerce_positive_int(brand.get("brand_id"))
            if brand_id is not None and brand_id not in seen:
                seen.add(brand_id)
                brand_ids.append(brand_id)

    if brand_ids:
        return brand_ids

    legacy_brand_id = _coerce_positive_int(settings_dict.get("brand_id"))
    return [legacy_brand_id] if legacy_brand_id is not None else []


def extract_legacy_brand_id(settings: Any) -> int | None:
    settings_dict = normalize_settings_json(settings)
    return _coerce_positive_int(settings_dict.get("brand_id"))


def get_project_frontend_brand_ids(project_id: int) -> list[int]:
    """Load enabled WB storefront brand ids for a project."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT pm.settings_json
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).mappings().first()
    return extract_frontend_brand_ids((row or {}).get("settings_json"))


def get_project_frontend_brand_id_strings(project_id: int) -> list[str]:
    return [str(brand_id) for brand_id in get_project_frontend_brand_ids(project_id)]
