"""Internal Query Meaning Library and matcher preview endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.schemas.seo_query_meaning_matcher import (
    MeaningAwareMatcherRequest,
    MeaningAwareMatcherResponse,
    QueryMeaningLibraryBuildRequest,
    QueryMeaningLibraryBuildResponse,
    QueryMeaningLibraryResponse,
)
from app.services.seo.query_meaning_matcher import (
    MissingQueryMeaningLibraryError,
    build_query_meaning_library,
    list_query_meanings,
    run_meaning_aware_matcher,
)
from app.services.seo.query_meaning_matcher.embeddings import MeaningEmbeddingError
from app.services.seo.query_meaning_matcher.matcher import CategoryBootstrapBuildingError, MissingSkuMeaningAnnotationError


router = APIRouter(prefix="/api/v1", tags=["seo-query-meaning-matcher"])


@router.post(
    "/projects/{project_id}/seo/query-meaning-library/build",
    response_model=QueryMeaningLibraryBuildResponse,
)
async def post_query_meaning_library_build_endpoint(
    request: QueryMeaningLibraryBuildRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> QueryMeaningLibraryBuildResponse:
        session = SessionLocal()
        try:
            response = build_query_meaning_library(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
                limit=int(request.limit),
                force_refresh=bool(request.force_refresh),
                use_llm=bool(request.use_llm),
            )
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_run)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/seo/query-meaning-library",
    response_model=QueryMeaningLibraryResponse,
)
async def get_query_meaning_library_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB subject/category ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return list_query_meanings(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            limit=int(limit),
            offset=int(offset),
            status=status,
        )
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/seo/meaning-aware-matcher/preview",
    response_model=MeaningAwareMatcherResponse,
)
async def post_meaning_aware_matcher_preview_endpoint(
    request: MeaningAwareMatcherRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> MeaningAwareMatcherResponse:
        session = SessionLocal()
        try:
            response = run_meaning_aware_matcher(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
                nm_id=int(request.nm_id),
                limit=int(request.limit),
                include_rejected=bool(request.include_rejected),
            )
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_run)
    except MissingQueryMeaningLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CategoryBootstrapBuildingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MissingSkuMeaningAnnotationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MeaningEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
