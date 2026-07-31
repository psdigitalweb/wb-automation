"""Internal SKU Meaning Preview / Annotation Tool endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.db import SessionLocal
from app.db_products import search_project_products_lookup
from app.deps import allow_local_debug_read
from app.schemas.seo_sku_meaning import (
    SkuMeaningAnnotationEnvelope,
    SkuMeaningAnnotationRequest,
    SkuMeaningAnnotationResponse,
    SkuMeaningCandidateQueriesResponse,
    SkuMeaningDraftResponse,
    SkuMeaningEvalExportRequest,
    SkuMeaningEvalExportResponse,
    SkuMeaningEvidencePack,
    SkuQueryJudgmentsRequest,
    SkuQueryJudgmentsResponse,
)
from app.schemas.wildberries_analytics import WBProductLookupItem, WBProductLookupResponse
from app.services.seo.sku_meaning import (
    build_sku_evidence_pack,
    export_eval_dataset,
    generate_sku_meaning_draft,
    get_annotation,
    list_candidate_queries,
    save_annotation,
    save_query_judgments,
)
from app.services.seo.sku_meaning.annotations import SkuMeaningAnnotationNotFoundError
from app.services.seo.sku_meaning.draft import SkuMeaningDraftError
from app.services.seo.sku_meaning.evidence import SkuMeaningProductNotFoundError, SkuMeaningScopeError


router = APIRouter(prefix="/api/v1", tags=["seo-sku-meaning"])


def _actor_from_membership(membership: dict) -> str | None:
    user = membership.get("user") if isinstance(membership, dict) else None
    if isinstance(user, dict):
        username = user.get("username") or user.get("email") or user.get("id")
        return str(username) if username is not None else None
    user_id = membership.get("user_id") if isinstance(membership, dict) else None
    return str(user_id) if user_id is not None else None


def _http_from_evidence_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SkuMeaningProductNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SkuMeaningScopeError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/projects/{project_id}/seo/sku-meaning/products/lookup",
    response_model=WBProductLookupResponse,
)
async def get_sku_meaning_product_lookup_endpoint(
    project_id: int = Path(..., description="Project ID"),
    q: str = Query(..., min_length=1, description="Search by nm_id or vendor_code"),
    limit: int = Query(8, ge=1, le=20),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    items = search_project_products_lookup(project_id=project_id, query=q, limit=limit)
    return WBProductLookupResponse(items=[WBProductLookupItem(**row) for row in items])


@router.get(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/evidence",
    response_model=SkuMeaningEvidencePack,
)
async def get_sku_meaning_evidence_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    category_id: int | None = Query(None, description="WB subject_id/category scope"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    except Exception as exc:
        raise _http_from_evidence_error(exc) from exc
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/draft",
    response_model=SkuMeaningDraftResponse,
)
async def post_sku_meaning_draft_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    category_id: int | None = Query(None, description="WB subject_id/category scope"),
    force_refresh: bool = Query(False),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        evidence_pack = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
        return generate_sku_meaning_draft(evidence_pack, force_refresh=force_refresh)
    except SkuMeaningDraftError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise _http_from_evidence_error(exc) from exc
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/annotation",
    response_model=SkuMeaningAnnotationEnvelope,
)
async def get_sku_meaning_annotation_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    category_id: int | None = Query(None, description="WB subject_id/category scope"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        annotation = get_annotation(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
        return SkuMeaningAnnotationEnvelope(annotation=annotation)
    finally:
        session.close()


@router.put(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/annotation",
    response_model=SkuMeaningAnnotationResponse,
)
async def put_sku_meaning_annotation_endpoint(
    request: SkuMeaningAnnotationRequest,
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    membership: dict = Depends(allow_local_debug_read),
):
    session = SessionLocal()
    try:
        if request.category_id is not None:
            category_id = int(request.category_id)
        else:
            evidence_pack = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=None)
            category_id = int(evidence_pack.category_id)
        response = save_annotation(
            session,
            project_id=project_id,
            nm_id=nm_id,
            category_id=category_id,
            request=request,
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise _http_from_evidence_error(exc) from exc
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/candidate-queries",
    response_model=SkuMeaningCandidateQueriesResponse,
)
async def get_sku_meaning_candidate_queries_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    category_id: int | None = Query(None, description="WB subject_id/category scope"),
    limit: int = Query(100, ge=1, le=300),
    search: str | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        if category_id is None:
            evidence_pack = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=None)
            category_id = int(evidence_pack.category_id)
        items = list_candidate_queries(
            session,
            project_id=project_id,
            category_id=int(category_id),
            nm_id=nm_id,
            limit=limit,
            search=search,
        )
        return SkuMeaningCandidateQueriesResponse(
            project_id=project_id,
            category_id=int(category_id),
            nm_id=nm_id,
            items=items,
        )
    except Exception as exc:
        raise _http_from_evidence_error(exc) from exc
    finally:
        session.close()


@router.put(
    "/projects/{project_id}/seo/sku-meaning/{nm_id}/query-judgments",
    response_model=SkuQueryJudgmentsResponse,
)
async def put_sku_meaning_query_judgments_endpoint(
    request: SkuQueryJudgmentsRequest,
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nm_id"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        items = save_query_judgments(
            session,
            project_id=project_id,
            nm_id=nm_id,
            category_id=request.category_id,
            annotation_id=request.annotation_id,
            items=request.items,
        )
        session.commit()
        return SkuQueryJudgmentsResponse(items=items)
    except SkuMeaningAnnotationNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        session.rollback()
        raise _http_from_evidence_error(exc) from exc
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/seo/eval-datasets/export",
    response_model=SkuMeaningEvalExportResponse,
)
async def post_sku_meaning_eval_export_endpoint(
    request: SkuMeaningEvalExportRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    session = SessionLocal()
    try:
        response = export_eval_dataset(
            session,
            project_id=project_id,
            request=request,
            actor=_actor_from_membership(membership),
        )
        session.commit()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        session.close()
