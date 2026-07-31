"""Stock-related DB queries for ingest and analytics."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy import text

from app.db import engine


def get_active_fbs_nm_ids(project_id: int) -> List[int]:
    """Get nm_id list with FBS stock qty > 0 from latest stock_snapshots run.

    Reuses the same approach as api_dashboard (fbs_latest):
    latest snapshot_at + SUM(quantity) by nm_id, where qty > 0.
    """
    sql = text("""
        WITH stock_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbs_latest AS (
            SELECT ss.nm_id::bigint AS nm_id,
                   SUM(COALESCE(ss.quantity, 0))::bigint AS qty
            FROM stock_snapshots ss
            JOIN stock_run r ON ss.snapshot_at = r.run_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        )
        SELECT nm_id FROM fbs_latest WHERE qty > 0
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"project_id": project_id})
        return [int(r[0]) for r in rows if r[0] is not None]


def get_active_wb_nm_ids(project_id: int) -> List[int]:
    """Get distinct nm_id with stock quantity > 0 (WB, from stock_snapshots).

    Used for wb_card_stats_daily daily mode (active SKU only).
    Same source as get_active_fbs_nm_ids — FBS stock_snapshots.
    """
    return get_active_fbs_nm_ids(project_id)


def get_latest_fbo_stock_totals_by_nm_id(
    nm_ids: List[int],
) -> Dict[int, Tuple[int, Optional[datetime]]]:
    """Return latest FBO (WB warehouses) stock totals by nm_id from supplier_stock_snapshots.

    supplier_stock_snapshots is append-only; for each nm_id + warehouse_name we take the latest
    record by COALESCE(last_change_date, snapshot_at), then sum quantities across warehouses.
    """
    if not nm_ids:
        return {}

    sql = text(
        """
        WITH latest_wh AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id::bigint AS nm_id,
                s.warehouse_name,
                COALESCE(s.quantity, 0)::bigint AS quantity,
                COALESCE(s.last_change_date, s.snapshot_at) AS updated_at
            FROM supplier_stock_snapshots s
            WHERE s.nm_id = ANY(:nm_ids)
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        totals AS (
            SELECT
                nm_id,
                SUM(quantity)::bigint AS qty,
                MAX(updated_at) AS updated_at
            FROM latest_wh
            GROUP BY nm_id
        )
        SELECT nm_id, qty, updated_at
        FROM totals
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"nm_ids": nm_ids}).fetchall()

    out: Dict[int, Tuple[int, Optional[datetime]]] = {}
    for nm_id, qty, updated_at in rows:
        if nm_id is None:
            continue
        out[int(nm_id)] = (int(qty or 0), updated_at if isinstance(updated_at, datetime) else None)
    return out


def get_latest_enterprise_stock_by_vendor_code_norm(
    project_id: int,
    vendor_code_norms: List[str],
) -> Tuple[Dict[str, int], Optional[datetime]]:
    """Return latest enterprise stock (catalog/RRP ingestion) by vendor_code_norm.

    Source: rrp_snapshots (append-only). We take the latest snapshot_at run for the project
    and aggregate per vendor_code_norm within that run.
    """
    norms = [v for v in vendor_code_norms if v is not None and str(v).strip() != ""]
    if not norms:
        return {}, None

    sql = text(
        """
        WITH rrp_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM rrp_snapshots
            WHERE project_id = :project_id
        ),
        rrp_latest AS (
            SELECT
                s.vendor_code_norm AS vendor_code_norm,
                MAX(s.rrp_stock)::bigint AS qty
            FROM rrp_snapshots s
            JOIN rrp_run r ON s.snapshot_at = r.run_at
            WHERE s.project_id = :project_id
              AND s.vendor_code_norm = ANY(:vendor_code_norms)
            GROUP BY s.vendor_code_norm
        )
        SELECT rl.vendor_code_norm, rl.qty, r.run_at
        FROM rrp_latest rl
        JOIN rrp_run r ON TRUE
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"project_id": project_id, "vendor_code_norms": norms},
        ).fetchall()

    out: Dict[str, int] = {}
    run_at: Optional[datetime] = None
    for vendor_code_norm, qty, rrp_run_at in rows:
        if vendor_code_norm is None:
            continue
        out[str(vendor_code_norm)] = int(qty or 0)
        if run_at is None and isinstance(rrp_run_at, datetime):
            run_at = rrp_run_at
    return out, run_at
