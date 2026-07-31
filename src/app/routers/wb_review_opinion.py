"""Manual-only API for analysis of written Wildberries reviews."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError

from app import settings
from app.db_wb_review_opinion import (
    create_review_opinion_run,
    find_active_review_opinion_run,
    find_cached_review_opinion_run,
    finish_review_opinion_failed,
    get_latest_review_opinion_runs,
)
from app.deps import get_project_membership, require_project_member
from app.schemas.wb_review_opinion import (
    ReviewOpinionGenerateRequest,
    ReviewOpinionGenerateResponse,
    ReviewOpinionRunSummary,
    ReviewOpinionStateResponse,
)
from app.services.review_opinion.input_builder import (
    MAX_REVIEWS_SENT,
    build_review_opinion_input,
)
from app.services.review_opinion.prompt import PROMPT_VERSION, SCHEMA_VERSION
from app.services.review_opinion.service import MIN_TEXT_REVIEWS
from app.tasks.wb_review_opinion import execute_review_opinion_task


router = APIRouter(prefix="/api/v1", tags=["wildberries-review-opinion"])


def _run_summary(row: dict[str, Any]) -> ReviewOpinionRunSummary:
    return ReviewOpinionRunSummary.model_validate(
        {
            key: row.get(key)
            for key in ReviewOpinionRunSummary.model_fields
        }
    )


def _build_input_or_404(project_id: int, nm_id: int):
    try:
        return build_review_opinion_input(project_id, nm_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Product not found") from exc


@router.get(
    "/projects/{project_id}/wildberries/catalog/{nm_id}/customer-opinion",
    response_model=ReviewOpinionStateResponse,
    summary="Current manually generated customer opinion and written-review counts",
)
async def get_customer_opinion(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    membership=Depends(get_project_membership),
):
    analysis_input = _build_input_or_404(project_id, nm_id)
    runs = get_latest_review_opinion_runs(project_id, nm_id)
    latest = runs["latest"]
    ready = runs["latest_ready"]
    result = ready.get("result_json") if ready else None

    return ReviewOpinionStateResponse(
        feature_enabled=settings.WB_REVIEW_OPINION_ENABLED,
        nm_id=nm_id,
        reviews_total=analysis_input.reviews_total,
        reviews_with_text=analysis_input.reviews_with_text,
        reviews_sent=analysis_input.reviews_sent,
        max_reviews_sent=MAX_REVIEWS_SENT,
        can_analyze=analysis_input.reviews_sent >= MIN_TEXT_REVIEWS,
        can_generate=membership.get("role") != "viewer",
        stale=bool(ready and ready.get("input_hash") != analysis_input.input_hash),
        latest_run=_run_summary(latest) if latest else None,
        result_run_id=int(ready["id"]) if ready else None,
        result_created_at=ready.get("finished_at") if ready else None,
        result=result,
    )


@router.post(
    "/projects/{project_id}/wildberries/catalog/{nm_id}/customer-opinion/generate",
    response_model=ReviewOpinionGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue analysis after an explicit operator command",
)
async def generate_customer_opinion(
    request: ReviewOpinionGenerateRequest,
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    membership=Depends(require_project_member),
):
    if not settings.WB_REVIEW_OPINION_ENABLED:
        raise HTTPException(status_code=503, detail="Customer opinion analysis is disabled")

    analysis_input = _build_input_or_404(project_id, nm_id)
    if analysis_input.reviews_sent < MIN_TEXT_REVIEWS:
        raise HTTPException(
            status_code=409,
            detail="At least two written reviews are required",
        )

    active = find_active_review_opinion_run(project_id, nm_id)
    if active:
        return ReviewOpinionGenerateResponse(
            run=_run_summary(active),
            reused=True,
            message="Analysis is already queued or running",
        )

    if not request.refresh:
        cached = find_cached_review_opinion_run(
            project_id,
            nm_id,
            input_hash=analysis_input.input_hash,
            prompt_version=PROMPT_VERSION,
            model=settings.OPENROUTER_REVIEW_MODEL,
        )
        if cached:
            return ReviewOpinionGenerateResponse(
                run=_run_summary(cached),
                reused=True,
                message="Current result is already up to date",
            )

    try:
        run = create_review_opinion_run(
            project_id=project_id,
            requested_by_user_id=membership.get("user_id"),
            nm_id=nm_id,
            input_hash=analysis_input.input_hash,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            model=settings.OPENROUTER_REVIEW_MODEL,
            reasoning_effort=settings.OPENROUTER_REVIEW_REASONING_EFFORT,
            reviews_total=analysis_input.reviews_total,
            reviews_with_text=analysis_input.reviews_with_text,
            reviews_sent=analysis_input.reviews_sent,
        )
    except IntegrityError:
        active = find_active_review_opinion_run(project_id, nm_id)
        if active:
            return ReviewOpinionGenerateResponse(
                run=_run_summary(active),
                reused=True,
                message="Analysis is already queued or running",
            )
        raise

    try:
        execute_review_opinion_task.delay(int(run["id"]))
    except Exception as exc:  # noqa: BLE001
        finish_review_opinion_failed(
            int(run["id"]),
            error_code="queue_unavailable",
            error_message="Could not queue the analysis",
        )
        raise HTTPException(
            status_code=503,
            detail="Could not queue the analysis",
        ) from exc

    return ReviewOpinionGenerateResponse(
        run=_run_summary(run),
        reused=False,
        message="Analysis queued by operator command",
    )
