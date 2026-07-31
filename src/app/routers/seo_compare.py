"""Read-only compare layer endpoints (Iteration 2, compare).

Surfaces:

* ``GET /api/v1/projects/{project_id}/seo/compare/matcher?category_id&nm_id``
  — diff the legacy persisted query-set against the candidate matcher_v2 trace.
* ``GET /api/v1/projects/{project_id}/seo/compare/generation?category_id&nm_id``
  — groups the SKU's ``SeoContentVersion`` rows by ``content_kind``.
* ``POST /api/v1/projects/{project_id}/seo/compare/{subject_type}/verdict``
  — writes only to ``seo_compare_verdicts`` (append-only review artifact).

**Contract (see
``docs/seo-module/implementation-plan/05_backend_contract_changes.md``):**
This router is forbidden from calling any mutating matcher / generation /
eval service function. The static check in
``tests/seo/test_seo_compare_read_only.py`` asserts the import allowlist.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoCompareVerdict
from app.services.seo.compare import (
    GenerationCompareResult,
    MatcherCompareResult,
    compare_generation,
    compare_matcher,
)


router = APIRouter(prefix="/api/v1", tags=["seo-compare"])


ALLOWED_SUBJECT_TYPES = {"matcher", "generation"}
ALLOWED_VERDICTS = {"accept", "reject", "needs_changes"}


class MatcherCompareResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    current: dict[str, Any]
    candidate: dict[str, Any]
    diff: dict[str, Any]


class GenerationCompareResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    by_kind: dict[str, list[dict[str, Any]]]
    latest_preview_id: Optional[int]
    latest_candidate_id: Optional[int]
    latest_approved_id: Optional[int]


class CompareVerdictRequest(BaseModel):
    subject_id: int = Field(..., description="Primary subject id (matcher_run_id or content_version_id)")
    related_id: Optional[int] = Field(default=None)
    verdict: str = Field(..., description="One of accept | reject | needs_changes")
    notes: Optional[str] = Field(default=None, max_length=4000)
    created_by: Optional[str] = Field(default=None, max_length=128)


class CompareVerdictResponse(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    related_id: Optional[int]
    verdict: str


@router.get(
    "/projects/{project_id}/seo/compare/matcher",
    response_model=MatcherCompareResponse,
)
async def get_compare_matcher_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(...),
    nm_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> MatcherCompareResponse:
        session = SessionLocal()
        try:
            result: MatcherCompareResult = compare_matcher(
                session,
                project_id=int(project_id),
                category_id=int(category_id),
                nm_id=int(nm_id),
            )
            return MatcherCompareResponse(
                project_id=int(project_id),
                category_id=int(category_id),
                nm_id=int(nm_id),
                current=dict(result.current),
                candidate=dict(result.candidate),
                diff=dict(result.diff),
            )
        finally:
            session.close()

    return await run_in_threadpool(_fetch)


@router.get(
    "/projects/{project_id}/seo/compare/generation",
    response_model=GenerationCompareResponse,
)
async def get_compare_generation_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(...),
    nm_id: int = Query(...),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> GenerationCompareResponse:
        session = SessionLocal()
        try:
            result: GenerationCompareResult = compare_generation(
                session,
                project_id=int(project_id),
                category_id=int(category_id),
                nm_id=int(nm_id),
            )
            return GenerationCompareResponse(
                project_id=int(project_id),
                category_id=int(category_id),
                nm_id=int(nm_id),
                by_kind=dict(result.by_kind),
                latest_preview_id=result.latest_preview_id,
                latest_candidate_id=result.latest_candidate_id,
                latest_approved_id=result.latest_approved_id,
            )
        finally:
            session.close()

    return await run_in_threadpool(_fetch)


@router.post(
    "/projects/{project_id}/seo/compare/{subject_type}/verdict",
    response_model=CompareVerdictResponse,
)
async def post_compare_verdict_endpoint(
    request: CompareVerdictRequest,
    project_id: int = Path(..., description="Project ID"),
    subject_type: str = Path(..., description="'matcher' or 'generation'"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    if subject_type not in ALLOWED_SUBJECT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"subject_type must be one of {sorted(ALLOWED_SUBJECT_TYPES)}",
        )
    verdict_norm = str(request.verdict or "").strip().lower()
    if verdict_norm not in ALLOWED_VERDICTS:
        raise HTTPException(
            status_code=400,
            detail=f"verdict must be one of {sorted(ALLOWED_VERDICTS)}",
        )

    def _run() -> CompareVerdictResponse:
        session = SessionLocal()
        try:
            row = SeoCompareVerdict(
                project_id=int(project_id),
                subject_type=subject_type,
                subject_id=int(request.subject_id),
                related_id=int(request.related_id) if request.related_id is not None else None,
                verdict=verdict_norm,
                notes=request.notes,
                created_by=request.created_by,
            )
            session.add(row)
            session.flush()
            session.commit()
            return CompareVerdictResponse(
                id=int(row.id),
                subject_type=str(row.subject_type),
                subject_id=int(row.subject_id),
                related_id=row.related_id,
                verdict=str(row.verdict),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(_run)
