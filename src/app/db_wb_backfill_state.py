"""DAO for wb_backfill_range_state (source of truth for backfill resume)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.db import engine

JOB_CODE_WB_CARD_STATS_DAILY = "wb_card_stats_daily"
JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL = "wb_communications_reviews_backfill"

# Max automatic continuation runs per single-day range (prevents infinite chain)
MAX_AUTO_CONTINUES_PER_DAY = 10


def _row_to_state(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "job_code": row["job_code"],
        "date_from": row["date_from"],
        "date_to": row["date_to"],
        "status": row["status"],
        "cursor_date": row["cursor_date"],
        "cursor_nm_offset": row["cursor_nm_offset"],
        "last_run_id": row["last_run_id"],
        "completed_at": row["completed_at"],
        "error_message": row["error_message"],
        "meta_json": row["meta_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_backfill_state(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
) -> Optional[Dict[str, Any]]:
    """Load range state by (project_id, job_code, date_from, date_to)."""
    sql = text("""
        SELECT id, project_id, job_code, date_from, date_to, status,
               cursor_date, cursor_nm_offset, last_run_id, completed_at,
               error_message, meta_json, created_at, updated_at
        FROM wb_backfill_range_state
        WHERE project_id = :project_id AND job_code = :job_code
          AND date_from = :date_from AND date_to = :date_to
    """)
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().first()
    return _row_to_state(row) if row else None


def upsert_backfill_state_running(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    run_id: int,
    cursor_date: date,
    cursor_nm_offset: int,
    meta_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or update state to running with given cursor. Used after each successful batch."""
    now = datetime.now(timezone.utc)
    meta = meta_json or {}
    import json as _json
    meta_str = _json.dumps(meta, ensure_ascii=False)
    sql = text("""
        INSERT INTO wb_backfill_range_state (
            project_id, job_code, date_from, date_to, status,
            cursor_date, cursor_nm_offset, last_run_id, meta_json, updated_at
        ) VALUES (
            :project_id, :job_code, :date_from, :date_to, 'running',
            :cursor_date, :cursor_nm_offset, :run_id, CAST(:meta_json AS jsonb), :now
        )
        ON CONFLICT (project_id, job_code, date_from, date_to) DO UPDATE SET
            status = 'running',
            cursor_date = EXCLUDED.cursor_date,
            cursor_nm_offset = EXCLUDED.cursor_nm_offset,
            last_run_id = EXCLUDED.last_run_id,
            completed_at = NULL,
            error_message = NULL,
            meta_json = EXCLUDED.meta_json,
            updated_at = EXCLUDED.updated_at
    """)
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "run_id": run_id,
                "cursor_date": cursor_date,
                "cursor_nm_offset": cursor_nm_offset,
                "meta_json": meta_str,
                "now": now,
            },
        )
    return get_backfill_state(project_id, job_code, date_from, date_to) or {}


def mark_backfill_state_paused(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    run_id: int,
    cursor_date: date,
    cursor_nm_offset: int,
    error_message: Optional[str] = None,
    meta_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Set state to paused with cursor pointing to next batch."""
    now = datetime.now(timezone.utc)
    meta = meta_json or {}
    import json as _json
    meta_str = _json.dumps(meta, ensure_ascii=False)
    sql = text("""
        INSERT INTO wb_backfill_range_state (
            project_id, job_code, date_from, date_to, status,
            cursor_date, cursor_nm_offset, last_run_id, error_message, meta_json, updated_at
        ) VALUES (
            :project_id, :job_code, :date_from, :date_to, 'paused',
            :cursor_date, :cursor_nm_offset, :run_id, :error_message, CAST(:meta_json AS jsonb), :now
        )
        ON CONFLICT (project_id, job_code, date_from, date_to) DO UPDATE SET
            status = 'paused',
            cursor_date = EXCLUDED.cursor_date,
            cursor_nm_offset = EXCLUDED.cursor_nm_offset,
            last_run_id = EXCLUDED.last_run_id,
            completed_at = NULL,
            error_message = COALESCE(EXCLUDED.error_message, wb_backfill_range_state.error_message),
            meta_json = EXCLUDED.meta_json,
            updated_at = EXCLUDED.updated_at
    """)
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "run_id": run_id,
                "cursor_date": cursor_date,
                "cursor_nm_offset": cursor_nm_offset,
                "error_message": error_message,
                "meta_json": meta_str,
                "now": now,
            },
        )


def mark_backfill_state_completed(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    run_id: int,
    nm_ids_count: int,
    meta_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Set state to completed (range fully processed). cursor = (date_to, nm_ids_count)."""
    now = datetime.now(timezone.utc)
    meta = meta_json or {}
    import json as _json
    meta_str = _json.dumps(meta, ensure_ascii=False)
    sql = text("""
        INSERT INTO wb_backfill_range_state (
            project_id, job_code, date_from, date_to, status,
            cursor_date, cursor_nm_offset, last_run_id, completed_at, meta_json, updated_at
        ) VALUES (
            :project_id, :job_code, :date_from, :date_to, 'completed',
            :date_to, :cursor_nm_offset, :run_id, :now, CAST(:meta_json AS jsonb), :now
        )
        ON CONFLICT (project_id, job_code, date_from, date_to) DO UPDATE SET
            status = 'completed',
            cursor_date = EXCLUDED.cursor_date,
            cursor_nm_offset = EXCLUDED.cursor_nm_offset,
            last_run_id = EXCLUDED.last_run_id,
            completed_at = EXCLUDED.completed_at,
            error_message = NULL,
            meta_json = EXCLUDED.meta_json,
            updated_at = EXCLUDED.updated_at
    """)
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "run_id": run_id,
                "cursor_nm_offset": nm_ids_count,
                "meta_json": meta_str,
                "now": now,
            },
        )


def mark_backfill_state_failed(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    run_id: int,
    cursor_date: Optional[date],
    cursor_nm_offset: Optional[int],
    error_message: str,
    meta_json: Optional[Dict[str, Any]] = None,
) -> None:
    """Set state to failed (e.g. auth error); cursor preserved for resume."""
    now = datetime.now(timezone.utc)
    meta = meta_json or {}
    import json as _json
    meta_str = _json.dumps(meta, ensure_ascii=False)
    sql = text("""
        INSERT INTO wb_backfill_range_state (
            project_id, job_code, date_from, date_to, status,
            cursor_date, cursor_nm_offset, last_run_id, error_message, meta_json, updated_at
        ) VALUES (
            :project_id, :job_code, :date_from, :date_to, 'failed',
            :cursor_date, :cursor_nm_offset, :run_id, :error_message, CAST(:meta_json AS jsonb), :now
        )
        ON CONFLICT (project_id, job_code, date_from, date_to) DO UPDATE SET
            status = 'failed',
            cursor_date = COALESCE(EXCLUDED.cursor_date, wb_backfill_range_state.cursor_date),
            cursor_nm_offset = COALESCE(EXCLUDED.cursor_nm_offset, wb_backfill_range_state.cursor_nm_offset),
            last_run_id = EXCLUDED.last_run_id,
            error_message = EXCLUDED.error_message,
            meta_json = EXCLUDED.meta_json,
            updated_at = EXCLUDED.updated_at
    """)
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "run_id": run_id,
                "cursor_date": cursor_date,
                "cursor_nm_offset": cursor_nm_offset,
                "error_message": error_message[:2000] if error_message else None,
                "meta_json": meta_str,
                "now": now,
            },
        )


def ensure_backfill_state_created(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    run_id: int,
) -> None:
    """Create state row at start of backfill (status=running, cursor at start)."""
    now = datetime.now(timezone.utc)
    sql = text("""
        INSERT INTO wb_backfill_range_state (
            project_id, job_code, date_from, date_to, status,
            cursor_date, cursor_nm_offset, last_run_id, updated_at
        ) VALUES (
            :project_id, :job_code, :date_from, :date_to, 'running',
            :date_from, 0, :run_id, :now
        )
        ON CONFLICT (project_id, job_code, date_from, date_to) DO NOTHING
    """)
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "run_id": run_id,
                "now": now,
            },
        )


def try_increment_auto_continue_count(
    project_id: int,
    job_code: str,
    date_from: date,
    date_to: date,
    max_count: int = MAX_AUTO_CONTINUES_PER_DAY,
) -> Optional[int]:
    """Increment auto_continue_count in meta_json only if status=paused and count < max_count.
    Returns new count if incremented, None if not updated (not paused, or at limit).
    """
    now = datetime.now(timezone.utc)
    sql = text("""
        UPDATE wb_backfill_range_state
        SET
            meta_json = jsonb_set(
                COALESCE(meta_json, '{}'::jsonb),
                '{auto_continue_count}',
                to_jsonb((COALESCE((meta_json->>'auto_continue_count')::int, 0) + 1)::int)
            ),
            updated_at = :now
        WHERE project_id = :project_id AND job_code = :job_code
          AND date_from = :date_from AND date_to = :date_to
          AND status = 'paused'
          AND (COALESCE((meta_json->>'auto_continue_count')::int, 0) < :max_count)
        RETURNING (meta_json->>'auto_continue_count')::int AS new_count
    """)
    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": project_id,
                "job_code": job_code,
                "date_from": date_from,
                "date_to": date_to,
                "now": now,
                "max_count": max_count,
            },
        ).mappings().first()
    if row is None:
        return None
    return int(row["new_count"])
