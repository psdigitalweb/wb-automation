"""Candidate matcher (matcher_v2) endpoints — iteration 1 additive path.

Two endpoints:

- ``POST /api/v1/projects/{project_id}/seo/matcher/v2/run`` — runs the
  candidate matcher for a SKU, persists a replayable trace, and returns the
  same shape the current preview endpoint returns plus ``run_id`` and
  ``quality_mode``.
- ``GET /api/v1/projects/{project_id}/seo/matcher/v2/runs/{run_id}`` —
  returns the persisted trace for a run (header row + per-query result rows)
  so the P1 matcher-run viewer and future compare layers can replay
  decisions.

The endpoints are additive. The existing
``/meaning-aware-matcher/preview`` endpoint keeps calling the current
matcher unchanged. See
``docs/seo-module/implementation-plan/05_backend_contract_changes.md``
sections 2-3.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoMatcherResult, SeoMatcherRun
from app.schemas.seo_matcher_v2 import (
    MatcherV2ResultItem,
    MatcherV2RunDetailResponse,
    MatcherV2RunRequest,
    MatcherV2RunResponse,
)
from app.services.seo.matcher_v2 import run_matcher_v2
from app.services.seo.category_profile import ProfileMissingError
from app.services.seo.query_meaning_matcher.embeddings import MeaningEmbeddingError
from app.services.seo.query_meaning_matcher.matcher import (
    CategoryBootstrapBuildingError,
    MissingQueryMeaningLibraryError,
    MissingSkuMeaningAnnotationError,
)


router = APIRouter(prefix="/api/v1", tags=["seo-matcher-v2"])


@router.post(
    "/projects/{project_id}/seo/matcher/v2/run",
    response_model=MatcherV2RunResponse,
)
async def post_matcher_v2_run_endpoint(
    request: MatcherV2RunRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> MatcherV2RunResponse:
        session = SessionLocal()
        try:
            bundle = run_matcher_v2(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
                nm_id=int(request.nm_id),
                limit=int(request.limit),
                include_rejected=bool(request.include_rejected),
            )
            run = bundle.run_row
            session.commit()
            return MatcherV2RunResponse(
                run_id=int(run.id),
                quality_mode=str(run.quality_mode or "full"),
                degraded_reasons=list(run.degraded_reasons or []),
                response=bundle.response,
            )
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
    except ProfileMissingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MeaningEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/seo/matcher/v2/runs/{run_id}",
    response_model=MatcherV2RunDetailResponse,
)
async def get_matcher_v2_run_endpoint(
    project_id: int = Path(..., description="Project ID"),
    run_id: int = Path(..., description="Matcher run ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> MatcherV2RunDetailResponse:
        session = SessionLocal()
        try:
            run = session.get(SeoMatcherRun, int(run_id))
            if run is None or int(run.project_id) != int(project_id):
                raise HTTPException(status_code=404, detail=f"matcher run {run_id} not found")

            result_rows = session.scalars(
                select(SeoMatcherResult)
                .where(SeoMatcherResult.run_id == int(run.id))
                .order_by(SeoMatcherResult.score.desc(), SeoMatcherResult.id.asc())
            ).all()
            items = [
                MatcherV2ResultItem(
                    id=int(row.id),
                    query_meaning_id=int(row.query_meaning_id) if row.query_meaning_id is not None else None,
                    cluster_key=row.cluster_key,
                    query_display=str(row.query_display),
                    normalized_query_text=str(row.normalized_query_text),
                    bucket=str(row.bucket),
                    eligibility_verdict=str(row.eligibility_verdict),
                    score=float(row.score),
                    score_components=dict(row.score_components or {}),
                    matched_atoms=list(row.matched_atoms or []),
                    missing_atoms=list(row.missing_atoms or []),
                    conflict_atoms=list(row.conflict_atoms or []),
                    reasons=list(row.reasons or []),
                    ranking_value_used=(
                        float(row.ranking_value_used) if row.ranking_value_used is not None else None
                    ),
                    semantic_similarity=(
                        float(row.semantic_similarity) if row.semantic_similarity is not None else None
                    ),
                    created_at=row.created_at,
                )
                for row in result_rows
            ]
            return MatcherV2RunDetailResponse(
                run_id=int(run.id),
                project_id=int(run.project_id),
                category_id=int(run.category_id),
                nm_id=int(run.nm_id),
                matcher_version=str(run.matcher_version),
                policy_version=str(run.policy_version),
                category_profile_version=str(run.category_profile_version),
                sku_atoms_id=int(run.sku_atoms_id) if run.sku_atoms_id is not None else None,
                vision_atoms_id=int(run.vision_atoms_id) if run.vision_atoms_id is not None else None,
                query_atoms_version=run.query_atoms_version,
                embedding_model=run.embedding_model,
                readiness_snapshot=dict(run.readiness_snapshot or {}),
                quality_mode=str(run.quality_mode) if run.quality_mode else None,
                degraded_reasons=list(run.degraded_reasons or []),
                metrics=dict(run.metrics or {}),
                error=dict(run.error) if run.error else None,
                started_at=run.started_at,
                completed_at=run.completed_at,
                results=items,
            )
        finally:
            session.close()

    return await run_in_threadpool(_fetch)
