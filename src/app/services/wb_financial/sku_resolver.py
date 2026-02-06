"""Resolve nm_id -> internal_sku using existing project logic.

Uses:
  1) internal_product_identifiers (marketplace_code='wildberries', marketplace_item_id=nm_id)
     + latest internal_data_snapshot success|partial -> internal_products.internal_sku
  2) fallback: products(project_id, nm_id).vendor_code_norm
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def resolve_internal_skus_bulk(
    project_id: int,
    nm_ids: List[int],
) -> Dict[int, str]:
    """Bulk resolve nm_id -> internal_sku. Returns {nm_id: internal_sku}."""
    if not nm_ids:
        return {}
    nm_ids = list(set(nm_ids))
    nm_id_strs = [str(x) for x in nm_ids]

    with engine.connect() as conn:
        all_rows = conn.execute(
            text("""
                WITH latest_snapshot AS (
                    SELECT id AS snapshot_id
                    FROM internal_data_snapshots
                    WHERE project_id = :project_id
                      AND status IN ('success', 'partial')
                    ORDER BY imported_at DESC NULLS LAST
                    LIMIT 1
                ),
                from_identifiers AS (
                    SELECT DISTINCT ON (ipi.marketplace_item_id::bigint)
                        ipi.marketplace_item_id::bigint AS nm_id,
                        ip.internal_sku
                    FROM internal_product_identifiers ipi
                    JOIN internal_products ip ON ip.id = ipi.internal_product_id
                        AND ip.snapshot_id = ipi.snapshot_id
                    CROSS JOIN latest_snapshot ls
                    WHERE ipi.project_id = :project_id
                      AND ipi.snapshot_id = ls.snapshot_id
                      AND ipi.marketplace_code = 'wildberries'
                      AND ipi.marketplace_item_id ~ '^[0-9]+$'
                      AND ipi.marketplace_item_id = ANY(:nm_id_strs)
                    ORDER BY ipi.marketplace_item_id::bigint, ipi.id DESC
                ),
                from_products AS (
                    SELECT nm_id, vendor_code_norm AS internal_sku
                    FROM products
                    WHERE project_id = :project_id
                      AND nm_id = ANY(:nm_ids)
                      AND vendor_code_norm IS NOT NULL
                )
                SELECT DISTINCT ON (nm_id) nm_id, internal_sku
                FROM (
                    SELECT nm_id, internal_sku, 0 AS ord FROM from_identifiers
                    UNION ALL
                    SELECT nm_id, internal_sku, 1 AS ord FROM from_products
                ) u
                ORDER BY nm_id, ord
            """),
            {"project_id": project_id, "nm_ids": nm_ids, "nm_id_strs": nm_id_strs},
        ).mappings().all()

    result: Dict[int, str] = {}
    seen: set = set()
    for r in all_rows:
        nid = r.get("nm_id")
        if nid is not None and nid not in seen:
            sku = r.get("internal_sku")
            if sku:
                result[int(nid)] = sku
                seen.add(nid)
    return result


def resolve_internal_sku(project_id: int, nm_id: Optional[int]) -> Optional[str]:
    """Resolve nm_id to internal_sku.

    Primary: internal_product_identifiers.marketplace_item_id -> internal_products.internal_sku
    Fallback: products.vendor_code_norm

    Returns None if nm_id is None or no mapping found.
    """
    if nm_id is None:
        return None

    # 1) Try internal_product_identifiers
    sql_ident = text(
        """
        SELECT ip.internal_sku
        FROM internal_product_identifiers ipi
        JOIN internal_products ip ON ip.id = ipi.internal_product_id
            AND ip.snapshot_id = ipi.snapshot_id
        JOIN internal_data_snapshots ids ON ids.id = ipi.snapshot_id
        WHERE ipi.project_id = :project_id
          AND ipi.marketplace_code = 'wildberries'
          AND ipi.marketplace_item_id IS NOT NULL
          AND ipi.marketplace_item_id ~ '^[0-9]+$'
          AND ipi.marketplace_item_id = :nm_id_str
          AND ids.status IN ('success', 'partial')
        ORDER BY ids.imported_at DESC NULLS LAST
        LIMIT 1
        """
    )
    nm_id_str = str(nm_id)
    with engine.connect() as conn:
        row = conn.execute(
            sql_ident,
            {"project_id": project_id, "nm_id_str": nm_id_str},
        ).mappings().first()
    if row and row.get("internal_sku"):
        return row["internal_sku"]

    # 2) Fallback: products.vendor_code_norm
    sql_prod = text(
        """
        SELECT vendor_code_norm AS internal_sku
        FROM products
        WHERE project_id = :project_id
          AND nm_id = :nm_id
          AND vendor_code_norm IS NOT NULL
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql_prod,
            {"project_id": project_id, "nm_id": nm_id},
        ).mappings().first()
    return row["internal_sku"] if row and row.get("internal_sku") else None
