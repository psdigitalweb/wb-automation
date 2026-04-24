"""Product-facing SEO module endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.schemas.seo_products import (
    SeoProductAnalysisRunRequest,
    SeoProductAnalysisRunResponse,
    SeoProductAnalysisStatusResponse,
    SeoProductListResponse,
    SeoProductSummaryResponse,
    SeoQuerySelectionRunRequest,
    SeoQuerySelectionUpdateRequest,
    SeoQuerySetResponse,
)
from app.services.seo.products import (
    get_product_analysis_status,
    get_product_seo_summary,
    get_query_selection,
    list_seo_products,
    run_product_analysis,
    run_query_selection,
    update_query_selection,
)


router = APIRouter(prefix="/api/v1", tags=["seo-products"])


@router.get("/projects/{project_id}/seo/products", response_model=SeoProductListResponse)
async def get_seo_products_endpoint(
    project_id: int = Path(...),
    category_id: int | None = Query(None),
    q: str | None = Query(None),
    analysis_status: str | None = Query(None),
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


@router.post("/projects/{project_id}/seo/products/{nm_id}/query-selection/run", response_model=SeoQuerySetResponse)
async def post_seo_query_selection_run_endpoint(
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
