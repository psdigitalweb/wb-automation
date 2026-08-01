"""Helpers for project-scoped WB storefront brand configuration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from app.db import engine


WB_SELLER_PATH_RE = re.compile(r"^/seller/(?P<seller_id>[1-9][0-9]*)/?$")
WB_SELLER_CATALOG_URL_TEMPLATE = (
    "https://catalog.wb.ru/sellers/v4/catalog?appType=1&curr=rub&dest=-1257786"
    "&lang=ru&page={page}&sort=popular&spp=30&supplier={seller_id}"
)


@dataclass(frozen=True)
class StorefrontSnapshotScope:
    query_type: str
    query_values: list[str]


def extract_storefront_snapshot_scope(settings: Any) -> StorefrontSnapshotScope:
    """Resolve the snapshot source selected for a project's storefront reports."""
    settings_dict = normalize_settings_json(settings)
    frontend_prices = settings_dict.get("frontend_prices")
    seller_id = extract_frontend_seller_id(settings_dict)
    source_type = (
        str(frontend_prices.get("source_type") or "").strip().lower()
        if isinstance(frontend_prices, dict)
        else ""
    )
    if seller_id is not None and source_type == "seller":
        return StorefrontSnapshotScope(query_type="seller", query_values=[str(seller_id)])

    brand_ids: list[int] = []
    if isinstance(frontend_prices, dict) and isinstance(frontend_prices.get("brands"), list):
        for brand in frontend_prices["brands"]:
            if not isinstance(brand, dict) or brand.get("enabled", True) is False:
                continue
            brand_id = _coerce_positive_int(brand.get("brand_id"))
            if brand_id is not None and brand_id not in brand_ids:
                brand_ids.append(brand_id)
    legacy_brand_id = extract_legacy_brand_id(settings_dict)
    if not brand_ids and legacy_brand_id is not None:
        brand_ids.append(legacy_brand_id)
    return StorefrontSnapshotScope(
        query_type="brand",
        query_values=[str(brand_id) for brand_id in brand_ids],
    )


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


def normalize_wb_seller_url(value: Any) -> tuple[str, int]:
    """Validate a public WB seller URL and return its canonical URL and seller id."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Укажите ссылку на продавца Wildberries")
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    hostname = (parsed.hostname or "").lower()
    if hostname != "wildberries.ru" and not hostname.endswith(".wildberries.ru"):
        raise ValueError("Ссылка должна вести на wildberries.ru/seller/ID")

    match = WB_SELLER_PATH_RE.fullmatch(parsed.path)
    if match is None:
        raise ValueError("Ожидается ссылка вида https://www.wildberries.ru/seller/4058267")

    seller_id = int(match.group("seller_id"))
    return f"https://www.wildberries.ru/seller/{seller_id}", seller_id


def extract_frontend_seller_id(settings: Any) -> int | None:
    settings_dict = normalize_settings_json(settings)
    frontend_prices = settings_dict.get("frontend_prices")
    if not isinstance(frontend_prices, dict):
        return None
    return _coerce_positive_int(frontend_prices.get("seller_id"))


def extract_frontend_seller_url(settings: Any) -> str | None:
    settings_dict = normalize_settings_json(settings)
    frontend_prices = settings_dict.get("frontend_prices")
    if not isinstance(frontend_prices, dict):
        return None
    try:
        canonical_url, _ = normalize_wb_seller_url(frontend_prices.get("seller_url"))
    except ValueError:
        seller_id = _coerce_positive_int(frontend_prices.get("seller_id"))
        return f"https://www.wildberries.ru/seller/{seller_id}" if seller_id is not None else None
    return canonical_url


def resolve_frontend_catalog_template(settings: Any, configured_template: Any = None) -> str:
    """Use the maintained seller template for seller-based storefronts."""
    if extract_frontend_seller_id(settings) is not None:
        return WB_SELLER_CATALOG_URL_TEMPLATE
    return str(configured_template or "").strip()


def extract_frontend_brand_ids(settings: Any) -> list[int]:
    """Return enabled storefront brand ids, preferring multi-brand settings.

    Legacy ``settings_json.brand_id`` remains supported as a fallback only when
    ``frontend_prices.brands`` has no enabled valid brand ids.
    """
    settings_dict = normalize_settings_json(settings)
    frontend_prices = settings_dict.get("frontend_prices")
    brand_ids: list[int] = []

    seller_id = extract_frontend_seller_id(settings_dict)
    if seller_id is not None:
        # The snapshot/report layer still calls this value brand_id/query_value.
        # Keep that storage contract while the configured storefront source is seller-based.
        return [seller_id]

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


def get_project_storefront_snapshot_scope(project_id: int) -> StorefrontSnapshotScope:
    """Load the selected storefront snapshot scope for report queries."""
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
    return extract_storefront_snapshot_scope((row or {}).get("settings_json"))


def get_project_storefront_snapshot_params(project_id: int) -> dict[str, Any]:
    """Return conventional bind parameters used by storefront report SQL."""
    scope = get_project_storefront_snapshot_scope(project_id)
    return {
        "storefront_query_type": scope.query_type,
        "brand_ids": scope.query_values,
    }


def get_project_frontend_brand_id_strings(project_id: int) -> list[str]:
    return [str(brand_id) for brand_id in get_project_frontend_brand_ids(project_id)]
