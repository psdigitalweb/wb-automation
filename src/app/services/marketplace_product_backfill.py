"""Safe, idempotent backfill from the legacy WB catalog to marketplace products."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from app.db import engine


_PROJECT_FILTER = "AND p.project_id = :project_id"


def _project_filter(project_id: Optional[int]) -> str:
    return _PROJECT_FILTER if project_id is not None else ""


def backfill_wildberries_marketplace_products(
    *,
    project_id: Optional[int] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Plan or apply the legacy ``products`` -> ``marketplace_products`` backfill.

    Existing WB reads are intentionally unaffected. Projects without a
    Wildberries connection are reported and skipped; the backfill never creates
    or enables marketplace connections on behalf of a user.
    """
    params = {"project_id": int(project_id)} if project_id is not None else {}
    where_project = _project_filter(project_id)
    scope_sql = text(
        f"""
        WITH wb_connections AS (
            SELECT MIN(pm.id) AS id, pm.project_id, COUNT(*)::integer AS connection_count
            FROM project_marketplaces pm
            JOIN marketplaces m ON m.id = pm.marketplace_id
            WHERE m.code = 'wildberries'
            GROUP BY pm.project_id
        )
        SELECT
            COUNT(*)::bigint AS legacy_products,
            COUNT(*) FILTER (WHERE wb.connection_count = 1)::bigint AS eligible_products,
            COUNT(*) FILTER (WHERE wb.id IS NULL)::bigint AS skipped_without_connection,
            COUNT(*) FILTER (WHERE wb.connection_count > 1)::bigint AS skipped_ambiguous_connection,
            COUNT(*) FILTER (WHERE wb.connection_count = 1 AND mp.id IS NOT NULL)::bigint
                AS existing_marketplace_products
        FROM products p
        LEFT JOIN wb_connections wb ON wb.project_id = p.project_id
        LEFT JOIN marketplace_products mp
          ON mp.project_marketplace_id = wb.id
         AND mp.marketplace_item_id = p.nm_id::text
        WHERE 1 = 1
          {where_project}
        """
    )

    connection_context = engine.connect() if dry_run else engine.begin()
    with connection_context as conn:
        scope = conn.execute(scope_sql, params).mappings().one()
        result: Dict[str, Any] = {
            "dry_run": dry_run,
            "project_id": project_id,
            "legacy_products": int(scope["legacy_products"] or 0),
            "eligible_products": int(scope["eligible_products"] or 0),
            "skipped_without_connection": int(scope["skipped_without_connection"] or 0),
            "skipped_ambiguous_connection": int(scope["skipped_ambiguous_connection"] or 0),
            "existing_marketplace_products": int(scope["existing_marketplace_products"] or 0),
            "rows_upserted": 0,
        }
        if dry_run or result["eligible_products"] == 0:
            return result

        upsert_sql = text(
            f"""
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
                wb.id,
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
            JOIN (
                SELECT MIN(pm.id) AS id, pm.project_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE m.code = 'wildberries'
                GROUP BY pm.project_id
                HAVING COUNT(*) = 1
            ) wb ON wb.project_id = p.project_id
            WHERE 1 = 1
              {where_project}
            ON CONFLICT (project_marketplace_id, marketplace_item_id)
            DO UPDATE SET
                project_id = EXCLUDED.project_id,
                marketplace_sku = EXCLUDED.marketplace_sku,
                title = EXCLUDED.title,
                attributes = COALESCE(marketplace_products.attributes, '{{}}'::jsonb)
                    || EXCLUDED.attributes,
                is_active = EXCLUDED.is_active,
                first_seen_at = LEAST(marketplace_products.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = GREATEST(marketplace_products.last_seen_at, EXCLUDED.last_seen_at),
                updated_at = now()
            """
        )
        execution = conn.execute(upsert_sql, params)
        result["rows_upserted"] = int(execution.rowcount or 0)
        return result
