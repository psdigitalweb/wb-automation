"""Product-facing SEO module endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import delete, desc, select

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoGenerationRun, SeoSkuQuerySet, SeoSkuQuerySetItem
from app.schemas.seo_products import (
    SeoCategorySelectedQueryApplyRequest,
    SeoCategorySelectedQueryListResponse,
    SeoCategorySelectedQuerySaveRequest,
    SeoProductAnalysisRunRequest,
    SeoProductAnalysisRunResponse,
    SeoProductAnalysisStatusResponse,
    SeoProductListResponse,
    SeoProductReadinessResponse,
    SeoProductSummaryResponse,
    SeoProductionQuerySelectionSaveRequest,
    SeoProductionQuerySelectionPreviewResponse,
    SeoProductionQuerySelectionRunResponse,
    SeoQuerySelectionRunRequest,
    SeoQuerySelectionUpdateRequest,
    SeoQuerySetResponse,
)
from app.services.seo.query_meaning_matcher.canonical import stable_hash
from app.services.seo.query_pipeline.normalization import normalize_query_text
from app.services.seo.production_query_selection import (
    ProductionQuerySelectionError,
    build_production_query_selection_preview,
    run_production_query_selection,
)
from app.services.seo.products import (
    apply_category_selected_queries_to_product,
    get_product_analysis_status,
    get_product_readiness,
    get_product_seo_summary,
    get_query_selection,
    list_category_selected_queries,
    list_seo_products,
    run_product_analysis,
    run_query_selection,
    save_category_selected_queries,
    update_query_selection,
)


router = APIRouter(prefix="/api/v1", tags=["seo-products"])


def _production_query_selection_response_from_run(row: SeoGenerationRun) -> SeoProductionQuerySelectionRunResponse:
    response_payload = row.response_payload if isinstance(row.response_payload, dict) else {}
    request_payload = row.request_payload if isinstance(row.request_payload, dict) else {}
    request_input = request_payload.get("input") if isinstance(request_payload.get("input"), dict) else {}
    return SeoProductionQuerySelectionRunResponse(
        run_id=int(row.id),
        project_id=int(row.project_id),
        nm_id=int(request_payload.get("nm_id") or 0),
        category_id=int(row.category_id),
        status=str(row.status),
        meaning_lines=response_payload.get("meaning_lines") or [],
        selected_queries=response_payload.get("selected_queries") or [],
        operator_candidates=response_payload.get("operator_candidates") or {},
        model=row.model_name,
        prompt_version=str(response_payload.get("prompt_version") or request_payload.get("prompt_version") or ""),
        artifact_path=response_payload.get("artifact_path"),
        candidate_count=int(response_payload.get("candidate_count_total") or request_input.get("candidate_count_total") or 0),
        sent_candidate_count=int(response_payload.get("candidate_count_sent") or request_input.get("candidate_count_sent") or 0),
        input_prompt=None,
    )


def _save_production_query_selection(
    session,
    *,
    project_id: int,
    nm_id: int,
    request: SeoProductionQuerySelectionSaveRequest,
) -> SeoQuerySetResponse:
    # In the production operator flow "Save selection" is the approval action.
    # Keep the DB-compatible status value, but do not expose a separate
    # draft/confirmed step to the user.
    query_set = session.scalars(
        select(SeoSkuQuerySet)
        .where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(request.category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
            SeoSkuQuerySet.status.in_(("draft", "confirmed")),
        )
        .order_by(desc(SeoSkuQuerySet.status == "confirmed"), desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))
    ).first()
    if query_set is None:
        query_set = SeoSkuQuerySet(
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
            status="confirmed",
        )
        session.add(query_set)
        session.flush()
    else:
        query_set.status = "confirmed"

    stale_query_sets = session.scalars(
        select(SeoSkuQuerySet).where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(request.category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
            SeoSkuQuerySet.status.in_(("draft", "confirmed")),
            SeoSkuQuerySet.id != int(query_set.id),
        )
    ).all()
    for stale in stale_query_sets:
        session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(stale.id)))
        session.delete(stale)

    query_set.matcher_version = "production_query_selection"
    query_set.atoms_version = "production_query_selection_v1"
    query_set.source_hash = stable_hash(
        {
            "kind": "production_query_selection_save",
            "run_id": request.run_id,
            "items": [item.model_dump(mode="json") for item in request.items],
        }
    )
    session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(query_set.id)))
    seen: set[str] = set()
    for item in request.items:
        normalized = normalize_query_text(item.query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        session.add(
            SeoSkuQuerySetItem(
                query_set_id=int(query_set.id),
                normalized_query_text=normalized,
                display_query=item.query,
                cluster_key=None,
                bucket="primary" if item.selected else "rejected",
                score=Decimal(str(item.confidence if item.confidence is not None else 1 if item.selected else 0)),
                ranking_value_used=Decimal(str(item.frequency)) if item.frequency is not None else None,
                selection_state="auto_selected" if item.selected else "excluded",
                reasons_payload={
                    "source": item.source,
                    "run_id": request.run_id,
                    "meaning_line": item.meaning_line,
                    "risk": item.risk,
                    "user_reasons": [item.explanation] if item.explanation else [],
                    "matched_atoms": [],
                    "missing_atoms": [],
                    "conflict_atoms": [],
                },
            )
        )
    session.flush()
    return get_query_selection(session, project_id=int(project_id), category_id=int(request.category_id), nm_id=int(nm_id))


@router.get(
    "/projects/{project_id}/seo/categories/{category_id}/selected-queries",
    response_model=SeoCategorySelectedQueryListResponse,
)
async def get_seo_category_selected_queries_endpoint(
    project_id: int = Path(...),
    category_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return list_category_selected_queries(session, project_id=int(project_id), category_id=int(category_id))
    finally:
        session.close()


@router.put(
    "/projects/{project_id}/seo/categories/{category_id}/selected-queries",
    response_model=SeoCategorySelectedQueryListResponse,
)
async def put_seo_category_selected_queries_endpoint(
    request: SeoCategorySelectedQuerySaveRequest,
    project_id: int = Path(...),
    category_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = save_category_selected_queries(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            request=request,
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.get("/projects/{project_id}/seo/products", response_model=SeoProductListResponse)
async def get_seo_products_endpoint(
    project_id: int = Path(...),
    category_id: int | None = Query(None),
    q: str | None = Query(None),
    analysis_status: str | None = Query(None),
    stock_status: str | None = Query(None, pattern="^(all|in_stock|out_of_stock)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return list_seo_products(
            session,
            project_id=int(project_id),
            category_id=category_id,
            q=q,
            analysis_status=analysis_status,
            stock_status=stock_status,
            limit=limit,
            offset=offset,
        )
    finally:
        session.close()


@router.get("/projects/{project_id}/seo/products/{nm_id}/seo-summary", response_model=SeoProductSummaryResponse)
async def get_seo_product_summary_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return get_product_seo_summary(session, project_id=int(project_id), nm_id=int(nm_id), category_id=category_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/projects/{project_id}/seo/products/{nm_id}/analysis/run", response_model=SeoProductAnalysisRunResponse)
async def post_seo_product_analysis_run_endpoint(
    request: SeoProductAnalysisRunRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = run_product_analysis(
            session,
            project_id=int(project_id),
            nm_id=int(nm_id),
            category_id=request.category_id,
            force_refresh=bool(request.force_refresh),
            include_vision=bool(request.include_vision),
            selected_image_urls=request.selected_image_urls,
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.get("/projects/{project_id}/seo/products/{nm_id}/analysis/status", response_model=SeoProductAnalysisStatusResponse)
async def get_seo_product_analysis_status_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return get_product_analysis_status(session, project_id=int(project_id), nm_id=int(nm_id), category_id=category_id)
    finally:
        session.close()


@router.get("/projects/{project_id}/seo/products/{nm_id}/readiness", response_model=SeoProductReadinessResponse)
async def get_seo_product_readiness_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return get_product_readiness(session, project_id=int(project_id), nm_id=int(nm_id), category_id=category_id)
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/products/{nm_id}/query-selection/preview",
    response_model=SeoProductionQuerySelectionPreviewResponse,
)
async def get_seo_production_query_selection_preview_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return build_production_query_selection_preview(
            session,
            project_id=int(project_id),
            nm_id=int(nm_id),
            category_id=int(category_id),
        )
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/products/{nm_id}/query-selection/latest-production",
    response_model=SeoProductionQuerySelectionRunResponse | None,
)
async def get_seo_production_query_selection_latest_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        rows = session.scalars(
            select(SeoGenerationRun)
            .where(
                SeoGenerationRun.project_id == int(project_id),
                SeoGenerationRun.category_id == int(category_id),
                SeoGenerationRun.provider_name == "query_selection",
                SeoGenerationRun.status == "completed",
            )
            .order_by(desc(SeoGenerationRun.updated_at), desc(SeoGenerationRun.id))
            .limit(20)
        ).all()
        for row in rows:
            request_payload = row.request_payload if isinstance(row.request_payload, dict) else {}
            if int(request_payload.get("nm_id") or 0) == int(nm_id):
                return _production_query_selection_response_from_run(row)
        return None
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/seo/products/{nm_id}/query-selection/run",
    response_model=SeoProductionQuerySelectionRunResponse,
)
async def post_seo_production_query_selection_run_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = run_production_query_selection(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
        )
        session.commit()
        return response
    except ProductionQuerySelectionError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/projects/{project_id}/seo/products/{nm_id}/query-selection/save-production", response_model=SeoQuerySetResponse)
async def post_seo_production_query_selection_save_endpoint(
    request: SeoProductionQuerySelectionSaveRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = _save_production_query_selection(
            session,
            project_id=int(project_id),
            nm_id=int(nm_id),
            request=request,
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/projects/{project_id}/seo/products/{nm_id}/query-selection/apply-category-list", response_model=SeoQuerySetResponse)
async def post_seo_query_selection_apply_category_list_endpoint(
    request: SeoCategorySelectedQueryApplyRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = apply_category_selected_queries_to_product(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
            query_texts=request.query_texts,
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/projects/{project_id}/seo/products/{nm_id}/query-selection/legacy-run", response_model=SeoQuerySetResponse)
async def post_seo_query_selection_legacy_run_endpoint(
    request: SeoQuerySelectionRunRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = run_query_selection(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
            limit=int(request.limit),
            include_rejected=bool(request.include_rejected),
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        status_code = 409 if "bootstrap" in str(exc).lower() or "library" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    finally:
        session.close()


@router.get("/projects/{project_id}/seo/products/{nm_id}/query-selection", response_model=SeoQuerySetResponse)
async def get_seo_query_selection_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return get_query_selection(session, project_id=int(project_id), category_id=int(category_id), nm_id=int(nm_id))
    finally:
        session.close()


@router.put("/projects/{project_id}/seo/products/{nm_id}/query-selection", response_model=SeoQuerySetResponse)
async def put_seo_query_selection_endpoint(
    request: SeoQuerySelectionUpdateRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = update_query_selection(session, project_id=int(project_id), nm_id=int(nm_id), request=request)
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()
