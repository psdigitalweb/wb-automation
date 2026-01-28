from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine
from app.services.scheduling.cron import compute_next_run, validate_cron, DEFAULT_TIMEZONE


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_schedule(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "marketplace_code": row["marketplace_code"],
        "job_code": row["job_code"],
        "cron_expr": row["cron_expr"],
        "timezone": row["timezone"],
        "is_enabled": row["is_enabled"],
        "next_run_at": row["next_run_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_schedules(project_id: int) -> List[Dict[str, Any]]:
    sql = text(
        """
        SELECT id, project_id, marketplace_code, job_code,
               cron_expr, timezone, is_enabled, next_run_at,
               created_at, updated_at
        FROM ingest_schedules
        WHERE project_id = :project_id
        ORDER BY marketplace_code, job_code
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"project_id": project_id}).mappings().all()
    return [_row_to_schedule(row) for row in rows]


def create_schedule(
    project_id: int,
    marketplace_code: str,
    job_code: str,
    cron_expr: str,
    timezone_str: Optional[str] = None,
    is_enabled: bool = True,
) -> Dict[str, Any]:
    """Create new schedule and compute next_run_at."""
    validate_cron(cron_expr)
    tz = timezone_str or DEFAULT_TIMEZONE
    now = _now_utc()
    next_run_at = compute_next_run(cron_expr, tz, now)

    sql = text(
        """
        INSERT INTO ingest_schedules (
            project_id, marketplace_code, job_code,
            cron_expr, timezone, is_enabled, next_run_at,
            created_at, updated_at
        ) VALUES (
            :project_id, :marketplace_code, :job_code,
            :cron_expr, :timezone, :is_enabled, :next_run_at,
            :now, :now
        )
        RETURNING id, project_id, marketplace_code, job_code,
                  cron_expr, timezone, is_enabled, next_run_at,
                  created_at, updated_at
        """
    )
    params = {
        "project_id": project_id,
        "marketplace_code": marketplace_code,
        "job_code": job_code,
        "cron_expr": cron_expr,
        "timezone": tz,
        "is_enabled": is_enabled,
        "next_run_at": next_run_at,
        "now": now,
    }
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_schedule(row)


def get_schedule(schedule_id: int) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT id, project_id, marketplace_code, job_code,
               cron_expr, timezone, is_enabled, next_run_at,
               created_at, updated_at
        FROM ingest_schedules
        WHERE id = :id
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"id": schedule_id}).mappings().first()
    return _row_to_schedule(row) if row else None


def update_schedule(
    schedule_id: int,
    cron_expr: Optional[str] = None,
    timezone_str: Optional[str] = None,
    is_enabled: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Partial update; recompute next_run_at when cron/timezone change or enabling schedule."""
    schedule = get_schedule(schedule_id)
    if not schedule:
        return None

    new_cron = cron_expr if cron_expr is not None else schedule["cron_expr"]
    new_tz = timezone_str if timezone_str is not None else schedule["timezone"]
    new_enabled = is_enabled if is_enabled is not None else schedule["is_enabled"]

    if cron_expr is not None:
        validate_cron(new_cron)

    now = _now_utc()
    next_run_at = compute_next_run(new_cron, new_tz, now) if new_enabled else None

    sql = text(
        """
        UPDATE ingest_schedules
        SET cron_expr = :cron_expr,
            timezone = :timezone,
            is_enabled = :is_enabled,
            next_run_at = :next_run_at,
            updated_at = :now
        WHERE id = :id
        RETURNING id, project_id, marketplace_code, job_code,
                  cron_expr, timezone, is_enabled, next_run_at,
                  created_at, updated_at
        """
    )
    params = {
        "id": schedule_id,
        "cron_expr": new_cron,
        "timezone": new_tz,
        "is_enabled": new_enabled,
        "next_run_at": next_run_at,
        "now": now,
    }
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_schedule(row) if row else None


def toggle_schedule(schedule_id: int, is_enabled: bool) -> Optional[Dict[str, Any]]:
    schedule = get_schedule(schedule_id)
    if not schedule:
        return None
    return update_schedule(
        schedule_id=schedule_id,
        is_enabled=is_enabled,
        cron_expr=schedule["cron_expr"],
        timezone_str=schedule["timezone"],
    )


def recalc_next_run(schedule_id: int, from_dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    schedule = get_schedule(schedule_id)
    if not schedule:
        return None
    if not schedule["is_enabled"]:
        # Disabled schedules do not have next_run_at
        sql = text(
            """
            UPDATE ingest_schedules
            SET next_run_at = NULL,
                updated_at = :now
            WHERE id = :id
            RETURNING id, project_id, marketplace_code, job_code,
                      cron_expr, timezone, is_enabled, next_run_at,
                      created_at, updated_at
            """
        )
        with engine.begin() as conn:
            row = conn.execute(sql, {"id": schedule_id, "now": _now_utc()}).mappings().first()
        return _row_to_schedule(row) if row else None

    ref = from_dt or _now_utc()
    next_run_at = compute_next_run(schedule["cron_expr"], schedule["timezone"], ref)
    sql = text(
        """
        UPDATE ingest_schedules
        SET next_run_at = :next_run_at,
            updated_at = :now
        WHERE id = :id
        RETURNING id, project_id, marketplace_code, job_code,
                  cron_expr, timezone, is_enabled, next_run_at,
                  created_at, updated_at
        """
    )
    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {"id": schedule_id, "next_run_at": next_run_at, "now": _now_utc()},
        ).mappings().first()
    return _row_to_schedule(row) if row else None


def due_schedules(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Return enabled schedules whose next_run_at <= now."""
    ref = now or _now_utc()
    sql = text(
        """
        SELECT id, project_id, marketplace_code, job_code,
               cron_expr, timezone, is_enabled, next_run_at,
               created_at, updated_at
        FROM ingest_schedules
        WHERE is_enabled = TRUE
          AND next_run_at IS NOT NULL
          AND next_run_at <= :now
        ORDER BY next_run_at ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"now": ref}).mappings().all()
    return [_row_to_schedule(row) for row in rows]


def mark_dispatched(schedule_id: int, next_run_at: datetime) -> Optional[Dict[str, Any]]:
    """Set next_run_at to provided value after dispatching current run."""
    sql = text(
        """
        UPDATE ingest_schedules
        SET next_run_at = :next_run_at,
            updated_at = :now
        WHERE id = :id
        RETURNING id, project_id, marketplace_code, job_code,
                  cron_expr, timezone, is_enabled, next_run_at,
                  created_at, updated_at
        """
    )
    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {"id": schedule_id, "next_run_at": next_run_at, "now": _now_utc()},
        ).mappings().first()
    return _row_to_schedule(row) if row else None


def delete_schedule(schedule_id: int) -> bool:
    """Delete schedule by id. Returns True if a row was deleted."""
    sql = text(
        """
        DELETE FROM ingest_schedules
        WHERE id = :id
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql, {"id": schedule_id})
    return result.rowcount > 0

