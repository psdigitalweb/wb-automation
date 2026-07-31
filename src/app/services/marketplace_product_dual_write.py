"""Best-effort mirror of the legacy WB product catalog into the neutral model."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from sqlalchemy import text

from app import settings
from app.db import engine


logger = logging.getLogger(__name__)


def _unique_nm_ids(rows: Iterable[Dict[str, Any]]) -> list[int]:
    return list(
        dict.fromkeys(
            int(row["nm_id"])
            for row in rows
            if row.get("nm_id") is not None and int(row["nm_id"]) > 0
        )
    )


def mirror_wb_products(*, project_id: int, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Mirror already-persisted legacy WB products in one idempotent statement."""
    nm_ids = _unique_nm_ids(rows)
    if not nm_ids:
        return {"status": "ok", "rows_requested": 0, "rows_upserted": 0}

    with engine.begin() as conn:
        connection = conn.execute(
            text(
                """
                SELECT COUNT(*)::integer AS connection_count, MIN(pm.id) AS connection_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                """
            ),
            {"project_id": int(project_id)},
        ).mappings().one()
        connection_count = int(connection["connection_count"] or 0)
        if connection_count != 1:
            status = "skipped_without_connection" if connection_count == 0 else "skipped_ambiguous_connection"
            return {
                "status": status,
                "rows_requested": len(nm_ids),
                "rows_upserted": 0,
                "connection_count": connection_count,
            }

        result = conn.execute(
            text(
                """
                INSERT INTO marketplace_products (
                    project_id,
                    project_marketplace_id,
                    marketplace_item_id,
                    marketplace_sku,
                    title,
                    attributes,
                    is_active,
                    first_seen_at,
                    last_seen_at
                )
                SELECT
                    p.project_id,
                    :connection_id,
                    p.nm_id::text,
                    NULLIF(btrim(p.vendor_code), ''),
                    p.title,
                    jsonb_strip_nulls(
                        jsonb_build_object(
                            'legacy_product_id', p.id,
                            'brand', p.brand,
                            'subject_id', p.subject_id,
                            'subject_name', p.subject_name
                        )
                    ),
                    TRUE,
                    COALESCE(p.first_seen_at, p.updated_at, now()),
                    COALESCE(p.updated_at, now())
                FROM products p
                WHERE p.project_id = :project_id
                  AND p.nm_id = ANY(:nm_ids)
                ON CONFLICT (project_marketplace_id, marketplace_item_id)
                DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    marketplace_sku = EXCLUDED.marketplace_sku,
                    title = EXCLUDED.title,
                    attributes = COALESCE(marketplace_products.attributes, '{}'::jsonb)
                        || EXCLUDED.attributes,
                    is_active = EXCLUDED.is_active,
                    first_seen_at = LEAST(marketplace_products.first_seen_at, EXCLUDED.first_seen_at),
                    last_seen_at = GREATEST(marketplace_products.last_seen_at, EXCLUDED.last_seen_at),
                    updated_at = now()
                """
            ),
            {
                "project_id": int(project_id),
                "connection_id": int(connection["connection_id"]),
                "nm_ids": nm_ids,
            },
        )
    return {
        "status": "ok",
        "rows_requested": len(nm_ids),
        "rows_upserted": int(result.rowcount or 0),
        "connection_count": connection_count,
    }


def mirror_wb_products_best_effort(
    *,
    project_id: int,
    rows: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run the optional mirror without allowing it to fail the legacy ingest."""
    if not settings.MARKETPLACE_PRODUCTS_DUAL_WRITE_ENABLED:
        return {"status": "disabled", "rows_requested": 0, "rows_upserted": 0}

    materialized_rows = list(rows)
    try:
        result = mirror_wb_products(project_id=project_id, rows=materialized_rows)
    except Exception:
        logger.exception(
            "Marketplace product mirror failed; legacy WB ingest remains committed "
            "project_id=%s rows_requested=%s",
            int(project_id),
            len(materialized_rows),
        )
        return {
            "status": "failed",
            "rows_requested": len(materialized_rows),
            "rows_upserted": 0,
        }

    if result["status"] != "ok":
        logger.warning(
            "Marketplace product mirror skipped project_id=%s status=%s connection_count=%s",
            int(project_id),
            result["status"],
            result.get("connection_count"),
        )
    return result
