"""Resolve nm_id -> internal_sku using existing project logic.

Uses:
  1) internal_product_identifiers (marketplace_code='wildberries', marketplace_item_id=nm_id)
     + latest internal_data_snapshot success|partial -> internal_products.internal_sku
  2) fallback: products(project_id, nm_id).vendor_code_norm
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from app.db import engine


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
