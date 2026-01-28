from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import ProgrammingError

from app.db import engine
from app.settings import INGEST_STUCK_TTL_SECONDS_DEFAULT
import json as _json

_JOB_TTL_SECONDS: Dict[tuple[str, str], int] = {
    # (marketplace_code, job_code): ttl_seconds
    # keep empty by default; override via env constant below if needed
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


_INGEST_RUNS_COLUMNS_CACHE: Optional[set[str]] = None
_DEBUG_LOG_PATH = r"d:\Work\EcomCore\.cursor\debug.log"


def _debug_log(location: str, message: str, data: Dict[str, Any], *, hypothesis_id: str) -> None:
    """Write NDJSON debug log line (no secrets)."""
    try:
        payload = {
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_ingest_runs_columns() -> set[str]:
    """Fetch available columns for ingest_runs (cached)."""
    global _INGEST_RUNS_COLUMNS_CACHE
    if _INGEST_RUNS_COLUMNS_CACHE is not None:
        return _INGEST_RUNS_COLUMNS_CACHE
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'ingest_runs'
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    cols = {r["column_name"] for r in rows if r.get("column_name")}
    _INGEST_RUNS_COLUMNS_CACHE = cols
    _debug_log(
        "services/ingest/runs.py:_get_ingest_runs_columns",
        "ingest_runs columns discovered",
        {"columns_count": len(cols), "has_params_json": "params_json" in cols, "has_meta_json": "meta_json" in cols},
        hypothesis_id="RUNS_SCHEMA",
    )
    return cols


def _row_to_run(row: Any) -> Dict[str, Any]:
    meta_json = row.get("meta_json")
    if isinstance(meta_json, str):
        try:
            import json as json_module

            meta_json = json_module.loads(meta_json)
        except Exception:
            meta_json = {}
    return {
        "id": row["id"],
        "schedule_id": row["schedule_id"],
        "project_id": row["project_id"],
        "marketplace_code": row["marketplace_code"],
        "job_code": row["job_code"],
        "triggered_by": row["triggered_by"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "duration_ms": row["duration_ms"],
        "error_message": row["error_message"],
        "error_trace": row["error_trace"],
        "stats_json": row["stats_json"],
        "params_json": row.get("params_json"),  # May not exist in older migrations
        "heartbeat_at": row.get("heartbeat_at"),
        "celery_task_id": row.get("celery_task_id"),
        "meta_json": meta_json,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class RunAlreadyRunningError(Exception):
    """Raised when another run is already running for same (project, marketplace, job)."""


def create_run_queued(
    project_id: int,
    marketplace_code: str,
    job_code: str,
    schedule_id: Optional[int],
    triggered_by: str,
    params_json: Optional[Dict[str, Any]] = None,
    *,
    conn=None,
) -> Dict[str, Any]:
    """Create a run with status 'queued'.

    Relies on partial unique index for 'running' status to prevent double start.
    """
    now = _now_utc()
    import json as json_module
    
    # Handle params_json: convert to JSON string or NULL
    if params_json is not None:
        params_json_str = json_module.dumps(params_json, ensure_ascii=False)
        params_json_sql = "CAST(:params_json AS jsonb)"
    else:
        params_json_str = None
        params_json_sql = "NULL"
    
    sql = text(
        f"""
        INSERT INTO ingest_runs (
            schedule_id, project_id, marketplace_code, job_code,
            triggered_by, status, params_json,
            created_at, updated_at
        ) VALUES (
            :schedule_id, :project_id, :marketplace_code, :job_code,
            :triggered_by, 'queued', {params_json_sql},
            :now, :now
        )
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  heartbeat_at, celery_task_id, meta_json,
                  created_at, updated_at
        """
    )
    params = {
        "schedule_id": schedule_id,
        "project_id": project_id,
        "marketplace_code": marketplace_code,
        "job_code": job_code,
        "triggered_by": triggered_by,
        "now": now,
    }
    if params_json_str is not None:
        params["params_json"] = params_json_str
    if conn is None:
        with engine.begin() as _conn:
            row = _conn.execute(sql, params).mappings().first()
    else:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row)


def get_run(run_id: int, *, conn=None) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT id, schedule_id, project_id, marketplace_code, job_code,
               triggered_by, status,
               started_at, finished_at, duration_ms,
               error_message, error_trace, stats_json, params_json,
               heartbeat_at, celery_task_id, meta_json,
               created_at, updated_at
        FROM ingest_runs
        WHERE id = :id
        """
    )
    try:
        if conn is None:
            with engine.connect() as _conn:
                row = _conn.execute(sql, {"id": run_id}).mappings().first()
        else:
            row = conn.execute(sql, {"id": run_id}).mappings().first()
    except ProgrammingError as exc:
        # If migrations weren't applied yet, ingest_runs may not exist.
        if "ingest_runs" in str(exc).lower() and ("does not exist" in str(exc).lower() or "undefinedtable" in str(exc).lower()):
            _debug_log(
                "services/ingest/runs.py:get_run",
                "ingest_runs table missing (return None)",
                {"run_id": run_id},
                hypothesis_id="RUNS_TABLE_MISSING",
            )
            return None
        raise
    return _row_to_run(row) if row else None


def touch_run(run_id: int, *, conn=None) -> bool:
    """Heartbeat: bump heartbeat_at + updated_at for a running run."""
    now = _now_utc()
    sql = text(
        """
        UPDATE ingest_runs
        SET heartbeat_at = :now,
            updated_at = :now
        WHERE id = :id AND status = 'running'
        """
    )
    if conn is None:
        with engine.begin() as _conn:
            res = _conn.execute(sql, {"id": run_id, "now": now})
    else:
        res = conn.execute(sql, {"id": run_id, "now": now})
    return (res.rowcount or 0) > 0


def set_run_progress(run_id: int, progress_stats: Dict[str, Any]) -> bool:
    """Update stats_json for a running run (for UI progress)."""
    now = _now_utc()
    import json as json_module

    stats_json_str = json_module.dumps(progress_stats, ensure_ascii=False)
    sql = text(
        """
        UPDATE ingest_runs
        SET stats_json = CAST(:stats_json AS jsonb),
            updated_at = :now
        WHERE id = :id AND status = 'running'
        """
    )
    with engine.begin() as conn:
        res = conn.execute(sql, {"id": run_id, "stats_json": stats_json_str, "now": now})

    return (res.rowcount or 0) > 0


def _try_unlock_stale_running_conflict(
    project_id: int,
    marketplace_code: str,
    job_code: str,
    *,
    stale_after_seconds: int = INGEST_STUCK_TTL_SECONDS_DEFAULT,
) -> bool:
    """If a conflicting 'running' run looks stale, mark it timeout and return True."""
    now = _now_utc()
    stale_before = now - timedelta(seconds=stale_after_seconds)

    select_sql = text(
        """
        SELECT id, started_at, updated_at, heartbeat_at
        FROM ingest_runs
        WHERE project_id = :project_id
          AND marketplace_code = :marketplace_code
          AND job_code = :job_code
          AND status = 'running'
        ORDER BY started_at ASC NULLS LAST
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            select_sql,
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
                "job_code": job_code,
            },
        ).mappings().first()
    if not row:
        return False

    run_id = row["id"]
    last_activity = row.get("heartbeat_at") or row.get("updated_at") or row.get("started_at") or now
    if last_activity >= stale_before:
        return False

    duration_ms = None
    if row.get("started_at"):
        duration_ms = int((now - row["started_at"]).total_seconds() * 1000)

    import json as json_module

    stats_json_str = json_module.dumps(
        {
            "ok": False,
            "reason": "stale_unlock_conflict",
            "stale_after_seconds": stale_after_seconds,
            "previous_last_activity": last_activity.isoformat()
            if hasattr(last_activity, "isoformat")
            else str(last_activity),
        },
        ensure_ascii=False,
    )

    meta_patch_str = json_module.dumps(
        {
            "system_action": {
                "type": "timeout",
                "reason_code": "stale_unlock_conflict",
                "actor": "system",
                "at": now.isoformat(),
            }
        },
        ensure_ascii=False,
    )

    update_sql = text(
        """
        UPDATE ingest_runs
        SET status = 'timeout',
            finished_at = :now,
            duration_ms = :duration_ms,
            error_message = :error_message,
            error_trace = :error_trace,
            stats_json = CAST(:stats_json AS jsonb),
            meta_json = COALESCE(meta_json, '{}'::jsonb) || CAST(:meta_patch AS jsonb),
            updated_at = :now
        WHERE id = :id AND status = 'running'
        """
    )
    with engine.begin() as conn:
        res = conn.execute(
            update_sql,
            {
                "id": run_id,
                "now": now,
                "duration_ms": duration_ms,
                "error_message": "stale running conflict",
                "error_trace": "Auto-unlocked stale running run due to stale heartbeat (conflict).",
                "stats_json": stats_json_str,
                "meta_patch": meta_patch_str,
            },
        )
    return (res.rowcount or 0) > 0


def _set_running_if_no_conflict(run_id: int) -> Dict[str, Any]:
    """Transition run to 'running', enforcing single running per (project, marketplace, job).

    This uses the partial unique index by attempting to set status='running' in a transaction.
    """
    # Fetch identifying tuple
    run = get_run(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    now = _now_utc()
    sql = text(
        """
        UPDATE ingest_runs
        SET status = 'running',
            started_at = :now,
            updated_at = :now
        WHERE id = :id
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  created_at, updated_at
        """
    )
    def _do_update() -> Dict[str, Any]:
        with engine.begin() as conn:
            row = conn.execute(sql, {"id": run_id, "now": _now_utc()}).mappings().first()
        if not row:
            raise ValueError(f"Run {run_id} not found on update")
        return _row_to_run(row)

    try:
        return _do_update()
    except IntegrityError as exc:
        # Another row is already running due to partial unique index.
        # If it looks stale (no heartbeat), auto-unlock it once and retry.
        unlocked = _try_unlock_stale_running_conflict(
            project_id=run["project_id"],
            marketplace_code=run["marketplace_code"],
            job_code=run["job_code"],
        )
        if unlocked:
            try:
                return _do_update()
            except IntegrityError:
                pass
        raise RunAlreadyRunningError(
            f"Another run is already running for project_id={run['project_id']}, "
            f"marketplace_code={run['marketplace_code']}, job_code={run['job_code']}"
        ) from exc


def start_run(run_id: int) -> Dict[str, Any]:
    return _set_running_if_no_conflict(run_id)


def ttl_seconds_for_job(marketplace_code: str, job_code: str) -> int:
    return _JOB_TTL_SECONDS.get((marketplace_code, job_code), INGEST_STUCK_TTL_SECONDS_DEFAULT)


def get_active_run(
    project_id: int,
    marketplace_code: str,
    job_code: str,
    *,
    conn=None,
) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT id, schedule_id, project_id, marketplace_code, job_code,
               triggered_by, status,
               started_at, finished_at, duration_ms,
               error_message, error_trace, stats_json, params_json,
               heartbeat_at, celery_task_id, meta_json,
               created_at, updated_at
        FROM ingest_runs
        WHERE project_id = :project_id
          AND marketplace_code = :marketplace_code
          AND job_code = :job_code
          AND status IN ('queued', 'running')
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    params = {"project_id": project_id, "marketplace_code": marketplace_code, "job_code": job_code}
    if conn is None:
        with engine.connect() as _conn:
            row = _conn.execute(sql, params).mappings().first()
    else:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row) if row else None


def is_stuck(run: Dict[str, Any], now: datetime, ttl_seconds: int) -> bool:
    last_activity = (
        run.get("heartbeat_at")
        or run.get("updated_at")
        or run.get("started_at")
        or run.get("created_at")
    )
    if not last_activity:
        return True
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - last_activity).total_seconds() > ttl_seconds


def mark_run_timeout(
    run_id: int,
    reason_code: str,
    reason_text: str,
    actor: str,
    *,
    conn=None,
) -> Optional[Dict[str, Any]]:
    now = _now_utc()
    import json as json_module

    meta_patch_str = json_module.dumps(
        {
            "system_action": {
                "type": "timeout",
                "reason_code": reason_code,
                "actor": actor,
                "at": now.isoformat(),
            }
        },
        ensure_ascii=False,
    )
    sql = text(
        """
        UPDATE ingest_runs
        SET status = 'timeout',
            finished_at = :now,
            error_message = :error_message,
            meta_json = COALESCE(meta_json, '{}'::jsonb) || CAST(:meta_patch AS jsonb),
            updated_at = :now
        WHERE id = :id
          AND status IN ('queued', 'running')
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  heartbeat_at, celery_task_id, meta_json,
                  created_at, updated_at
        """
    )
    params = {
        "id": run_id,
        "now": now,
        "error_message": (reason_text or "")[:500],
        "meta_patch": meta_patch_str,
    }
    if conn is None:
        with engine.begin() as _conn:
            row = _conn.execute(sql, params).mappings().first()
    else:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row) if row else None


def mark_run_skipped(
    run_id: int,
    reason_code: str,
    actor: str,
    reason_text: str | None = None,
    *,
    conn=None,
) -> Optional[Dict[str, Any]]:
    now = _now_utc()
    import json as json_module

    meta_patch_str = json_module.dumps(
        {
            "system_action": {
                "type": "skipped",
                "reason_code": reason_code,
                "actor": actor,
                "at": now.isoformat(),
            }
        },
        ensure_ascii=False,
    )
    sql = text(
        """
        UPDATE ingest_runs
        SET status = 'skipped',
            finished_at = :now,
            error_message = COALESCE(:error_message, error_message),
            meta_json = COALESCE(meta_json, '{}'::jsonb) || CAST(:meta_patch AS jsonb),
            updated_at = :now
        WHERE id = :id
          AND status IN ('queued', 'running')
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  heartbeat_at, celery_task_id, meta_json,
                  created_at, updated_at
        """
    )
    params = {
        "id": run_id,
        "now": now,
        "meta_patch": meta_patch_str,
        "error_message": (reason_text or "")[:500] if reason_text else None,
    }
    if conn is None:
        with engine.begin() as _conn:
            row = _conn.execute(sql, params).mappings().first()
    else:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row) if row else None


def set_run_celery_task_id(run_id: int, task_id: str, *, conn=None) -> bool:
    sql = text(
        """
        UPDATE ingest_runs
        SET celery_task_id = :task_id,
            updated_at = :now
        WHERE id = :id
        """
    )
    now = _now_utc()
    params = {"id": run_id, "task_id": task_id, "now": now}
    if conn is None:
        with engine.begin() as _conn:
            res = _conn.execute(sql, params)
    else:
        res = conn.execute(sql, params)
    return (res.rowcount or 0) > 0


def compute_lock_key(project_id: int, marketplace_code: str, job_code: str) -> int:
    """Compute stable int64 for advisory lock."""
    import hashlib
    import struct

    raw = f"{project_id}:{marketplace_code}:{job_code}".encode("utf-8")
    digest = hashlib.sha1(raw).digest()[:8]
    return struct.unpack(">q", digest)[0]


def try_advisory_xact_lock(lock_key: int, *, conn) -> bool:
    row = conn.execute(
        text("SELECT pg_try_advisory_xact_lock(:lock_key) AS ok"),
        {"lock_key": lock_key},
    ).mappings().first()
    return bool(row["ok"]) if row else False


def finish_run_success(run_id: int, stats_json: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    now = _now_utc()
    run = get_run(run_id)
    if not run:
        return None
    duration_ms = None
    if run["started_at"]:
        duration_ms = int((now - run["started_at"]).total_seconds() * 1000)

    import json as json_module
    
    # Handle stats_json: convert to JSON string or NULL
    if stats_json is not None:
        stats_json_str = json_module.dumps(stats_json, ensure_ascii=False)
        stats_json_sql = "CAST(:stats_json AS jsonb)"
    else:
        stats_json_str = None
        stats_json_sql = "NULL"

    # CAS: only update if still in 'running' status to prevent race conditions
    sql = text(
        f"""
        UPDATE ingest_runs
        SET status = 'success',
            finished_at = :now,
            duration_ms = :duration_ms,
            stats_json = {stats_json_sql},
            updated_at = :now
        WHERE id = :id AND status = 'running'
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  created_at, updated_at
        """
    )
    params = {
        "id": run_id,
        "now": now,
        "duration_ms": duration_ms,
    }
    if stats_json_str is not None:
        params["stats_json"] = stats_json_str
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row) if row else None


def finish_run_failed(
    run_id: int,
    error_message: str,
    error_trace: str,
    stats_json: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    now = _now_utc()
    run = get_run(run_id)
    if not run:
        return None
    duration_ms = None
    if run["started_at"]:
        duration_ms = int((now - run["started_at"]).total_seconds() * 1000)

    import json as json_module
    
    # Handle stats_json: convert to JSON string or NULL
    if stats_json is not None:
        stats_json_str = json_module.dumps(stats_json, ensure_ascii=False)
        stats_json_sql = "CAST(:stats_json AS jsonb)"
    else:
        stats_json_str = None
        stats_json_sql = "NULL"

    # CAS: only update if still in 'running' status to prevent race conditions
    sql = text(
        f"""
        UPDATE ingest_runs
        SET status = 'failed',
            finished_at = :now,
            duration_ms = :duration_ms,
            error_message = :error_message,
            error_trace = :error_trace,
            stats_json = {stats_json_sql},
            updated_at = :now
        WHERE id = :id AND status = 'running'
        RETURNING id, schedule_id, project_id, marketplace_code, job_code,
                  triggered_by, status,
                  started_at, finished_at, duration_ms,
                  error_message, error_trace, stats_json, params_json,
                  created_at, updated_at
        """
    )
    params = {
        "id": run_id,
        "now": now,
        "duration_ms": duration_ms,
        "error_message": error_message[:500],
        "error_trace": error_trace[:50000],
    }
    if stats_json_str is not None:
        params["stats_json"] = stats_json_str
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
    return _row_to_run(row) if row else None


def get_runs(
    project_id: int,
    marketplace_code: Optional[str] = None,
    job_code: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List runs for project with optional filters, newest first."""
    _debug_log(
        "services/ingest/runs.py:get_runs",
        "get_runs entry",
        {
            "project_id": project_id,
            "marketplace_code": marketplace_code,
            "job_code": job_code,
            "status": status,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "limit": limit,
        },
        hypothesis_id="RUNS_500",
    )
    where_clauses = ["project_id = :project_id"]
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit}

    if marketplace_code:
        where_clauses.append("marketplace_code = :marketplace_code")
        params["marketplace_code"] = marketplace_code
    if job_code:
        where_clauses.append("job_code = :job_code")
        params["job_code"] = job_code
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if date_from:
        where_clauses.append("started_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("started_at <= :date_to")
        params["date_to"] = date_to

    where_sql = " AND ".join(where_clauses)
    cols = _get_ingest_runs_columns()
    optional = ["params_json", "heartbeat_at", "celery_task_id", "meta_json"]
    select_optional = []
    for c in optional:
        if c in cols:
            select_optional.append(c)
        else:
            select_optional.append(f"NULL AS {c}")
    select_sql = ",\n               ".join(
        [
            "id",
            "schedule_id",
            "project_id",
            "marketplace_code",
            "job_code",
            "triggered_by",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "error_message",
            "error_trace",
            "stats_json",
            *select_optional,
            "created_at",
            "updated_at",
        ]
    )
    sql = text(
        f"""
        SELECT {select_sql}
        FROM ingest_runs
        WHERE {where_sql}
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT :limit
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
    except ProgrammingError as exc:
        # Most common cause in fresh envs: migrations not applied -> table missing.
        msg = str(exc).lower()
        if "ingest_runs" in msg and ("does not exist" in msg or "undefinedtable" in msg):
            _debug_log(
                "services/ingest/runs.py:get_runs",
                "ingest_runs table missing (return empty)",
                {"project_id": project_id},
                hypothesis_id="RUNS_TABLE_MISSING",
            )
            return []
        _debug_log(
            "services/ingest/runs.py:get_runs",
            "get_runs ProgrammingError",
            {"error": str(exc), "where_sql": where_sql, "params_keys": list(params.keys())},
            hypothesis_id="RUNS_500",
        )
        raise
    except Exception as exc:
        _debug_log(
            "services/ingest/runs.py:get_runs",
            "get_runs query failed",
            {"error": str(exc), "where_sql": where_sql, "params_keys": list(params.keys()), "has_columns_cache": _INGEST_RUNS_COLUMNS_CACHE is not None},
            hypothesis_id="RUNS_500",
        )
        raise
    return [_row_to_run(row) for row in rows]


def get_last_run(
    project_id: int,
    marketplace_code: str,
    job_code: str,
) -> Optional[Dict[str, Any]]:
    """Get the most recent run for a specific (project, marketplace, job_code)."""
    sql = text(
        """
        SELECT id, schedule_id, project_id, marketplace_code, job_code,
               triggered_by, status,
               started_at, finished_at, duration_ms,
               error_message, error_trace, stats_json, params_json,
               heartbeat_at, celery_task_id, meta_json,
               created_at, updated_at
        FROM ingest_runs
        WHERE project_id = :project_id
          AND marketplace_code = :marketplace_code
          AND job_code = :job_code
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
                "job_code": job_code,
            },
        ).mappings().first()
    return _row_to_run(row) if row else None


def has_active_run(
    project_id: int,
    marketplace_code: str,
    job_code: str,
) -> bool:
    """Check if there's an active (running or queued) run for a specific job."""
    sql = text(
        """
        SELECT COUNT(*) as count
        FROM ingest_runs
        WHERE project_id = :project_id
          AND marketplace_code = :marketplace_code
          AND job_code = :job_code
          AND status IN ('running', 'queued')
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
                "job_code": job_code,
            },
        ).scalar()
    return result > 0 if result else False

