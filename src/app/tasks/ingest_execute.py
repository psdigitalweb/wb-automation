from __future__ import annotations

import json
import logging
import traceback
import threading

from app.celery_app import celery_app
from billiard.exceptions import SoftTimeLimitExceeded
from app.services.ingest.runs import (
    RunAlreadyRunningError,
    get_run,
    start_run,
    finish_run_success,
    finish_run_failed,
    touch_run,
    mark_run_skipped,
)
from app.services.ingest.registry import execute_ingest_job, IngestJobNotFound
from app.utils.asyncio_runner import run_async_safe

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.ingest.execute_ingest",
    soft_time_limit=30 * 60,  # 30 minutes (raises SoftTimeLimitExceeded)
    time_limit=32 * 60,       # 32 minutes (hard kill, best-effort safety net)
)
def execute_ingest(run_id: int) -> dict:
    """Worker task: execute specific ingestion job for given run."""
    
    # Load run
    run = get_run(run_id)
    if not run:
        return {"status": "not_found", "run_id": run_id}

    # Track if we've started the run (to ensure finalization in finally)
    run_started = False
    heartbeat_stop: threading.Event | None = None
    heartbeat_thread: threading.Thread | None = None
    project_id = None
    marketplace_code = None
    job_code = None

    try:
        # Attempt to transition to running (enforces single running via partial index)
        start_run(run_id)
        run_started = True

        # Heartbeat: bump updated_at while running so UI sees progress and stale-unlock works.
        heartbeat_stop = threading.Event()

        def _hb():
            while heartbeat_stop is not None and not heartbeat_stop.wait(15):
                try:
                    touch_run(run_id)
                except Exception as e:
                    logger.warning(f"execute_ingest: heartbeat failed for run_id={run_id}: {type(e).__name__}: {e}")

        heartbeat_thread = threading.Thread(
            target=_hb,
            name=f"ingest-heartbeat-{run_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        
        project_id = run["project_id"]
        marketplace_code = run["marketplace_code"]
        job_code = run["job_code"]

        # Call registered ingestion function (async)
        # Use safe async runner to handle cases where event loop may already be running
        # Force thread pool for Celery prefork workers to avoid race conditions
        stats = run_async_safe(
            execute_ingest_job(
                project_id=project_id,
                marketplace_code=marketplace_code,
                job_code=job_code,
                run_id=run_id,
            ),
            context_info={"run_id": run_id, "job_code": job_code},
            force_thread=True,  # Always use thread pool in Celery to avoid race conditions
        )
        
        logger.info(f"execute_ingest: run_async_safe completed, run_id={run_id}, stats_type={type(stats).__name__}")
        
        if not isinstance(stats, dict):
            stats = {"ok": True, "result": str(stats)}

        # If job reports ok=False, finalize as failed (contract: success means complete run).
        if isinstance(stats, dict) and stats.get("ok") is False:
            reason = (
                stats.get("reason")
                or stats.get("error")
                or stats.get("message")
                or "ingest_failed"
            )
            tb = json.dumps(stats, ensure_ascii=False)[:50000]
            logger.warning(f"execute_ingest: job returned ok=False, failing run_id={run_id}, reason={reason}")
            # Preserve debug progress (phase_label, last_request, last_events) from set_run_progress
            current = get_run(run_id)
            if current and isinstance(current.get("stats_json"), dict):
                for k in ("phase_label", "last_request", "last_events", "sleeping", "sleep_remaining_seconds"):
                    if k in current["stats_json"]:
                        stats = {**stats, k: current["stats_json"][k]}
            finish_run_failed(
                run_id=run_id,
                error_message=str(reason),
                error_trace=tb,
                stats_json=stats,
            )
            return {
                "status": "failed",
                "run_id": run_id,
                "project_id": project_id,
                "marketplace_code": marketplace_code,
                "job_code": job_code,
                "error": "job_reported_failure",
                "detail": str(reason),
                "stats": stats,
            }

        logger.info(f"execute_ingest: calling finish_run_success, run_id={run_id}")
        # Preserve debug progress from set_run_progress for UI
        current = get_run(run_id)
        if current and isinstance(current.get("stats_json"), dict):
            for k in ("phase_label", "last_request", "last_events", "sleeping", "sleep_remaining_seconds"):
                if k in current["stats_json"]:
                    stats = {**stats, k: current["stats_json"][k]}
        finish_run_success(run_id, stats_json=stats)
        logger.info(f"execute_ingest: finish_run_success completed, run_id={run_id}")
        
        return {
            "status": "success",
            "run_id": run_id,
            "project_id": project_id,
            "marketplace_code": marketplace_code,
            "job_code": job_code,
            "stats": stats,
        }
    except SoftTimeLimitExceeded as exc:
        tb = traceback.format_exc()
        if run_started:
            finish_run_failed(
                run_id=run_id,
                error_message="soft_time_limit_exceeded",
                error_trace=tb,
                stats_json={"ok": False, "reason": "timeout"},
            )
        return {"status": "failed", "run_id": run_id, "error": "timeout", "detail": str(exc)}
    except RunAlreadyRunningError as exc:
        # Concurrent active run detected - finalize current run as skipped (must not leave queued forever)
        logger.info(
            f"execute_ingest: run {run_id} skipped due to concurrent run "
            f"(project_id={run['project_id']}, marketplace={run['marketplace_code']}, job={run['job_code']})"
        )
        try:
            mark_run_skipped(
                run_id,
                reason_code="concurrent_active_run",
                actor="worker",
            )
        except Exception as e:
            logger.warning(
                f"execute_ingest: failed to mark run skipped, run_id={run_id}: {type(e).__name__}: {e}"
            )
        return {
            "status": "skipped",
            "run_id": run_id,
            "reason": "concurrent_run_forbidden",
        }
    except IngestJobNotFound as exc:
        tb = traceback.format_exc()
        # Only finalize if we started the run
        if run_started:
            finish_run_failed(
                run_id=run_id,
                error_message=str(exc),
                error_trace=tb,
                stats_json={"ok": False, "reason": "job_not_found"},
            )
        return {
            "status": "failed",
            "run_id": run_id,
            "error": "job_not_found",
            "detail": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive
        tb = traceback.format_exc()
        # Only finalize if we started the run
        if run_started:
            finish_run_failed(
                run_id=run_id,
                error_message=str(exc),
                error_trace=tb,
                stats_json={"ok": False},
            )
        return {
            "status": "failed",
            "run_id": run_id,
            "error": type(exc).__name__,
            "detail": str(exc),
        }
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)
        # Safety net: ensure run is finalized if it was started but not finished
        if run_started:
            # Double-check current status to avoid race conditions
            current_run = get_run(run_id)
            if current_run and current_run["status"] == "running":
                # Run is still in running state - this shouldn't happen but we fix it
                logger.error(
                    f"execute_ingest: run {run_id} left in running state, "
                    f"finalizing as failed (safety net)"
                )
                finish_run_failed(
                    run_id=run_id,
                    error_message="Run was left in running state (safety net finalization)",
                    error_trace="Safety net: run was not finalized by normal execution path",
                    stats_json={"ok": False, "reason": "safety_net_finalization"},
                )

