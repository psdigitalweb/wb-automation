from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db import engine
from app.deps import get_current_active_user, get_project_membership
from app.schemas.ingest_schedule import (
    IngestScheduleCreate,
    IngestScheduleUpdate,
    IngestScheduleResponse,
)
from app.schemas.ingest_run import (
    IngestRunResponse,
    IngestRunListResponse,
    IngestRunMarkTimeoutRequest,
    RunStatus,
    WBIngestStatusResponse,
    WBIngestRunRequest,
)
from app.schemas.ingest_job import IngestJobResponse
from app.services.ingest import schedules as schedules_service
from app.services.ingest import runs as runs_service
from app.services.ingest import jobs as jobs_service
from app.services.ingest.registry import (
    IngestJobNotFound,
    get_job_definition,
    list_job_definitions,
)
from app.services.scheduling.cron import format_cron_human_readable
from app.tasks.ingest_execute import execute_ingest


router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.get(
    "/projects/{project_id}/ingest/schedules",
    response_model=List[IngestScheduleResponse],
)
async def list_project_schedules(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    schedules = schedules_service.list_schedules(project_id=project_id)
    return [IngestScheduleResponse(**s) for s in schedules]


@router.post(
    "/projects/{project_id}/ingest/schedules",
    response_model=IngestScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_schedule(
    body: IngestScheduleCreate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    job_def = get_job_definition(body.job_code)
    if not job_def:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported job_code '{body.job_code}'",
        )
    if not job_def["supports_schedule"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Job '{body.job_code}' does not support schedules",
        )

    marketplace_code = job_def["source_code"]

    try:
        schedule = schedules_service.create_schedule(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=body.job_code,
            cron_expr=body.cron_expr,
            timezone_str=body.timezone,
            is_enabled=body.is_enabled,
        )
    except Exception as exc:
        # Most validation errors (cron/tz) are already surfaced via HTTPException from services
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return IngestScheduleResponse(**schedule)


@router.put(
    "/ingest/schedules/{schedule_id}",
    response_model=IngestScheduleResponse,
)
async def update_schedule(
    body: IngestScheduleUpdate,
    schedule_id: int = Path(..., description="Schedule ID"),
    current_user: dict = Depends(get_current_active_user),
):
    schedule = schedules_service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    updated = schedules_service.update_schedule(
        schedule_id=schedule_id,
        cron_expr=body.cron_expr,
        timezone_str=body.timezone,
        is_enabled=body.is_enabled,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return IngestScheduleResponse(**updated)


@router.delete(
    "/ingest/schedules/{schedule_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_schedule_endpoint(
    schedule_id: int = Path(..., description="Schedule ID"),
    current_user: dict = Depends(get_current_active_user),
):
    schedule = schedules_service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    deleted = schedules_service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return {"ok": True}


@router.post(
    "/ingest/schedules/{schedule_id}/run",
    response_model=IngestRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_schedule_now(
    schedule_id: int = Path(..., description="Schedule ID"),
    current_user: dict = Depends(get_current_active_user),
):
    schedule = schedules_service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    # Validate job definition and manual support
    job_def = get_job_definition(schedule["job_code"])
    if not job_def:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported job_code '{schedule['job_code']}'",
        )
    if not job_def["supports_manual"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Job '{schedule['job_code']}' does not support manual run",
        )

    project_id = schedule["project_id"]
    marketplace_code = schedule["marketplace_code"]
    job_code = schedule["job_code"]

    run_id: int | None = None
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        lock_key = runs_service.compute_lock_key(project_id, marketplace_code, job_code)
        if not runs_service.try_advisory_xact_lock(lock_key, conn=conn):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="lock_not_acquired",
            )

        active = runs_service.get_active_run(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
            conn=conn,
        )
        if active:
            ttl = runs_service.ttl_seconds_for_job(marketplace_code, job_code)
            if not runs_service.is_stuck(active, now=now, ttl_seconds=ttl):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="active_run_exists",
                )
            runs_service.mark_run_timeout(
                active["id"],
                reason_code="manual_stuck",
                reason_text=f"No heartbeat > {ttl}s",
                actor=str(current_user.get("email") or "manual"),
                conn=conn,
            )

        run = runs_service.create_run_queued(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
            schedule_id=schedule["id"],
            triggered_by="manual",
            conn=conn,
        )
        run_id = int(run["id"])

    # Fire-and-forget Celery task (after run committed)
    try:
        res = execute_ingest.delay(run_id)
        runs_service.set_run_celery_task_id(run_id, res.id)
    except IngestJobNotFound as exc:
        # Mark failed immediately if no job found
        runs_service.finish_run_failed(
            run_id=run_id,
            error_message=str(exc),
            error_trace=str(exc),
            stats_json={"ok": False, "reason": "job_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    run_after = runs_service.get_run(run_id)
    return IngestRunResponse(**(run_after or run))


@router.get(
    "/projects/{project_id}/ingest/runs",
    response_model=IngestRunListResponse,
)
async def list_project_runs(
    project_id: int = Path(..., description="Project ID"),
    marketplace_code: Optional[str] = Query(None),
    job_code: Optional[str] = Query(None),
    status_param: Optional[RunStatus] = Query(
        None,
        alias="status",
        description="Run status filter",
    ),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    if job_code:
        job_def = get_job_definition(job_code)
        if not job_def:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported job_code '{job_code}'",
            )
    if marketplace_code:
        # Allow only known source codes from job definitions
        allowed_sources = {j["source_code"] for j in list_job_definitions()}
        if marketplace_code not in allowed_sources:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported marketplace_code '{marketplace_code}'",
            )

    try:
        runs = runs_service.get_runs(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
            status=status_param,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except Exception as exc:
        # We can't rely on host filesystem logging in Docker; surface safe error detail for debugging.
        err_msg = f"{type(exc).__name__}: {str(exc)}"
        raise HTTPException(
            status_code=500,
            detail=("Failed to list ingest runs. " + err_msg)[:500],
        ) from exc

    items = [IngestRunResponse(**r) for r in runs]
    return IngestRunListResponse(items=items)


@router.get(
    "/ingest/jobs",
    response_model=List[IngestJobResponse],
)
async def list_ingest_jobs(
    current_user: dict = Depends(get_current_active_user),
):
    """
    List all available ingestion jobs with metadata for UI.
    """
    return jobs_service.list_jobs()


@router.get(
    "/ingest/runs/{run_id}",
    response_model=IngestRunResponse,
)
async def get_run(
    run_id: int = Path(..., description="Run ID"),
    current_user: dict = Depends(get_current_active_user),
):
    run = runs_service.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return IngestRunResponse(**run)


@router.post(
    "/projects/{project_id}/ingest/runs/{run_id}/mark-timeout",
    response_model=IngestRunResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_run_timeout_endpoint(
    body: IngestRunMarkTimeoutRequest,
    project_id: int = Path(..., description="Project ID"),
    run_id: int = Path(..., description="Run ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    run = runs_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.get("project_id") != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.get("status") not in ("queued", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is not active (queued/running)",
        )

    updated = runs_service.mark_run_timeout(
        run_id,
        reason_code=body.reason_code or "manual",
        reason_text=body.reason_text or "Marked timeout manually",
        actor=str(current_user.get("email") or "manual"),
    )
    if not updated:
        # Status may have changed concurrently.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run status changed",
        )
    return IngestRunResponse(**updated)


@router.get(
    "/projects/{project_id}/ingestions/wb/status",
    response_model=List[WBIngestStatusResponse],
)
async def get_wb_ingest_status(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get status of all Wildberries ingestion jobs for a project."""
    marketplace_code = "wildberries"
    
    # Get all WB job definitions
    all_jobs = list_job_definitions()
    wb_jobs = [j for j in all_jobs if j["source_code"] == marketplace_code]
    
    # Get all schedules for this project and marketplace
    schedules = schedules_service.list_schedules(project_id=project_id)
    schedules_by_job = {
        s["job_code"]: s
        for s in schedules
        if s["marketplace_code"] == marketplace_code and s["is_enabled"]
    }
    
    result = []
    for job_def in wb_jobs:
        job_code = job_def["job_code"]
        
        # Get last run
        last_run = runs_service.get_last_run(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
        )
        
        # Check if there's an active run
        is_running = runs_service.has_active_run(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
        )
        
        # Get schedule info
        schedule = schedules_by_job.get(job_code)
        has_schedule = schedule is not None
        schedule_summary = None
        if schedule:
            schedule_summary = format_cron_human_readable(schedule["cron_expr"])
        
        # Determine last run status
        last_run_at = None
        last_status = None
        if last_run:
            last_run_at = last_run.get("finished_at") or last_run.get("started_at")
            last_status = last_run.get("status")
            # If run is still active, show current status
            if last_run.get("status") in ("running", "queued"):
                last_status = last_run.get("status")
        
        result.append(
            WBIngestStatusResponse(
                job_code=job_code,
                title=job_def["title"],
                has_schedule=has_schedule,
                schedule_summary=schedule_summary,
                last_run_at=last_run_at,
                last_status=last_status,
                is_running=is_running,
            )
        )
    
    return result


@router.post(
    "/projects/{project_id}/ingestions/wb/{job_code}/run",
    response_model=IngestRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_wb_ingest_manual(
    project_id: int = Path(..., description="Project ID"),
    job_code: str = Path(..., description="Job code"),
    body: Optional[WBIngestRunRequest] = None,
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Manually trigger a Wildberries ingestion job.
    
    For jobs that require parameters (e.g., wb_finances), pass params_json in body:
    {"params_json": {"date_from": "2024-01-01", "date_to": "2024-01-31"}}
    """
    marketplace_code = "wildberries"
    
    # Validate job definition
    job_def = get_job_definition(job_code)
    if not job_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_code}' not found",
        )
    
    if job_def["source_code"] != marketplace_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{job_code}' is not a Wildberries job",
        )
    
    if not job_def["supports_manual"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Job '{job_code}' does not support manual run",
        )
    
    # Validate params_json for jobs that require it
    params_json = body.params_json if body else None
    if job_code == "wb_finances":
        if not params_json:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job 'wb_finances' requires params_json with 'date_from' and 'date_to'",
            )
        date_from = params_json.get("date_from")
        date_to = params_json.get("date_to")
        if not date_from or not date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job 'wb_finances' requires 'date_from' and 'date_to' in params_json",
            )
        # Validate date format
        try:
            from datetime import datetime
            datetime.strptime(date_from, "%Y-%m-%d")
            datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD",
            )
    
    # Check if there's already an active run
    if runs_service.has_active_run(project_id, marketplace_code, job_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_code}' is already running or queued",
        )
    
    # Get schedule if exists (optional, for linking)
    schedules = schedules_service.list_schedules(project_id=project_id)
    schedule = next(
        (s for s in schedules if s["marketplace_code"] == marketplace_code and s["job_code"] == job_code),
        None
    )
    schedule_id = schedule["id"] if schedule else None
    
    # Create run with triggered_by='manual'
    try:
        run = runs_service.create_run_queued(
            project_id=project_id,
            marketplace_code=marketplace_code,
            job_code=job_code,
            schedule_id=schedule_id,
            triggered_by="manual",
            params_json=params_json,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    # Fire-and-forget Celery task
    try:
        execute_ingest.delay(run["id"])
    except IngestJobNotFound as exc:
        # Mark failed immediately if no job found
        runs_service.finish_run_failed(
            run_id=run["id"],
            error_message=str(exc),
            error_trace=str(exc),
            stats_json={"ok": False, "reason": "job_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    return IngestRunResponse(**run)

