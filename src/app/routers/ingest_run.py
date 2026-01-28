from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from app.deps import get_current_active_user, get_project_membership
from app.services.ingest.runs import create_run_queued, has_active_run, finish_run_failed
from app.services.ingest.registry import get_job_definition, IngestJobNotFound
from app.tasks.ingest_execute import execute_ingest


IngestDomain = Literal[
    "products",
    "warehouses",
    "stocks",
    "supplier_stocks",
    "prices",
    "frontend_prices",
    "rrp_xml",
]


class IngestRunRequest(BaseModel):
    domain: IngestDomain = Field(..., description="Ingestion domain to enqueue")


class IngestRunResponse(BaseModel):
    task_id: str
    run_id: int | None = None
    domain: IngestDomain
    status: Literal["queued"]


router = APIRouter(prefix="/api/v1/projects", tags=["ingest-run"])


@router.post("/{project_id}/ingest/run", response_model=IngestRunResponse)
async def run_ingest(
    body: IngestRunRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    # Map legacy "domain" to new ingest job definition.
    job_def = get_job_definition(body.domain)
    if not job_def:
        # Literal should prevent this, but keep it safe.
        raise ValueError(f"Unsupported domain: {body.domain}")

    marketplace_code = job_def["source_code"]
    job_code = job_def["job_code"]

    # Prevent spamming queued runs from legacy UI.
    if has_active_run(project_id=project_id, marketplace_code=marketplace_code, job_code=job_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{body.domain}' is already running or queued",
        )

    run = create_run_queued(
        project_id=project_id,
        marketplace_code=marketplace_code,
        job_code=job_code,
        schedule_id=None,
        triggered_by="manual",
    )

    try:
        result = execute_ingest.delay(run["id"])
    except IngestJobNotFound as exc:
        finish_run_failed(
            run_id=run["id"],
            error_message=str(exc),
            error_trace=str(exc),
            stats_json={"ok": False, "reason": "job_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return IngestRunResponse(task_id=result.id, run_id=run["id"], domain=body.domain, status="queued")

