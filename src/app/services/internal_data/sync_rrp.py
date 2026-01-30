"""Build RRP snapshots from Internal Data.

`rrp_snapshots` is used by the WB price discrepancies report.

Historically the project relied on `rrp_xml` ingestion (local file: RRP_XML_PATH or /app/test.xml),
but in production this is often unavailable. Internal Data is the source of truth for RRP.

This module builds append-only rows in `rrp_snapshots` from the latest Internal Data snapshot.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy import text

from app.db import engine

logger = logging.getLogger(__name__)


def sync_internal_data_to_rrp_snapshots(project_id: int) -> Dict[str, Any]:
    """Build `rrp_snapshots` from the latest Internal Data snapshot.

    Key requirements:
    - Works on fresh DB (no dependency on local XML files).
    - Uses the same SKU normalization as `products.vendor_code_norm` generated column:
      trim '/' and take last segment after '/'.
    - Accepts latest internal_data snapshot with status in ('success','partial').
    - Does NOT require products to exist at build time (insert all normalized SKUs).
    - Append-only, but idempotent per Internal Data snapshot by using snapshot_at=imported_at.

    Returns a dict with detailed stats for UI/diagnostics.
    """
    logger.info(f"sync_internal_data_to_rrp_snapshots: starting for project_id={project_id}")
    start_time = datetime.now(timezone.utc)

    stats: Dict[str, Any] = {
        "project_id": project_id,
        "started_at": start_time.isoformat(),
        "source": "internal_data",
        "snapshot_id": None,
        "snapshot_imported_at": None,
        "snapshot_status": None,
        "already_built": False,
        "rows_found_rrp": 0,
        "rows_with_stock": 0,
        "rows_inserted": 0,
        "rows_matched_products": None,
        "sample_unmatched_skus": [],
        "errors": [],
    }

    # SQL fragments to match products.vendor_code_norm logic (see Alembic f1a2b3c4d5e6).
    sku_norm_expr = "NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '')"
    stock_expr = (
        "CASE "
        "WHEN COALESCE(ip.attributes, '{}'::jsonb) ? 'stock' "
        " AND (ip.attributes->>'stock') ~ '^[0-9]+$' "
        "THEN (ip.attributes->>'stock')::bigint "
        "ELSE NULL END"
    )

    try:
        with engine.begin() as conn:
            latest_snapshot = conn.execute(
                text(
                    """
                    SELECT
                      id,
                      imported_at,
                      status,
                      rows_imported,
                      rows_failed,
                      row_count
                    FROM internal_data_snapshots
                    WHERE project_id = :project_id
                      AND status IN ('success', 'partial')
                    ORDER BY imported_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    """
                ),
                {"project_id": project_id},
            ).mappings().first()

            if not latest_snapshot:
                msg = "No internal_data_snapshots with status success|partial found for this project"
                logger.warning(f"sync_internal_data_to_rrp_snapshots: {msg} project_id={project_id}")
                stats["errors"].append(msg)
                return stats

            snapshot_id = int(latest_snapshot["id"])
            imported_at = latest_snapshot.get("imported_at")
            snapshot_status = latest_snapshot.get("status")

            # Use imported_at as snapshot_at to make the build idempotent per internal snapshot.
            snapshot_at = imported_at or datetime.now(timezone.utc)

            stats["snapshot_id"] = snapshot_id
            stats["snapshot_imported_at"] = imported_at.isoformat() if hasattr(imported_at, "isoformat") else None
            stats["snapshot_status"] = snapshot_status

            logger.info(
                "sync_internal_data_to_rrp_snapshots: using snapshot_id=%s imported_at=%s status=%s",
                snapshot_id,
                stats["snapshot_imported_at"],
                snapshot_status,
            )

            # Idempotency: if we already built from this internal snapshot, do nothing.
            already_built_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM rrp_snapshots
                    WHERE project_id = :project_id
                      AND source_file = 'internal_data_sync'
                      AND snapshot_at = :snapshot_at
                    """
                ),
                {"project_id": project_id, "snapshot_at": snapshot_at},
            ).scalar()
            if int(already_built_count or 0) > 0:
                stats["already_built"] = True
                logger.info(
                    "sync_internal_data_to_rrp_snapshots: already built, skipping insert "
                    "project_id=%s snapshot_id=%s snapshot_at=%s",
                    project_id,
                    snapshot_id,
                    stats["snapshot_imported_at"] or str(snapshot_at),
                )

                # Still compute match diagnostics (best-effort) for UI visibility.
                try:
                    matched = conn.execute(
                        text(
                            f"""
                            WITH src AS (
                              SELECT DISTINCT {sku_norm_expr} AS sku_norm
                              FROM internal_product_prices ipp
                              JOIN internal_products ip ON ip.id = ipp.internal_product_id
                              JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                              WHERE ids.id = :snapshot_id
                                AND ids.project_id = :project_id
                                AND ipp.rrp IS NOT NULL
                                AND ip.internal_sku IS NOT NULL
                            )
                            SELECT COUNT(*)::bigint
                            FROM src
                            JOIN products p
                              ON p.project_id = :project_id
                             AND p.vendor_code_norm = src.sku_norm
                            WHERE src.sku_norm IS NOT NULL
                            """
                        ),
                        {"project_id": project_id, "snapshot_id": snapshot_id},
                    ).scalar()
                    stats["rows_matched_products"] = int(matched or 0)
                except Exception as e:
                    stats["errors"].append(f"match_diagnostics_failed: {type(e).__name__}: {e}")
                return stats

            # Count how many RRP rows exist in internal data (by normalized SKU).
            rows_found_rrp = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)::bigint
                    FROM (
                      SELECT DISTINCT {sku_norm_expr} AS sku_norm
                      FROM internal_product_prices ipp
                      JOIN internal_products ip ON ip.id = ipp.internal_product_id
                      JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                      WHERE ids.id = :snapshot_id
                        AND ids.project_id = :project_id
                        AND ipp.rrp IS NOT NULL
                        AND ip.internal_sku IS NOT NULL
                    ) t
                    WHERE t.sku_norm IS NOT NULL
                    """
                ),
                {"project_id": project_id, "snapshot_id": snapshot_id},
            ).scalar()
            stats["rows_found_rrp"] = int(rows_found_rrp or 0)

            rows_with_stock = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)::bigint
                    FROM (
                      SELECT DISTINCT
                        {sku_norm_expr} AS sku_norm,
                        {stock_expr} AS stock_qty
                      FROM internal_product_prices ipp
                      JOIN internal_products ip ON ip.id = ipp.internal_product_id
                      JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                      WHERE ids.id = :snapshot_id
                        AND ids.project_id = :project_id
                        AND ipp.rrp IS NOT NULL
                        AND ip.internal_sku IS NOT NULL
                    ) t
                    WHERE t.sku_norm IS NOT NULL AND t.stock_qty IS NOT NULL
                    """
                ),
                {"project_id": project_id, "snapshot_id": snapshot_id},
            ).scalar()
            stats["rows_with_stock"] = int(rows_with_stock or 0)

            if stats["rows_found_rrp"] == 0:
                msg = (
                    "No RRP rows found in Internal Data for latest snapshot "
                    "(check mapping_json.fields.rrp / data source)"
                )
                logger.warning(
                    "sync_internal_data_to_rrp_snapshots: %s project_id=%s snapshot_id=%s",
                    msg,
                    project_id,
                    snapshot_id,
                )
                stats["errors"].append(msg)
                return stats

            # Build + insert append-only snapshot (single SQL, no Python row materialization).
            insert_res = conn.execute(
                text(
                    f"""
                    INSERT INTO rrp_snapshots
                      (project_id, snapshot_at, vendor_code_raw, vendor_code_norm, barcode, rrp_price, rrp_stock, source_file)
                    SELECT
                      :project_id AS project_id,
                      :snapshot_at AS snapshot_at,
                      MIN(ip.internal_sku) AS vendor_code_raw,
                      {sku_norm_expr} AS vendor_code_norm,
                      NULL AS barcode,
                      MAX(ipp.rrp) AS rrp_price,
                      MAX({stock_expr}) AS rrp_stock,
                      'internal_data_sync' AS source_file
                    FROM internal_product_prices ipp
                    JOIN internal_products ip ON ip.id = ipp.internal_product_id
                    JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                    WHERE ids.id = :snapshot_id
                      AND ids.project_id = :project_id
                      AND ipp.rrp IS NOT NULL
                      AND ip.internal_sku IS NOT NULL
                      AND {sku_norm_expr} IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1
                        FROM rrp_snapshots rs
                        WHERE rs.project_id = :project_id
                          AND rs.source_file = 'internal_data_sync'
                          AND rs.snapshot_at = :snapshot_at
                      )
                    GROUP BY {sku_norm_expr}
                    """
                ),
                {"project_id": project_id, "snapshot_id": snapshot_id, "snapshot_at": snapshot_at},
            )
            stats["rows_inserted"] = int(getattr(insert_res, "rowcount", 0) or 0)

            # Diagnostics: how much matches products (best-effort).
            try:
                matched = conn.execute(
                    text(
                        f"""
                        WITH src AS (
                          SELECT DISTINCT {sku_norm_expr} AS sku_norm
                          FROM internal_product_prices ipp
                          JOIN internal_products ip ON ip.id = ipp.internal_product_id
                          JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                          WHERE ids.id = :snapshot_id
                            AND ids.project_id = :project_id
                            AND ipp.rrp IS NOT NULL
                            AND ip.internal_sku IS NOT NULL
                        )
                        SELECT COUNT(*)::bigint
                        FROM src
                        JOIN products p
                          ON p.project_id = :project_id
                         AND p.vendor_code_norm = src.sku_norm
                        WHERE src.sku_norm IS NOT NULL
                        """
                    ),
                    {"project_id": project_id, "snapshot_id": snapshot_id},
                ).scalar()
                stats["rows_matched_products"] = int(matched or 0)

                unmatched_rows = conn.execute(
                    text(
                        f"""
                        WITH src AS (
                          SELECT DISTINCT {sku_norm_expr} AS sku_norm
                          FROM internal_product_prices ipp
                          JOIN internal_products ip ON ip.id = ipp.internal_product_id
                          JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                          WHERE ids.id = :snapshot_id
                            AND ids.project_id = :project_id
                            AND ipp.rrp IS NOT NULL
                            AND ip.internal_sku IS NOT NULL
                        )
                        SELECT src.sku_norm
                        FROM src
                        LEFT JOIN products p
                          ON p.project_id = :project_id
                         AND p.vendor_code_norm = src.sku_norm
                        WHERE src.sku_norm IS NOT NULL
                          AND p.nm_id IS NULL
                        ORDER BY src.sku_norm
                        LIMIT 20
                        """
                    ),
                    {"project_id": project_id, "snapshot_id": snapshot_id},
                ).scalars().all()
                stats["sample_unmatched_skus"] = [str(x) for x in (unmatched_rows or [])]
            except Exception as e:
                stats["errors"].append(f"match_diagnostics_failed: {type(e).__name__}: {e}")

            logger.info(
                "sync_internal_data_to_rrp_snapshots: inserted=%s found_rrp=%s matched_products=%s project_id=%s",
                stats["rows_inserted"],
                stats["rows_found_rrp"],
                stats.get("rows_matched_products"),
                project_id,
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
        "sync_internal_data_to_rrp_snapshots: completed project_id=%s inserted=%s errors=%s elapsed_ms=%s",
        project_id,
        stats.get("rows_inserted"),
        len(stats.get("errors") or []),
        stats.get("elapsed_ms"),
    )

    return stats
