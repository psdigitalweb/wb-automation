"""Stock-related DB queries for ingest and analytics."""

from typing import List

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
