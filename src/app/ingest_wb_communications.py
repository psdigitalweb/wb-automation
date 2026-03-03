"""WB Communications ingest: read-only collection of feedbacks and questions.

Uses time-window pagination, filters by active_nm_ids (FBS stock qty > 0).
Watermark: last_date_to per entity_type, updated only after successful chunk.
Mode: default incremental; params_json.mode == "reviews_backfill" for full archive backfill.
"""

import json
import os
from datetime import date as date_type, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text

from app.db import engine
from app.db_stocks import get_active_fbs_nm_ids
from app.db_wb_analytics import get_wb_nm_ids_for_project
from app.db_wb_backfill_state import (
    JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL,
    ensure_backfill_state_created,
    get_backfill_state,
    mark_backfill_state_completed,
    mark_backfill_state_failed,
    mark_backfill_state_paused,
    upsert_backfill_state_running,
)
from app.wb.communications_client import WBCommunicationsClient

OVERLAP_SEC = 6 * 3600
FEEDBACK_DAILY_DAYS = 120
QUESTION_DAILY_DAYS = 120
BATCH_UPSERT_SIZE = 1000
MAX_FEEDBACK_SKIP = 199990
QUESTIONS_TAKE_PLUS_SKIP_MAX = 10000
WINDOW_DAYS = 7


def _nm_id(x: Dict[str, Any]) -> Optional[int]:
    """Safe extract nm_id from productDetails. Returns None if missing or invalid."""
    try:
        pd = x.get("productDetails") or {}
        nm = pd.get("nmId") or pd.get("nm_id")
        return int(nm) if nm is not None else None
    except (ValueError, TypeError):
        return None


def _get_use_sandbox(project_id: int) -> bool:
    """Read use_sandbox from project_marketplaces.settings_json->'wb_communications'->>'use_sandbox'."""
    sql = text("""
        SELECT pm.settings_json->'wb_communications'->>'use_sandbox' AS use_sandbox
        FROM project_marketplaces pm
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE pm.project_id = :project_id AND m.code = 'wildberries'
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"project_id": project_id}).mappings().first()
    if not row or not row.get("use_sandbox"):
        return False
    return str(row["use_sandbox"]).lower() in ("true", "1", "yes")


def _load_watermark(project_id: int, entity_type: str, conn) -> Optional[int]:
    row = conn.execute(
        text("SELECT last_date_to FROM wb_communications_watermarks WHERE project_id = :pid AND entity_type = :et"),
        {"pid": project_id, "et": entity_type},
    ).mappings().first()
    return int(row["last_date_to"]) if row and row.get("last_date_to") is not None else None


def _update_watermark(project_id: int, entity_type: str, last_date_to: int, conn) -> None:
    """Upsert watermark. last_date_to = GREATEST(existing, new) for monotonicity."""
    conn.execute(
        text("""
            INSERT INTO wb_communications_watermarks (project_id, entity_type, last_date_to, updated_at)
            VALUES (:pid, :et, :last_date_to, now())
            ON CONFLICT (project_id, entity_type) DO UPDATE SET
                last_date_to = GREATEST(wb_communications_watermarks.last_date_to, EXCLUDED.last_date_to),
                updated_at = now()
        """),
        {"pid": project_id, "et": entity_type, "last_date_to": last_date_to},
    )


def _parse_created_date(s: Any) -> Optional[datetime]:
    """Parse createdDate from API (ISO string) to datetime."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s.replace(tzinfo=timezone.utc) if s.tzinfo is None else s
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _bulk_upsert_feedbacks(
    conn,
    project_id: int,
    run_id: int,
    snapshot_at: datetime,
    rows: List[Dict[str, Any]],
    is_archived: bool = False,
    source_endpoint: str = "feedbacks",
) -> int:
    if not rows:
        return 0
    # last_seen_at for idempotency and debugging
    last_seen_at = snapshot_at
    sql = text("""
        INSERT INTO wb_feedback_snapshots (
            project_id, external_id, nm_id, snapshot_at, ingest_run_id,
            product_valuation, created_date, is_answered, has_media, raw,
            is_archived, source_endpoint, last_seen_at
        ) VALUES (
            :project_id, :external_id, :nm_id, :snapshot_at, :ingest_run_id,
            :product_valuation, :created_date, :is_answered, :has_media, CAST(:raw AS jsonb),
            :is_archived, :source_endpoint, :last_seen_at
        )
        ON CONFLICT (project_id, external_id) DO UPDATE SET
            nm_id = EXCLUDED.nm_id,
            snapshot_at = EXCLUDED.snapshot_at,
            ingest_run_id = EXCLUDED.ingest_run_id,
            product_valuation = EXCLUDED.product_valuation,
            created_date = EXCLUDED.created_date,
            is_answered = EXCLUDED.is_answered,
            has_media = EXCLUDED.has_media,
            raw = EXCLUDED.raw,
            is_archived = EXCLUDED.is_archived,
            source_endpoint = EXCLUDED.source_endpoint,
            last_seen_at = EXCLUDED.last_seen_at
    """)
    n = 0
    for i in range(0, len(rows), BATCH_UPSERT_SIZE):
        batch = rows[i : i + BATCH_UPSERT_SIZE]
        for r in batch:
            conn.execute(
                sql,
                {
                    "project_id": project_id,
                    "external_id": r["external_id"],
                    "nm_id": r.get("nm_id"),
                    "snapshot_at": snapshot_at,
                    "ingest_run_id": run_id,
                    "product_valuation": r.get("product_valuation"),
                    "created_date": r.get("created_date"),
                    "is_answered": r.get("is_answered"),
                    "has_media": r.get("has_media"),
                    "raw": json.dumps(r["raw"], ensure_ascii=False) if r.get("raw") else None,
                    "is_archived": is_archived,
                    "source_endpoint": source_endpoint,
                    "last_seen_at": last_seen_at,
                },
            )
            n += 1
    return n


def _bulk_upsert_questions(
    conn,
    project_id: int,
    run_id: int,
    snapshot_at: datetime,
    rows: List[Dict[str, Any]],
) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO wb_question_snapshots (
            project_id, external_id, nm_id, snapshot_at, ingest_run_id,
            created_date, is_answered, raw
        ) VALUES (
            :project_id, :external_id, :nm_id, :snapshot_at, :ingest_run_id,
            :created_date, :is_answered, CAST(:raw AS jsonb)
        )
        ON CONFLICT (project_id, external_id) DO UPDATE SET
            nm_id = EXCLUDED.nm_id,
            snapshot_at = EXCLUDED.snapshot_at,
            ingest_run_id = EXCLUDED.ingest_run_id,
            created_date = EXCLUDED.created_date,
            is_answered = EXCLUDED.is_answered,
            raw = EXCLUDED.raw
    """)
    n = 0
    for i in range(0, len(rows), BATCH_UPSERT_SIZE):
        batch = rows[i : i + BATCH_UPSERT_SIZE]
        for r in batch:
            conn.execute(
                sql,
                {
                    "project_id": project_id,
                    "external_id": r["external_id"],
                    "nm_id": r.get("nm_id"),
                    "snapshot_at": snapshot_at,
                    "ingest_run_id": run_id,
                    "created_date": r.get("created_date"),
                    "is_answered": r.get("is_answered"),
                    "raw": json.dumps(r["raw"], ensure_ascii=False) if r.get("raw") else None,
                },
            )
            n += 1
    return n


async def _process_feedbacks_window(
    client: WBCommunicationsClient,
    project_id: int,
    run_id: int,
    active_nm_ids: Set[int],
    date_from: int,
    date_to: int,
    snapshot_at: datetime,
    stats: Dict[str, Any],
    touch_run_fn,
) -> int:
    """Process one time window for feedbacks."""
    total_upserted = 0
    for is_answered in (False, True):
        skip = 0
        while skip <= MAX_FEEDBACK_SKIP:
            resp = await client.list_feedbacks(
                date_from=date_from,
                date_to=date_to,
                take=5000,
                skip=skip,
                order="dateDesc",
                is_answered=is_answered,
            )
            items = (resp.get("data") or {}).get("feedbacks") or []
            rows = []
            for x in items:
                nm = _nm_id(x)
                if nm is None:
                    continue
                if nm not in active_nm_ids:
                    continue
                ext_id = x.get("id") or x.get("external_id")
                if not ext_id:
                    continue
                created_dt = _parse_created_date(x.get("createdDate"))
                answer = x.get("answer")
                has_media = bool(
                    (x.get("photoLinks") and len(x.get("photoLinks", [])) > 0)
                    or (x.get("video") and (x.get("video") or {}).get("link"))
                )
                rows.append({
                    "external_id": str(ext_id),
                    "nm_id": nm,
                    "product_valuation": x.get("productValuation"),
                    "created_date": created_dt,
                    "is_answered": answer is not None,
                    "has_media": has_media,
                    "raw": x,
                })
            if rows:
                with engine.begin() as conn:
                    total_upserted += _bulk_upsert_feedbacks(conn, project_id, run_id, snapshot_at, rows)
            if len(items) < 5000:
                break
            skip += 5000
            if touch_run_fn:
                touch_run_fn()
    return total_upserted


async def _process_questions_window(
    client: WBCommunicationsClient,
    project_id: int,
    run_id: int,
    active_nm_ids: Set[int],
    date_from: int,
    date_to: int,
    snapshot_at: datetime,
    stats: Dict[str, Any],
    touch_run_fn,
) -> int:
    """Process one time window for questions. Binary-splits if take+skip would exceed 10k."""
    total_upserted = 0
    for is_answered in (False, True):
        skip = 0
        while skip + 5000 <= QUESTIONS_TAKE_PLUS_SKIP_MAX:
            resp = await client.list_questions(
                date_from=date_from,
                date_to=date_to,
                take=5000,
                skip=skip,
                order="dateDesc",
                is_answered=is_answered,
            )
            items = (resp.get("data") or {}).get("questions") or []
            rows = []
            for x in items:
                nm = _nm_id(x)
                if nm is None:
                    continue
                if nm not in active_nm_ids:
                    continue
                ext_id = x.get("id") or x.get("external_id")
                if not ext_id:
                    continue
                created_dt = _parse_created_date(x.get("createdDate"))
                answer = x.get("answer")
                rows.append({
                    "external_id": str(ext_id),
                    "nm_id": nm,
                    "created_date": created_dt,
                    "is_answered": answer is not None,
                    "raw": x,
                })
            if rows:
                with engine.begin() as conn:
                    total_upserted += _bulk_upsert_questions(conn, project_id, run_id, snapshot_at, rows)
            if len(items) < 5000:
                break
            skip += 5000
            if skip + 5000 > QUESTIONS_TAKE_PLUS_SKIP_MAX and len(items) == 5000:
                mid = (date_from + date_to) // 2
                if mid <= date_from:
                    break
                left = await _process_questions_window(
                    client, project_id, run_id, active_nm_ids,
                    date_from, mid, snapshot_at, stats, touch_run_fn,
                )
                right = await _process_questions_window(
                    client, project_id, run_id, active_nm_ids,
                    mid, date_to, snapshot_at, stats, touch_run_fn,
                )
                return total_upserted + left + right
            if touch_run_fn:
                touch_run_fn()
    return total_upserted


def _date_to_start_ts(d: date_type) -> int:
    """Start of day UTC as unix timestamp."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _date_to_end_ts(d: date_type) -> int:
    """End of day UTC as unix timestamp (last second)."""
    return _date_to_start_ts(d) + 86400 - 1


async def _process_one_window_reviews_backfill(
    client: WBCommunicationsClient,
    project_id: int,
    run_id: int,
    project_nm_ids: Set[int],
    date_from_ts: int,
    date_to_ts: int,
    snapshot_at: datetime,
    stats: Dict[str, Any],
    touch_run_fn,
) -> int:
    """Fetch active + archive feedbacks for one time window; filter by project_nm_ids; upsert. Returns total upserted."""
    total = 0
    for is_answered in (False, True):
        skip = 0
        while skip <= MAX_FEEDBACK_SKIP:
            resp = await client.list_feedbacks(
                date_from=date_from_ts,
                date_to=date_to_ts,
                take=5000,
                skip=skip,
                order="dateDesc",
                is_answered=is_answered,
            )
            items = (resp.get("data") or {}).get("feedbacks") or []
            rows = []
            for x in items:
                nm = _nm_id(x)
                if nm is None or nm not in project_nm_ids:
                    continue
                ext_id = x.get("id") or x.get("external_id")
                if not ext_id:
                    continue
                created_dt = _parse_created_date(x.get("createdDate"))
                answer = x.get("answer")
                has_media = bool(
                    (x.get("photoLinks") and len(x.get("photoLinks", [])) > 0)
                    or (x.get("video") and (x.get("video") or {}).get("link"))
                )
                rows.append({
                    "external_id": str(ext_id),
                    "nm_id": nm,
                    "product_valuation": x.get("productValuation"),
                    "created_date": created_dt,
                    "is_answered": answer is not None,
                    "has_media": has_media,
                    "raw": x,
                })
            if rows:
                with engine.begin() as conn:
                    total += _bulk_upsert_feedbacks(
                        conn, project_id, run_id, snapshot_at, rows,
                        is_archived=False, source_endpoint="feedbacks",
                    )
            if len(items) < 5000:
                break
            skip += 5000
            if touch_run_fn:
                touch_run_fn()

    for is_answered in (False, True):
        skip = 0
        while skip <= MAX_FEEDBACK_SKIP:
            resp = await client.list_feedbacks_archive(
                date_from=date_from_ts,
                date_to=date_to_ts,
                take=5000,
                skip=skip,
                order="dateDesc",
                is_answered=is_answered,
            )
            items = (resp.get("data") or {}).get("feedbacks") or []
            rows = []
            for x in items:
                nm = _nm_id(x)
                if nm is None or nm not in project_nm_ids:
                    continue
                ext_id = x.get("id") or x.get("external_id")
                if not ext_id:
                    continue
                created_dt = _parse_created_date(x.get("createdDate"))
                answer = x.get("answer")
                has_media = bool(
                    (x.get("photoLinks") and len(x.get("photoLinks", [])) > 0)
                    or (x.get("video") and (x.get("video") or {}).get("link"))
                )
                rows.append({
                    "external_id": str(ext_id),
                    "nm_id": nm,
                    "product_valuation": x.get("productValuation"),
                    "created_date": created_dt,
                    "is_answered": answer is not None,
                    "has_media": has_media,
                    "raw": x,
                })
            if rows:
                with engine.begin() as conn:
                    total += _bulk_upsert_feedbacks(
                        conn, project_id, run_id, snapshot_at, rows,
                        is_archived=True, source_endpoint="feedbacks/archive",
                    )
            if len(items) < 5000:
                break
            skip += 5000
            if touch_run_fn:
                touch_run_fn()
    return total


async def _ingest_wb_communications_reviews_backfill(
    project_id: int,
    run_id: Optional[int],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Full reviews backfill: project nm_ids, date range, active + archive; resume via wb_backfill_range_state."""
    from app.utils.get_project_marketplace_token import get_wb_token_for_project

    token = get_wb_token_for_project(project_id) or os.getenv("WB_TOKEN", "")
    if not token or token.upper() == "MOCK":
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_token",
            "domain": "wb_communications",
            "project_id": project_id,
        }

    date_from_s = params.get("date_from")
    date_to_s = params.get("date_to")
    if not date_from_s or not date_to_s:
        return {
            "ok": False,
            "reason": "missing_date_range",
            "domain": "wb_communications",
            "project_id": project_id,
        }
    try:
        date_from = date_type.fromisoformat(str(date_from_s)[:10])
        date_to = date_type.fromisoformat(str(date_to_s)[:10])
    except (ValueError, TypeError):
        return {
            "ok": False,
            "reason": "invalid_date_range",
            "domain": "wb_communications",
            "project_id": project_id,
        }

    project_nm_ids = set(get_wb_nm_ids_for_project(project_id))
    if not project_nm_ids:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_project_nm_ids",
            "domain": "wb_communications",
            "project_id": project_id,
        }

    state = get_backfill_state(
        project_id, JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL, date_from, date_to
    )
    if state and state.get("status") == "completed":
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_completed",
            "domain": "wb_communications",
            "project_id": project_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
    if state and state.get("status") == "running":
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_running_for_range",
            "domain": "wb_communications",
            "project_id": project_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

    run_id = run_id or 0
    ensure_backfill_state_created(
        project_id, JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL, date_from, date_to, run_id
    )

    cursor_date = date_from - timedelta(days=1)
    if state and state.get("status") in ("paused", "failed"):
        cd = state.get("cursor_date")
        if cd is not None:
            cursor_date = cd

    use_sandbox = _get_use_sandbox(project_id)
    client = WBCommunicationsClient(token=token, use_sandbox=use_sandbox)
    snapshot_at = datetime.now(timezone.utc)
    stats: Dict[str, Any] = {
        "feedbacks_upserted": 0,
        "domain": "wb_communications",
        "project_id": project_id,
        "mode": "reviews_backfill",
    }

    def touch_run() -> None:
        if run_id:
            try:
                from app.services.ingest import runs as runs_service
                runs_service.touch_run(run_id)
            except Exception:
                pass

    try:
        window_start = cursor_date + timedelta(days=1)
        last_window_end = cursor_date
        while window_start <= date_to:
            window_end = min(window_start + timedelta(days=WINDOW_DAYS - 1), date_to)
            date_from_ts = _date_to_start_ts(window_start)
            date_to_ts = _date_to_end_ts(window_end)
            cnt = await _process_one_window_reviews_backfill(
                client, project_id, run_id, project_nm_ids,
                date_from_ts, date_to_ts, snapshot_at, stats, touch_run,
            )
            stats["feedbacks_upserted"] += cnt
            last_window_end = window_end
            upsert_backfill_state_running(
                project_id, JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL,
                date_from, date_to, run_id,
                cursor_date=window_end,
                cursor_nm_offset=0,
                meta_json={"phase": "active", "last_date_to_ts": date_to_ts},
            )
            window_start = window_end + timedelta(days=1)
            touch_run()

        mark_backfill_state_completed(
            project_id, JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL,
            date_from, date_to, run_id, len(project_nm_ids),
        )
    except Exception as e:
        mark_backfill_state_failed(
            project_id, JOB_CODE_WB_COMMUNICATIONS_REVIEWS_BACKFILL,
            date_from, date_to, run_id,
            cursor_date=last_window_end,
            cursor_nm_offset=0,
            error_message=str(e),
        )
        raise

    stats["ok"] = True
    stats["finished_at"] = datetime.utcnow().isoformat()
    stats["date_from"] = date_from.isoformat()
    stats["date_to"] = date_to.isoformat()

    if run_id:
        try:
            from app.services.ingest import runs as runs_service
            from app.tasks.ingest_execute import execute_ingest
            if not runs_service.has_active_run(
                project_id=project_id,
                marketplace_code="internal",
                job_code="build_wb_communications_aggregates",
            ):
                build_run = runs_service.create_run_queued(
                    project_id=project_id,
                    marketplace_code="internal",
                    job_code="build_wb_communications_aggregates",
                    schedule_id=None,
                    triggered_by="chained",
                    params_json={"chained_from_job": "wb_communications", "chained_from_run_id": run_id},
                )
                execute_ingest.delay(build_run["id"])
                stats["chained_aggregates_run_id"] = build_run["id"]
        except Exception:
            pass

    return stats


async def ingest_wb_communications(
    project_id: int,
    run_id: Optional[int] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Main ingest: incremental (default) or reviews_backfill via params.mode."""
    run_params = params if params is not None else {}
    if (run_params.get("mode") or "").strip().lower() == "reviews_backfill":
        return await _ingest_wb_communications_reviews_backfill(project_id, run_id, run_params)

    # Incremental: collect feedbacks and questions for active (in-stock) nm_ids.
    from app.utils.get_project_marketplace_token import get_wb_token_for_project

    token = get_wb_token_for_project(project_id) or os.getenv("WB_TOKEN", "")
    if not token or token.upper() == "MOCK":
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_token",
            "domain": "wb_communications",
            "project_id": project_id,
        }

    active_nm_ids = set(get_active_fbs_nm_ids(project_id))
    if not active_nm_ids:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_in_stock_nm_ids",
            "domain": "wb_communications",
            "project_id": project_id,
        }

    use_sandbox = _get_use_sandbox(project_id)
    client = WBCommunicationsClient(token=token, use_sandbox=use_sandbox)
    snapshot_at = datetime.now(timezone.utc)
    now_ts = int(snapshot_at.timestamp())
    stats: Dict[str, Any] = {
        "feedbacks_upserted": 0,
        "questions_upserted": 0,
        "domain": "wb_communications",
        "project_id": project_id,
    }

    def touch_run() -> None:
        if run_id:
            try:
                from app.services.ingest import runs as runs_service
                runs_service.touch_run(run_id)
            except Exception:
                pass

    with engine.connect() as conn:
        for entity_type in ("feedback", "question"):
            wm = _load_watermark(project_id, entity_type, conn)
            date_from = (wm - OVERLAP_SEC) if wm is not None else (now_ts - 90 * 86400)
            date_to = now_ts

            window_start = date_from
            while window_start < date_to:
                chunk_end = min(window_start + WINDOW_DAYS * 86400, date_to)
                if entity_type == "feedback":
                    cnt = await _process_feedbacks_window(
                        client, project_id, run_id or 0, active_nm_ids,
                        window_start, chunk_end, snapshot_at, stats, touch_run,
                    )
                else:
                    cnt = await _process_questions_window(
                        client, project_id, run_id or 0, active_nm_ids,
                        window_start, chunk_end, snapshot_at, stats, touch_run,
                    )
                if entity_type == "feedback":
                    stats["feedbacks_upserted"] += cnt
                else:
                    stats["questions_upserted"] += cnt
                with engine.begin() as upd_conn:
                    _update_watermark(project_id, entity_type, chunk_end, upd_conn)
                window_start = chunk_end
                touch_run()

    stats["ok"] = True
    stats["finished_at"] = datetime.utcnow().isoformat()

    if run_id:
        try:
            from app.services.ingest import runs as runs_service
            from app.tasks.ingest_execute import execute_ingest
            if not runs_service.has_active_run(
                project_id=project_id,
                marketplace_code="internal",
                job_code="build_wb_communications_aggregates",
            ):
                build_run = runs_service.create_run_queued(
                    project_id=project_id,
                    marketplace_code="internal",
                    job_code="build_wb_communications_aggregates",
                    schedule_id=None,
                    triggered_by="chained",
                    params_json={"chained_from_job": "wb_communications", "chained_from_run_id": run_id},
                )
                execute_ingest.delay(build_run["id"])
                stats["chained_aggregates_run_id"] = build_run["id"]
        except Exception:
            pass

    return stats


def build_wb_communications_daily_aggregates(project_id: int, run_id: Optional[int] = None) -> Dict[str, Any]:
    """Rebuild daily tables from snapshots for last N days. Group by created_date::date + nm_id.

    wb_product_feedback_daily.total_count = count of feedbacks created on that day (per-day count),
    NOT the cumulative total per SKU. Cumulative total is in get_reviews_summary from wb_feedback_snapshots.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FEEDBACK_DAILY_DAYS)

    sql_feedback = text("""
        INSERT INTO wb_product_feedback_daily (
            project_id, snapshot_date, nm_id, total_count, avg_rating,
            cnt_1_2, cnt_with_media, cnt_unanswered, ingest_run_id
        )
        SELECT
            project_id,
            created_date::date AS snapshot_date,
            nm_id,
            COUNT(*)::int AS total_count,
            AVG(product_valuation)::numeric(5,2) AS avg_rating,
            COUNT(*) FILTER (WHERE product_valuation IN (1, 2))::int AS cnt_1_2,
            COUNT(*) FILTER (WHERE has_media = true)::int AS cnt_with_media,
            COUNT(*) FILTER (WHERE is_answered = false)::int AS cnt_unanswered,
            :run_id AS ingest_run_id
        FROM wb_feedback_snapshots
        WHERE project_id = :project_id
          AND created_date IS NOT NULL
          AND created_date >= :cutoff
          AND nm_id IS NOT NULL
        GROUP BY project_id, created_date::date, nm_id
        ON CONFLICT (project_id, snapshot_date, nm_id) DO UPDATE SET
            total_count = EXCLUDED.total_count,
            avg_rating = EXCLUDED.avg_rating,
            cnt_1_2 = EXCLUDED.cnt_1_2,
            cnt_with_media = EXCLUDED.cnt_with_media,
            cnt_unanswered = EXCLUDED.cnt_unanswered,
            ingest_run_id = EXCLUDED.ingest_run_id
    """)

    sql_questions = text("""
        INSERT INTO wb_product_questions_daily (
            project_id, snapshot_date, nm_id, total_count, cnt_unanswered, ingest_run_id
        )
        SELECT
            project_id,
            created_date::date AS snapshot_date,
            nm_id,
            COUNT(*)::int AS total_count,
            COUNT(*) FILTER (WHERE is_answered = false)::int AS cnt_unanswered,
            :run_id AS ingest_run_id
        FROM wb_question_snapshots
        WHERE project_id = :project_id
          AND created_date IS NOT NULL
          AND created_date >= :cutoff
          AND nm_id IS NOT NULL
        GROUP BY project_id, created_date::date, nm_id
        ON CONFLICT (project_id, snapshot_date, nm_id) DO UPDATE SET
            total_count = EXCLUDED.total_count,
            cnt_unanswered = EXCLUDED.cnt_unanswered,
            ingest_run_id = EXCLUDED.ingest_run_id
    """)

    with engine.begin() as conn:
        conn.execute(sql_feedback, {"project_id": project_id, "run_id": run_id, "cutoff": cutoff})
        conn.execute(sql_questions, {"project_id": project_id, "run_id": run_id, "cutoff": cutoff})

    return {
        "ok": True,
        "domain": "build_wb_communications_aggregates",
        "project_id": project_id,
        "finished_at": datetime.utcnow().isoformat(),
    }
