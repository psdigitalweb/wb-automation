"""Resolve nm_id -> internal_sku using existing project logic.

Uses:
  1) confirmed marketplace_product_mappings
  2) internal_product_identifiers (marketplace_code='wildberries', marketplace_item_id=nm_id)
     + latest internal_data_snapshot success|partial -> internal_products.internal_sku
  3) marketplace_products.marketplace_sku (does not require the manual catalog)
  4) legacy fallback: products(project_id, nm_id).vendor_code_norm
"""
from __future__ import annotations

from typing import Dict, List, Optional

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

    nm_id_str = str(nm_id)
    sql_canonical_mapping = text(
        """
        SELECT icp.internal_sku
        FROM marketplace_products mp
        JOIN project_marketplaces pm
          ON pm.id = mp.project_marketplace_id
         AND pm.project_id = mp.project_id
        JOIN marketplaces m ON m.id = pm.marketplace_id
        JOIN marketplace_product_mappings mapping
          ON mapping.marketplace_product_id = mp.id
         AND mapping.project_id = mp.project_id
         AND mapping.mapping_status = 'confirmed'
        JOIN internal_catalog_products icp
          ON icp.id = mapping.internal_catalog_product_id
         AND icp.project_id = mapping.project_id
        WHERE mp.project_id = :project_id
          AND m.code = 'wildberries'
          AND mp.marketplace_item_id = :nm_id_str
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql_canonical_mapping,
            {"project_id": project_id, "nm_id_str": nm_id_str},
        ).mappings().first()
    if row and row.get("internal_sku"):
        return row["internal_sku"]

    # 2) Try legacy internal_product_identifiers
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
    with engine.connect() as conn:
        row = conn.execute(
            sql_ident,
            {"project_id": project_id, "nm_id_str": nm_id_str},
        ).mappings().first()
    if row and row.get("internal_sku"):
        return row["internal_sku"]

    # 3) Canonical marketplace product. This exists after marketplace ingest even
    # when the optional internal catalog was never uploaded.
    sql_marketplace_product = text(
        """
        SELECT mp.marketplace_sku AS internal_sku
        FROM marketplace_products mp
        JOIN project_marketplaces pm
          ON pm.id = mp.project_marketplace_id
         AND pm.project_id = mp.project_id
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE mp.project_id = :project_id
          AND m.code = 'wildberries'
          AND mp.marketplace_item_id = :nm_id_str
          AND NULLIF(btrim(mp.marketplace_sku), '') IS NOT NULL
        ORDER BY mp.id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql_marketplace_product,
            {"project_id": project_id, "nm_id_str": nm_id_str},
        ).mappings().first()
    if row and row.get("internal_sku"):
        return row["internal_sku"]

    # 4) Legacy fallback during the compatibility period.
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


def resolve_internal_skus_bulk(
    project_id: int,
    nm_ids: List[Optional[int]],
) -> Dict[int, Optional[str]]:
    """Resolve multiple nm_ids to internal_sku. Returns dict nm_id -> internal_sku."""
    result: Dict[int, Optional[str]] = {}
    seen: set = set()
    for nm_id in nm_ids:
        if nm_id is None or nm_id in seen:
            continue
        seen.add(nm_id)
        result[nm_id] = resolve_internal_sku(project_id, nm_id)
    return result
