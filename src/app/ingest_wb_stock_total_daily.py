"""Build one project-scoped daily FBS stock total snapshot."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict

from sqlalchemy import text

from app.db import engine


async def build_wb_stock_total_daily(
    *,
    project_id: int,
    run_id: int | None = None,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    params = params or {}
    requested_date = params.get("snapshot_date") or params.get("date_to")
    if isinstance(requested_date, datetime):
        snapshot_date = requested_date.date()
    elif isinstance(requested_date, date):
        snapshot_date = requested_date
    elif requested_date:
        snapshot_date = date.fromisoformat(str(requested_date)[:10])
    else:
        snapshot_date = datetime.now(timezone.utc).date()

    sql = text(
        """
        WITH latest_run AS (
            SELECT MAX(snapshot_at) AS snapshot_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        totals AS (
            SELECT ss.nm_id, SUM(COALESCE(ss.quantity, 0))::int AS qty_total
            FROM stock_snapshots ss
            JOIN latest_run lr ON lr.snapshot_at = ss.snapshot_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        upserted AS (
            INSERT INTO wb_stock_total_daily_snapshots (
                project_id, nm_id, qty_total, snapshot_date, source, ingest_run_id,
                created_at, updated_at
            )
            SELECT
                p.project_id,
                p.nm_id,
                COALESCE(t.qty_total, 0),
                :snapshot_date,
                jsonb_build_object('source', 'stock_snapshots', 'snapshot_at', lr.snapshot_at),
                :run_id,
                now(),
                now()
            FROM products p
            CROSS JOIN latest_run lr
            LEFT JOIN totals t ON t.nm_id = p.nm_id
            WHERE p.project_id = :project_id
              AND lr.snapshot_at IS NOT NULL
            ON CONFLICT (project_id, nm_id, snapshot_date) DO UPDATE SET
                qty_total = EXCLUDED.qty_total,
                source = EXCLUDED.source,
                ingest_run_id = EXCLUDED.ingest_run_id,
                updated_at = now()
            RETURNING qty_total
        )
        SELECT COUNT(*)::int AS rows_written,
               COUNT(*) FILTER (WHERE qty_total > 0)::int AS products_in_stock,
               COALESCE(SUM(qty_total), 0)::int AS qty_total
        FROM upserted
        """
    )
    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": int(project_id),
                "snapshot_date": snapshot_date,
                "run_id": int(run_id) if run_id is not None else None,
            },
        ).mappings().one()

    rows_written = int(row.get("rows_written") or 0)
    return {
        "ok": rows_written > 0,
        "scope": "project",
        "project_id": int(project_id),
        "domain": "wb_stock_total_daily",
        "snapshot_date": snapshot_date.isoformat(),
        "rows_written": rows_written,
        "products_in_stock": int(row.get("products_in_stock") or 0),
        "qty_total": int(row.get("qty_total") or 0),
        **({} if rows_written > 0 else {"reason": "no_fbs_snapshot"}),
    }
