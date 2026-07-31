"""Manual project-scoped competitor review collection API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.exc import IntegrityError

from app import settings
from app.db_wb_competitor_reviews import (
    add_targets,
    create_competitor_analysis,
    create_run,
    delete_targets,
    find_active_competitor_analysis,
    find_cached_competitor_analysis,
    finish_competitor_analysis_failed,
    finish_run,
    get_competitor_analysis_state,
    get_active_run,
    get_run,
    list_reviews,
    list_targets,
    mark_target_failed,
)
from app.deps import get_project_membership, require_project_member
from app.schemas.wb_competitor_reviews import (
    AddCompetitorTargetsRequest,
    AddCompetitorTargetsResponse,
    CollectCompetitorReviewsRequest,
    CollectCompetitorReviewsResponse,
    CompetitorReviewListResponse,
    CompetitorAnalysisRunResponse,
    CompetitorAnalysisStateResponse,
    DeleteCompetitorTargetsResponse,
    GenerateCompetitorAnalysisRequest,
    GenerateCompetitorAnalysisResponse,
    CompetitorRunResponse,
    CompetitorTargetResponse,
    CompetitorTargetsResponse,
    GetCompetitorRunResponse,
)
from app.services.competitor_analysis.contracts import PIPELINE_VERSION, SCHEMA_VERSION
from app.services.competitor_analysis.input_builder import (
    build_competitor_analysis_input,
    estimate_analysis_cost,
)
from app.tasks.wb_competitor_reviews import (
    analyze_competitor_reviews_task,
    collect_competitor_reviews_task,
)


router = APIRouter(prefix="/api/v1", tags=["wildberries-competitor-reviews"])


def _run(row: dict[str, Any]) -> CompetitorRunResponse:
    return CompetitorRunResponse.model_validate(
        {key: row.get(key) for key in CompetitorRunResponse.model_fields}
    )


def _target(row: dict[str, Any]) -> dict[str, Any]:
    value = {
        key: row.get(key)
        for key in CompetitorTargetResponse.model_fields
    }
    value["analysis_estimated_cost_usd"] = estimate_analysis_cost(
        reviews_count=int(row.get("text_reviews_count") or 0),
        text_chars=int(row.get("analysis_text_chars") or 0),
    )
    return value


def _analysis_run(row: dict[str, Any] | None) -> CompetitorAnalysisRunResponse | None:
    if row is None:
        return None
    value = {
        key: row.get(key)
        for key in CompetitorAnalysisRunResponse.model_fields
    }
    value["result"] = row.get("result_json")
    return CompetitorAnalysisRunResponse.model_validate(value)


def _analysis_is_stale(target: dict[str, Any], ready: dict[str, Any] | None) -> bool:
    if ready is None:
        return False
    collected_at = target.get("last_collected_at")
    source_at = ready.get("source_last_collected_at")
    return bool(collected_at and (source_at is None or source_at < collected_at))


@router.post(
    "/projects/{project_id}/competitor-reviews/targets",
    response_model=AddCompetitorTargetsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_competitor_targets(
    request: AddCompetitorTargetsRequest,
    project_id: int = Path(..., ge=1),
    _membership: dict = Depends(require_project_member),
):
    result = add_targets(project_id, request.nm_ids)
    return AddCompetitorTargetsResponse(
        items=[_target(row) for row in result["items"]],
        added_count=result["added_count"],
        existing_count=result["existing_count"],
    )


@router.get(
    "/projects/{project_id}/competitor-reviews/targets",
    response_model=CompetitorTargetsResponse,
)
async def get_competitor_targets(
    project_id: int = Path(..., ge=1),
    _membership: dict = Depends(get_project_membership),
):
    return CompetitorTargetsResponse(
        items=[_target(row) for row in list_targets(project_id)]
    )


@router.delete(
    "/projects/{project_id}/competitor-reviews/targets",
    response_model=DeleteCompetitorTargetsResponse,
)
async def delete_competitor_targets(
    project_id: int = Path(..., ge=1),
    nm_ids: list[int] = Query(..., min_length=1, max_length=50),
    _membership: dict = Depends(require_project_member),
):
    unique_ids = list(dict.fromkeys(nm_ids))
    if any(value <= 0 for value in unique_ids):
        raise HTTPException(status_code=422, detail="nm_ids must be positive")

    rows = list_targets(project_id, nm_ids=unique_ids)
    found_ids = {int(row["nm_id"]) for row in rows}
    missing = [value for value in unique_ids if value not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Competitor targets not found: {', '.join(str(value) for value in missing[:10])}",
        )
    if get_active_run(project_id):
        raise HTTPException(
            status_code=409,
            detail="Wait for the current competitor review collection to finish",
        )
    active_analysis_ids = [
        int(row["nm_id"])
        for row in rows
        if row.get("analysis_status") in {"queued", "running"}
    ]
    if active_analysis_ids:
        raise HTTPException(
            status_code=409,
            detail=(
                "Wait for analysis to finish for nmID: "
                + ", ".join(str(value) for value in active_analysis_ids[:10])
            ),
        )

    deleted_nm_ids = delete_targets(project_id, unique_ids)
    return DeleteCompetitorTargetsResponse(
        deleted_nm_ids=deleted_nm_ids,
        deleted_count=len(deleted_nm_ids),
    )


@router.post(
    "/projects/{project_id}/competitor-reviews/collect",
    response_model=CollectCompetitorReviewsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def collect_competitor_targets(
    request: CollectCompetitorReviewsRequest,
    project_id: int = Path(..., ge=1),
    membership: dict = Depends(require_project_member),
):
    rows = list_targets(project_id, nm_ids=request.nm_ids) if request.nm_ids else list_targets(project_id)
    nm_ids = [int(row["nm_id"]) for row in rows]
    if not nm_ids:
        raise HTTPException(status_code=409, detail="No competitor products to collect")
    if len(nm_ids) > 50:
        raise HTTPException(status_code=400, detail="Collect at most 50 products per run")
    if request.nm_ids and len(nm_ids) != len(request.nm_ids):
        known = set(nm_ids)
        missing = [value for value in request.nm_ids if value not in known]
        raise HTTPException(
            status_code=404,
            detail=f"Competitor targets not found: {', '.join(str(value) for value in missing[:10])}",
        )

    active = get_active_run(project_id)
    if active:
        return CollectCompetitorReviewsResponse(run=_run(active))
    try:
        run = create_run(
            project_id,
            requested_by_user_id=membership.get("user_id"),
            nm_ids=nm_ids,
        )
    except IntegrityError:
        active = get_active_run(project_id)
        if active:
            return CollectCompetitorReviewsResponse(run=_run(active))
        raise
    try:
        collect_competitor_reviews_task.delay(int(run["id"]))
    except Exception as exc:  # noqa: BLE001
        finish_run(
            int(run["id"]),
            completed_nm_ids=[],
            failed_nm_ids=nm_ids,
            error_message="Could not queue competitor review collection",
            failed=True,
        )
        for nm_id in nm_ids:
            mark_target_failed(
                project_id,
                nm_id,
                code="queue_unavailable",
                message="Could not queue collection",
            )
        raise HTTPException(
            status_code=503,
            detail="Could not queue competitor review collection",
        ) from exc
    return CollectCompetitorReviewsResponse(run=_run(run))


@router.get(
    "/projects/{project_id}/competitor-reviews/runs/{run_id}",
    response_model=GetCompetitorRunResponse,
)
async def get_competitor_run(
    project_id: int = Path(..., ge=1),
    run_id: int = Path(..., ge=1),
    _membership: dict = Depends(get_project_membership),
):
    row = get_run(project_id, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Collection run not found")
    return GetCompetitorRunResponse(run=_run(row))


@router.get(
    "/projects/{project_id}/competitor-reviews/targets/{nm_id}/reviews",
    response_model=CompetitorReviewListResponse,
)
async def get_competitor_target_reviews(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _membership: dict = Depends(get_project_membership),
):
    result = list_reviews(project_id, nm_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="Competitor target not found")
    return CompetitorReviewListResponse.model_validate(result)


@router.get(
    "/projects/{project_id}/competitor-reviews/targets/{nm_id}/analysis",
    response_model=CompetitorAnalysisStateResponse,
)
async def get_competitor_analysis(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    _membership: dict = Depends(get_project_membership),
):
    state = get_competitor_analysis_state(project_id, nm_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Competitor target not found")
    analysis_input = build_competitor_analysis_input(project_id, nm_id)
    target = state["target"]
    return CompetitorAnalysisStateResponse(
        nm_id=nm_id,
        reviews_with_text=len(analysis_input.reviews),
        estimated_cost_usd=analysis_input.estimated_cost_usd,
        can_generate=(
            settings.WB_COMPETITOR_ANALYSIS_ENABLED
            and len(analysis_input.reviews) >= 2
        ),
        is_stale=_analysis_is_stale(target, state["latest_ready"]),
        latest=_analysis_run(state["latest"]),
        latest_ready=_analysis_run(state["latest_ready"]),
    )


@router.post(
    "/projects/{project_id}/competitor-reviews/targets/{nm_id}/analysis",
    response_model=GenerateCompetitorAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_competitor_analysis(
    request: GenerateCompetitorAnalysisRequest,
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    membership: dict = Depends(require_project_member),
):
    if not settings.WB_COMPETITOR_ANALYSIS_ENABLED:
        raise HTTPException(status_code=503, detail="Competitor analysis is disabled")
    analysis_input = build_competitor_analysis_input(project_id, nm_id)
    if len(analysis_input.reviews) < 2:
        raise HTTPException(
            status_code=409,
            detail="At least two written reviews are required",
        )
    active = find_active_competitor_analysis(analysis_input.target_id)
    if active:
        return GenerateCompetitorAnalysisResponse(
            run=_analysis_run(active),
            cached=False,
        )
    if not request.refresh:
        cached = find_cached_competitor_analysis(
            analysis_input.target_id,
            input_hash=analysis_input.input_hash,
            pipeline_version=PIPELINE_VERSION,
        )
        if cached:
            return GenerateCompetitorAnalysisResponse(
                run=_analysis_run(cached),
                cached=True,
            )
    try:
        run = create_competitor_analysis(
            target_id=analysis_input.target_id,
            requested_by_user_id=membership.get("user_id"),
            input_hash=analysis_input.input_hash,
            pipeline_version=PIPELINE_VERSION,
            schema_version=SCHEMA_VERSION,
            reviews_sent=len(analysis_input.reviews),
            source_last_collected_at=analysis_input.source_last_collected_at,
            estimated_cost_usd=analysis_input.estimated_cost_usd,
            max_cost_usd=request.max_cost_usd,
        )
    except IntegrityError:
        active = find_active_competitor_analysis(analysis_input.target_id)
        if active:
            return GenerateCompetitorAnalysisResponse(
                run=_analysis_run(active),
                cached=False,
            )
        raise
    try:
        analyze_competitor_reviews_task.delay(int(run["id"]))
    except Exception as exc:  # noqa: BLE001
        finish_competitor_analysis_failed(
            int(run["id"]),
            error_code="queue_unavailable",
            error_message="Could not queue competitor analysis",
        )
        raise HTTPException(
            status_code=503,
            detail="Could not queue competitor analysis",
        ) from exc
    return GenerateCompetitorAnalysisResponse(
        run=_analysis_run(run),
        cached=False,
    )
