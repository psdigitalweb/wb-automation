from __future__ import annotations

from datetime import datetime, timezone

from app.celery_app import celery_app
from app.db import engine
from app.services.ingest.schedules import due_schedules, mark_dispatched
from app.services.ingest import runs as runs_service


@celery_app.task(name="app.tasks.ingest_dispatcher.dispatch_due_schedules")
def dispatch_due_schedules() -> int:
    """Celery Beat task: dispatch due ingestion schedules.

    - Selects enabled schedules with next_run_at <= now (UTC)
    - Creates ingest_runs with status 'queued'
    - Enqueues execute_ingest task per run
    - Recalculates schedule.next_run_at from now

    Returns number of dispatched runs.
    """
    from app.tasks.ingest_execute import execute_ingest  # Local import for Celery
    from app.services.scheduling.cron import compute_next_run

    now = datetime.now(timezone.utc)
    schedules = due_schedules(now=now)
    dispatched = 0

    for schedule in schedules:
        project_id = schedule["project_id"]
        marketplace_code = schedule["marketplace_code"]
        job_code = schedule["job_code"]

        # Compute next_run_at from current *now* (persisted regardless of dispatch/skip when active alive)
        next_run_at = compute_next_run(
            cron_expr=schedule["cron_expr"],
            timezone=schedule["timezone"],
            from_dt=now,
        )

        run_id: int | None = None

        # Single-flight + stuck detection under advisory lock.
        with engine.begin() as conn:
            lock_key = runs_service.compute_lock_key(project_id, marketplace_code, job_code)
            if not runs_service.try_advisory_xact_lock(lock_key, conn=conn):
                # Another dispatcher/actor is handling this (best-effort). Do not create a run.
                continue

            active = runs_service.get_active_run(
                project_id=project_id,
                marketplace_code=marketplace_code,
                job_code=job_code,
                conn=conn,
            )
            if active:
                ttl = runs_service.ttl_seconds_for_job(marketplace_code, job_code)
                if not runs_service.is_stuck(active, now=now, ttl_seconds=ttl):
                    # Active run is alive -> do NOT create a new run.
                    run_id = None
                else:
                    runs_service.mark_run_timeout(
                        active["id"],
                        reason_code="scheduler_stuck",
                        reason_text=f"No heartbeat > {ttl}s",
                        actor="scheduler",
                        conn=conn,
                    )

            if not active or (active and runs_service.is_stuck(active, now=now, ttl_seconds=runs_service.ttl_seconds_for_job(marketplace_code, job_code))):
                run = runs_service.create_run_queued(
                    project_id=project_id,
                    marketplace_code=marketplace_code,
                    job_code=job_code,
                    schedule_id=schedule["id"],
                    triggered_by="schedule",
                    conn=conn,
                )
                run_id = int(run["id"])

        if run_id is None:
            # Active run is alive; mark schedule as dispatched to avoid repeated due selection.
            mark_dispatched(schedule_id=schedule["id"], next_run_at=next_run_at)
            continue

        # Enqueue worker task (after run committed)
        res = execute_ingest.delay(run_id)
        runs_service.set_run_celery_task_id(run_id, res.id)

        mark_dispatched(schedule_id=schedule["id"], next_run_at=next_run_at)
        dispatched += 1
    return dispatched


# Backward-compat alias (older Beat/task name)
@celery_app.task(name="app.tasks.ingest.dispatch_due_schedules")
def dispatch_due_schedules_legacy() -> int:
    return dispatch_due_schedules()

