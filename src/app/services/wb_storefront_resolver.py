"""Read-only discovery and verification for a public WB seller storefront."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text

from app.db import engine
from app.ingest_frontend_prices import extract_products_from_response
from app.services.project_proxy import get_frontend_prices_proxy_config
from app.services.wb_storefront_brands import (
    WB_SELLER_CATALOG_URL_TEMPLATE,
    normalize_wb_seller_url,
)
from app.utils.httpx_client import make_async_client


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.wildberries.ru/",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _integer(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _base_result(*, seller_url: str, seller_id: int, proxy_configured: bool) -> dict[str, Any]:
    return {
        "verified": False,
        "seller_url": seller_url,
        "seller_id": seller_id,
        "seller_name": None,
        "proxy_configured": proxy_configured,
        "http_status": None,
        "storefront_products_count": 0,
        "cabinet_products_count": 0,
        "matched_products_count": 0,
        "coverage_percent": 0.0,
        "sample_products": [],
        "error_code": None,
        "message": None,
        "verification_source": None,
        "verified_at": None,
    }


def _complete_verification(
    *,
    result: dict[str, Any],
    products: list[dict[str, Any]],
    project_id: int,
    seller_id: int,
    verification_source: str,
    verified_at: Any = None,
) -> dict[str, Any] | None:
    normalized_products: list[dict[str, Any]] = []
    returned_seller_ids: set[int] = set()
    for product in products:
        nm_id = _integer(product.get("id") or product.get("nmId") or product.get("nm_id"))
        if nm_id is None:
            continue
        product_seller_id = _integer(product.get("supplierId") or product.get("supplier_id"))
        if product_seller_id is not None:
            returned_seller_ids.add(product_seller_id)
        normalized_products.append(
            {
                "nm_id": nm_id,
                "title": str(product.get("name") or "").strip() or None,
                "brand": str(product.get("brand") or "").strip() or None,
            }
        )
    if not normalized_products:
        return None
    if returned_seller_ids and returned_seller_ids != {seller_id}:
        return {
            **result,
            "storefront_products_count": len(normalized_products),
            "error_code": "seller_id_mismatch",
            "message": "Ответ Wildberries относится к другому продавцу.",
        }

    storefront_nm_ids = {item["nm_id"] for item in normalized_products}
    with engine.connect() as conn:
        cabinet_nm_ids = {
            int(row[0])
            for row in conn.execute(
                text("SELECT nm_id FROM products WHERE project_id = :project_id"),
                {"project_id": int(project_id)},
            )
        }
    matched = storefront_nm_ids & cabinet_nm_ids
    seller_name = next(
        (
            str(product.get("supplier") or "").strip()
            for product in products
            if str(product.get("supplier") or "").strip()
        ),
        None,
    )
    coverage = round(len(matched) / len(cabinet_nm_ids) * 100, 1) if cabinet_nm_ids else 0.0
    message = (
        "Витрина подтверждена по последнему успешному снимку; Wildberries временно ограничил live-проверку."
        if verification_source == "cached_snapshot"
        else "Витрина доступна и соответствует указанному продавцу."
    )
    return {
        **result,
        "verified": True,
        "seller_name": seller_name,
        "storefront_products_count": len(storefront_nm_ids),
        "cabinet_products_count": len(cabinet_nm_ids),
        "matched_products_count": len(matched),
        "coverage_percent": coverage,
        "sample_products": normalized_products[:5],
        "message": message,
        "verification_source": verification_source,
        "verified_at": verified_at.isoformat() if hasattr(verified_at, "isoformat") else verified_at,
    }


def _resolve_cached_snapshot(
    *,
    result: dict[str, Any],
    project_id: int,
    seller_id: int,
) -> dict[str, Any] | None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT f.raw, f.snapshot_at
                FROM frontend_catalog_price_snapshots f
                JOIN ingest_runs r ON r.id = f.ingest_run_id
                WHERE r.project_id = :project_id
                  AND r.status = 'success'
                  AND f.query_value = :seller_id
                  AND f.snapshot_at = (
                      SELECT MAX(f2.snapshot_at)
                      FROM frontend_catalog_price_snapshots f2
                      JOIN ingest_runs r2 ON r2.id = f2.ingest_run_id
                      WHERE r2.project_id = :project_id
                        AND r2.status = 'success'
                        AND f2.query_value = :seller_id
                  )
                """
            ),
            {"project_id": int(project_id), "seller_id": str(seller_id)},
        ).mappings().all()
    products = [row["raw"] for row in rows if isinstance(row.get("raw"), dict)]
    verified_at = rows[0].get("snapshot_at") if rows else None
    return _complete_verification(
        result=result,
        products=products,
        project_id=project_id,
        seller_id=seller_id,
        verification_source="cached_snapshot",
        verified_at=verified_at,
    )


async def resolve_wb_storefront(*, project_id: int, seller_url: str) -> dict[str, Any]:
    canonical_url, seller_id = normalize_wb_seller_url(seller_url)
    try:
        proxy_url, _ = get_frontend_prices_proxy_config(int(project_id))
    except Exception:
        result = _base_result(
            seller_url=canonical_url,
            seller_id=seller_id,
            proxy_configured=True,
        )
        return {
            **result,
            "error_code": "proxy_configuration_error",
            "message": "Прокси настроен некорректно. Проверьте настройки прокси проекта.",
        }

    result = _base_result(
        seller_url=canonical_url,
        seller_id=seller_id,
        proxy_configured=bool(proxy_url),
    )
    catalog_url = (
        WB_SELLER_CATALOG_URL_TEMPLATE.replace("{seller_id}", str(seller_id))
        .replace("{brand_id}", str(seller_id))
        .replace("{page}", "1")
    )
    timeout_seconds = 60.0 if proxy_url else 30.0
    timeout = httpx.Timeout(
        timeout_seconds,
        connect=timeout_seconds,
        read=timeout_seconds,
        write=timeout_seconds,
        pool=timeout_seconds,
    )

    try:
        async with make_async_client(
            proxy_url=proxy_url,
            timeout=timeout,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            response = await client.get(catalog_url)
    except Exception as exc:
        return {
            **result,
            "error_code": "storefront_network_error",
            "message": f"Не удалось получить витрину: {type(exc).__name__}",
        }

    result["http_status"] = int(response.status_code)
    if response.status_code != 200:
        if response.status_code == 429:
            cached = _resolve_cached_snapshot(
                result=result,
                project_id=int(project_id),
                seller_id=seller_id,
            )
            if cached is not None:
                return cached
        error_code = "proxy_required" if response.status_code == 403 and not proxy_url else "storefront_http_error"
        message = (
            "Wildberries не отдал витрину напрямую. Подключите прокси проекта и повторите проверку."
            if error_code == "proxy_required"
            else f"Wildberries вернул HTTP {response.status_code}. Повторите проверку позже."
        )
        return {**result, "error_code": error_code, "message": message}

    try:
        payload = response.json()
    except Exception:
        return {
            **result,
            "error_code": "invalid_storefront_response",
            "message": "Wildberries вернул некорректный ответ витрины.",
        }

    products = extract_products_from_response(payload if isinstance(payload, dict) else {})
    completed = _complete_verification(
        result=result,
        products=products,
        project_id=int(project_id),
        seller_id=seller_id,
        verification_source="live",
    )
    if completed is None:
        return {
            **result,
            "error_code": "empty_storefront",
            "message": "По этой ссылке Wildberries не вернул товары продавца.",
        }
    return completed
