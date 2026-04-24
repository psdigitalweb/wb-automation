"""SEO text generation endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import settings as app_settings
from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoContentVersion
from app.schemas.seo_generation import (
    SeoGenerationLatestResponse,
    SeoGenerationRunRequest,
    SeoGenerationRunResponse,
)
from app.services.seo.generation.promotion import (
    GenerationPromotionError,
    promote_content_version,
    record_human_review,
)
from app.services.seo.generation.service import (
    SeoGenerationError,
    get_latest_generation,
    recalculate_latest_seo_relevance_v2,
    run_seo_generation,
)


router = APIRouter(prefix="/api/v1", tags=["seo-generation"])


class SeoFeatureFlags(BaseModel):
    """Iteration 1: runtime-visible SEO feature flags.

    The frontend reads this to decide whether to:
      * show the "Run generation" button (vs. a "coming soon" stub)
      * always display the "Research preview" banner

    Today the button is gated purely on ``generation_preview_enabled``;
    additional gates (category tier, selection_state) ship in iteration 2.
    """

    generation_preview_enabled: bool
    generation_max_attempts: int
    generation_publishable: bool = False


@router.get(
    "/seo/feature-flags",
    response_model=SeoFeatureFlags,
)
async def get_seo_feature_flags_endpoint(
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    return SeoFeatureFlags(
        generation_preview_enabled=bool(
            getattr(app_settings, "SEO_GENERATION_PREVIEW_ENABLED", False)
        ),
        generation_max_attempts=int(getattr(app_settings, "SEO_GENERATION_MAX_ATTEMPTS", 1)),
        generation_publishable=False,
    )


@router.post(
    "/projects/{project_id}/seo/products/{nm_id}/generation/run",
    response_model=SeoGenerationRunResponse,
)
async def post_seo_generation_run_endpoint(
    request: SeoGenerationRunRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    if not bool(getattr(app_settings, "SEO_GENERATION_PREVIEW_ENABLED", False)):
        raise HTTPException(
            status_code=503,
            detail=(
                "SEO generation is disabled. Set SEO_GENERATION_PREVIEW_ENABLED=true "
                "to enable the research-preview endpoint."
            ),
        )
    session = SessionLocal()
    try:
        response = run_seo_generation(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
            query_set_id=request.query_set_id,
            main_query_text=request.main_query_text,
            brand_voice=request.brand_voice,
            allow_draft_query_set=bool(request.allow_draft_query_set),
        )
        session.commit()
        return response
    except SeoGenerationError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/products/{nm_id}/generation/latest",
    response_model=SeoGenerationLatestResponse,
)
async def get_seo_generation_latest_endpoint(
    project_id: int = Path(...),
    nm_id: int = Path(...),
    category_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        return get_latest_generation(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
        )
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/seo/products/{nm_id}/generation/recalculate-seo-v2",
    response_model=SeoGenerationLatestResponse,
)
async def post_seo_generation_recalculate_seo_v2_endpoint(
    request: SeoGenerationRunRequest,
    project_id: int = Path(...),
    nm_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        recalculate_latest_seo_relevance_v2(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
        )
        session.commit()
        return get_latest_generation(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            nm_id=int(nm_id),
        )
    except SeoGenerationError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Iteration 2 (WS-D): lifecycle promotion + human review
# ---------------------------------------------------------------------------


class SeoGenerationPromoteRequest(BaseModel):
    target_kind: str = Field(
        ...,
        description="Target content_kind. One of 'candidate' | 'approved'. "
        "'published' is refused in Iteration 2.",
    )


class SeoGenerationPromoteResponse(BaseModel):
    content_version_id: int
    previous_content_kind: str
    new_content_kind: str
    eligibility_tier: str
    human_review_id: Optional[int]


class SeoGenerationHumanReviewRequest(BaseModel):
    verdict: str = Field(..., description="One of accept | reject | needs_changes")
    reviewer: Optional[str] = Field(default=None, max_length=128)
    rubric: Optional[dict] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=4000)


class SeoGenerationHumanReviewResponse(BaseModel):
    id: int
    content_version_id: int
    reviewer: Optional[str]
    verdict: str


@router.post(
    "/projects/{project_id}/seo/generation/content/{content_version_id}/promote",
    response_model=SeoGenerationPromoteResponse,
)
async def post_seo_generation_promote_endpoint(
    request: SeoGenerationPromoteRequest,
    project_id: int = Path(...),
    content_version_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> SeoGenerationPromoteResponse:
        session = SessionLocal()
        try:
            content = session.get(SeoContentVersion, int(content_version_id))
            if content is None or int(content.project_id) != int(project_id):
                raise HTTPException(status_code=404, detail="content version not found")
            result = promote_content_version(
                session,
                content_version_id=int(content_version_id),
                target_kind=request.target_kind,
            )
            session.commit()
            return SeoGenerationPromoteResponse(
                content_version_id=result.content_version_id,
                previous_content_kind=result.previous_content_kind,
                new_content_kind=result.new_content_kind,
                eligibility_tier=result.eligibility_tier,
                human_review_id=result.human_review_id,
            )
        except GenerationPromotionError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(_run)


@router.post(
    "/projects/{project_id}/seo/generation/content/{content_version_id}/human-review",
    response_model=SeoGenerationHumanReviewResponse,
)
async def post_seo_generation_human_review_endpoint(
    request: SeoGenerationHumanReviewRequest,
    project_id: int = Path(...),
    content_version_id: int = Path(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> SeoGenerationHumanReviewResponse:
        session = SessionLocal()
        try:
            content = session.get(SeoContentVersion, int(content_version_id))
            if content is None or int(content.project_id) != int(project_id):
                raise HTTPException(status_code=404, detail="content version not found")
            row = record_human_review(
                session,
                content_version_id=int(content_version_id),
                reviewer=request.reviewer,
                verdict=request.verdict,
                rubric=request.rubric,
                notes=request.notes,
            )
            session.commit()
            return SeoGenerationHumanReviewResponse(
                id=int(row.id),
                content_version_id=int(row.content_version_id),
                reviewer=row.reviewer,
                verdict=str(row.verdict),
            )
        except GenerationPromotionError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(_run)
