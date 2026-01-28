from __future__ import annotations

"""Helpers for WB current+history contract.

This module implements:
- Partial upsert into wb_current_metrics with COALESCE to avoid null overwrites.
- Time-bucketing helpers for hourly (snapshot_at) and daily (snapshot_date) values
  in project timezone (Europe/Istanbul by default, until per-project TZ is added).
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List

from zoneinfo import ZoneInfo
from sqlalchemy import text

from app.db import engine


_DEFAULT_PROJECT_TZ = "Europe/Istanbul"


def _get_project_timezone(_: int) -> ZoneInfo:
    """Return project timezone.

    For now, we always use Europe/Istanbul as default, as there is no per-project
    timezone column in the current schema. This can be extended later to read
    from projects/settings.
    """
    return ZoneInfo(_DEFAULT_PROJECT_TZ)


def compute_hour_bucket_utc(project_id: int, now_utc: datetime | None = None) -> datetime:
    """Compute hourly bucket (floor to hour) in project TZ, returned as UTC."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    tz = _get_project_timezone(project_id)
    local = now_utc.astimezone(tz)
    local_bucket = local.replace(minute=0, second=0, microsecond=0)
    return local_bucket.astimezone(timezone.utc)


def compute_snapshot_date(project_id: int, now_utc: datetime | None = None) -> date:
    """Compute snapshot_date (DATE) in project TZ."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    tz = _get_project_timezone(project_id)
    local = now_utc.astimezone(tz)
    return local.date()


def _normalize_current_row(row: Dict[str, Any], run_id: int | None) -> Dict[str, Any]:
    """Ensure all expected keys exist for wb_current_metrics upsert."""
    return {
        "project_id": row["project_id"],
        "nm_id": row["nm_id"],
        # Optional current metrics: allow absence -> None so COALESCE keeps old values.
        "current_qty_fbo": row.get("current_qty_fbo"),
        "current_qty_fbs": row.get("current_qty_fbs"),
        "current_price_showcase": row.get("current_price_showcase"),
        "current_spp_percent": row.get("current_spp_percent"),
        "current_price_base": row.get("current_price_base"),
        "last_ingest_run_id": run_id,
    }


_UPSERT_CURRENT_SQL = text(
    """
    INSERT INTO wb_current_metrics (
        project_id,
        nm_id,
        current_qty_fbo,
        current_qty_fbs,
        current_price_showcase,
        current_spp_percent,
        current_price_base,
        updated_at,
        last_ingest_run_id
    )
    VALUES (
        :project_id,
        :nm_id,
        :current_qty_fbo,
        :current_qty_fbs,
        :current_price_showcase,
        :current_spp_percent,
        :current_price_base,
        now(),
        :last_ingest_run_id
    )
    ON CONFLICT (project_id, nm_id)
    DO UPDATE SET
        current_qty_fbo = COALESCE(EXCLUDED.current_qty_fbo, wb_current_metrics.current_qty_fbo),
        current_qty_fbs = COALESCE(EXCLUDED.current_qty_fbs, wb_current_metrics.current_qty_fbs),
        current_price_showcase = COALESCE(EXCLUDED.current_price_showcase, wb_current_metrics.current_price_showcase),
        current_spp_percent = COALESCE(EXCLUDED.current_spp_percent, wb_current_metrics.current_spp_percent),
        current_price_base = COALESCE(EXCLUDED.current_price_base, wb_current_metrics.current_price_base),
        updated_at = now(),
        last_ingest_run_id = EXCLUDED.last_ingest_run_id
    """
)


def upsert_wb_current_metrics_on_conn(
    conn,
    rows: Iterable[Dict[str, Any]],
    run_id: int | None,
) -> int:
    """Bulk upsert into wb_current_metrics using existing connection/transaction.

    - Only (project_id, nm_id) are required in each row.
    - Other fields are optional; if missing or None, they will NOT overwrite existing
      values thanks to COALESCE in the ON CONFLICT clause.
    - updated_at and last_ingest_run_id are always refreshed on upsert.

    Returns:
        int: number of logical items attempted (len(rows)), suitable for
             current_upserts = items_total semantics.
    """
    normalized: List[Dict[str, Any]] = [
        _normalize_current_row(row, run_id) for row in rows
    ]
    if not normalized:
        return 0

    conn.execute(_UPSERT_CURRENT_SQL, normalized)

    # For stats we intentionally return the number of items we attempted to upsert,
    # not the number of actually changed rows, to keep semantics stable.
    return len(normalized)


