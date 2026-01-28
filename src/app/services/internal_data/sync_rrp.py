"""Sync Internal Data RRP to rrp_snapshots table.

This module provides functionality to synchronize RRP prices from internal_product_prices
to rrp_snapshots table, which is used by the price discrepancies report.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy import text

from app.db import engine

logger = logging.getLogger(__name__)


def sync_internal_data_to_rrp_snapshots(project_id: int) -> Dict[str, Any]:
    """Sync RRP prices from internal_product_prices to rrp_snapshots.
    
    This function:
    1. Finds the latest internal_data_snapshot for the project
    2. Extracts RRP prices from internal_product_prices
    3. Maps internal_sku to vendor_code_norm via products table
    4. Inserts/updates rrp_snapshots with snapshot_at = now()
    
    Returns:
        Dict with sync statistics (rows_synced, rows_skipped, errors)
    """
    logger.info(f"sync_internal_data_to_rrp_snapshots: starting for project_id={project_id}")
    start_time = datetime.now(timezone.utc)
    
    stats = {
        "project_id": project_id,
        "started_at": start_time.isoformat(),
        "rows_synced": 0,
        "rows_skipped": 0,
        "errors": [],
    }
    
    try:
        with engine.begin() as conn:
            # Get latest internal_data_snapshot for this project
            latest_snapshot = conn.execute(
                text("""
                    SELECT id, imported_at, project_id
                    FROM internal_data_snapshots
                    WHERE project_id = :project_id
                    ORDER BY imported_at DESC
                    LIMIT 1
                """),
                {"project_id": project_id},
            ).mappings().first()
            
            if not latest_snapshot:
                logger.warning(
                    f"sync_internal_data_to_rrp_snapshots: no internal_data_snapshots found "
                    f"for project_id={project_id}"
                )
                stats["errors"].append("No internal_data_snapshots found for this project")
                return stats
            
            snapshot_id = latest_snapshot["id"]
            logger.info(
                f"sync_internal_data_to_rrp_snapshots: using snapshot_id={snapshot_id} "
                f"imported_at={latest_snapshot['imported_at']}"
            )
            
            # Extract RRP prices with mapping to products.vendor_code_norm
            # Only sync rows where:
            # - internal_product_prices.rrp IS NOT NULL
            # - internal_products.internal_sku matches products.vendor_code_norm
            # - products.project_id matches
            rrp_rows = conn.execute(
                text("""
                    SELECT DISTINCT
                        :project_id AS project_id,
                        NOW() AS snapshot_at,
                        ip.internal_sku AS vendor_code_raw,
                        ip.internal_sku AS vendor_code_norm,
                        NULL AS barcode,
                        ipp.rrp AS rrp_price,
                        NULL AS rrp_stock,
                        'internal_data_sync' AS source_file
                    FROM internal_product_prices ipp
                    JOIN internal_products ip ON ipp.internal_product_id = ip.id
                    JOIN internal_data_snapshots ids ON ipp.snapshot_id = ids.id
                    JOIN products p ON p.vendor_code_norm = ip.internal_sku
                        AND p.project_id = ids.project_id
                    WHERE ids.id = :snapshot_id
                      AND ids.project_id = :project_id
                      AND ipp.rrp IS NOT NULL
                      AND ip.internal_sku IS NOT NULL
                    ORDER BY ip.internal_sku
                """),
                {
                    "project_id": project_id,
                    "snapshot_id": snapshot_id,
                },
            ).mappings().all()
            
            if not rrp_rows:
                logger.warning(
                    f"sync_internal_data_to_rrp_snapshots: no RRP rows found to sync "
                    f"for project_id={project_id} snapshot_id={snapshot_id}"
                )
                stats["errors"].append("No RRP rows found to sync (check mapping between internal_sku and products.vendor_code_norm)")
                return stats
            
            logger.info(
                f"sync_internal_data_to_rrp_snapshots: found {len(rrp_rows)} RRP rows to sync "
                f"for project_id={project_id}"
            )
            
            # Insert into rrp_snapshots (append-only, no upsert)
            # This creates a new snapshot_at timestamp for this sync
            insert_sql = text("""
                INSERT INTO rrp_snapshots
                    (project_id, snapshot_at, vendor_code_raw, vendor_code_norm, barcode, rrp_price, rrp_stock, source_file)
                VALUES
                    (:project_id, :snapshot_at, :vendor_code_raw, :vendor_code_norm, :barcode, :rrp_price, :rrp_stock, :source_file)
            """)
            
            rows_to_insert = [dict(row) for row in rrp_rows]
            conn.execute(insert_sql, rows_to_insert)
            
            stats["rows_synced"] = len(rows_to_insert)
            
            logger.info(
                f"sync_internal_data_to_rrp_snapshots: synced {stats['rows_synced']} rows "
                f"to rrp_snapshots for project_id={project_id}"
            )
    
    except Exception as e:
        logger.error(
            f"sync_internal_data_to_rrp_snapshots: error for project_id={project_id}: {e}",
            exc_info=True,
        )
        stats["errors"].append(f"{type(e).__name__}: {str(e)}")
    
    end_time = datetime.now(timezone.utc)
    elapsed_ms = (end_time - start_time).total_seconds() * 1000
    stats["completed_at"] = end_time.isoformat()
    stats["elapsed_ms"] = round(elapsed_ms, 2)
    
    logger.info(
        f"sync_internal_data_to_rrp_snapshots: completed for project_id={project_id} "
        f"rows_synced={stats['rows_synced']} errors={len(stats['errors'])} elapsed={elapsed_ms:.2f}ms"
    )
    
    return stats
