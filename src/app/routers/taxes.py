"""Taxes router: tax profile, tax statements, build endpoints."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.taxes import (
    BuildTaxRequest,
    BuildTaxResponse,
    TaxProfileResponse,
    TaxProfileUpdate,
    TaxStatementResponse,
)
from app.db_taxes import (
    get_tax_profile,
    get_latest_tax_statement,
    list_tax_statements,
    upsert_tax_profile,
)
from app.services.ingest.runs import create_run_queued
from app.services.ingest.registry import IngestJobNotFound, get_job_definition
from app.tasks.ingest_execute import execute_ingest
from app.utils.periods import ensure_period


router = APIRouter(prefix="/api/v1", tags=["taxes"])


@router.get(
    "/projects/{project_id}/taxes/profile",
    response_model=TaxProfileResponse,
)
async def get_tax_profile_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get tax profile for a project."""
    profile = get_tax_profile(project_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax profile not found",
        )
    return TaxProfileResponse(**profile)


@router.put(
    "/projects/{project_id}/taxes/profile",
    response_model=TaxProfileResponse,
)
async def update_tax_profile_endpoint(
    body: TaxProfileUpdate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Update tax profile for a project (admin only)."""
    params_json = body.params_json if body.params_json is not None else {}
    
    profile = upsert_tax_profile(
        project_id=project_id,
        model_code=body.model_code,
        params_json=params_json,
    )
    
    return TaxProfileResponse(**profile)


@router.get(
    "/projects/{project_id}/taxes/statements",
    response_model=List[TaxStatementResponse],
)
async def list_tax_statements_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_id: Optional[int] = Query(None, description="Filter by period_id"),
    date_from: Optional[date] = Query(None, description="Filter by period date_from"),
    date_to: Optional[date] = Query(None, description="Filter by period date_to"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List tax statements for a project with optional filters."""
    statements = list_tax_statements(
        project_id=project_id,
        period_id=period_id,
        date_from=date_from,
        date_to=date_to,
    )
    
    return [TaxStatementResponse(**stmt) for stmt in statements]


@router.get(
    "/projects/{project_id}/taxes/statements/latest",
    response_model=TaxStatementResponse,
)
async def get_latest_tax_statement_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_id: int = Query(..., description="Period ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get latest tax statement snapshot for a project and period."""
    statement = get_latest_tax_statement(project_id=project_id, period_id=period_id)
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax statement not found",
        )
    return TaxStatementResponse(**statement)


@router.post(
    "/projects/{project_id}/taxes/build",
    response_model=BuildTaxResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_tax_statement_endpoint(
    body: BuildTaxRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Build tax statement for a project and period (admin only).
    
    Creates an ingest_run with build_tax_statement job and enqueues execution.
    """
    # Validate job definition
    job_def = get_job_definition("build_tax_statement")
    if not job_def:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="build_tax_statement job not found",
        )
    
    # Resolve period_id
    period_id: int
    if body.period_id:
        period_id = body.period_id
    else:
        # Ensure period exists
        if not body.date_from or not body.date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from and date_to are required when period_id is not provided",
            )
        period_id = ensure_period("wb_week", body.date_from, body.date_to)
    
    # Create run with params_json
    try:
        run = create_run_queued(
            project_id=project_id,
            marketplace_code="internal",
            job_code="build_tax_statement",
            schedule_id=None,
            triggered_by="api",
            params_json={"period_id": period_id},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    
    # Enqueue execution
    try:
        execute_ingest.delay(run["id"])
    except IngestJobNotFound as exc:
        # Mark failed immediately if no job found
        from app.services.ingest.runs import finish_run_failed
        
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
    
    return BuildTaxResponse(
        run_id=run["id"],
        status="queued",
        project_id=project_id,
        period_id=period_id,
    )
