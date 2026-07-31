"""Candidate-path query-set endpoints (Iteration 2, WS-C).

The candidate path projects ``SeoMatcherRun`` / ``SeoMatcherResult`` trace
rows into a dedicated ``SeoSkuQuerySet`` (``status='candidate'``). UI reads
the projected query set; the trace remains immutable.

Endpoints:

* ``POST /api/v1/projects/{project_id}/seo/query-sets/candidate/project`` —
  project the latest (or an explicit) matcher_v2 run into the candidate
  query set.
* ``POST /api/v1/projects/{project_id}/seo/query-sets/candidate/{query_set_id}/approval`` —
  apply a whitelisted approval-state transition (``draft -> preview ->
  candidate -> approved``).

The legacy ``draft`` / ``confirmed`` query-set endpoints in
``seo_products.py`` stay untouched (D2: legacy ``status == 'confirmed'``
must keep working this iteration).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoSkuQuerySet
from app.services.seo.query_set_candidate import (
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_CANDIDATE,
    APPROVAL_STATE_DRAFT,
    APPROVAL_STATE_PREVIEW,
    CandidateQuerySetError,
    project_matcher_run_into_query_set,
    transition_approval_state,
)


router = APIRouter(prefix="/api/v1", tags=["seo-query-set-candidate"])


_APPROVAL_STATES = {
    APPROVAL_STATE_DRAFT,
    APPROVAL_STATE_PREVIEW,
    APPROVAL_STATE_CANDIDATE,
    APPROVAL_STATE_APPROVED,
}


class CandidateProjectRequest(BaseModel):
    category_id: int
    nm_id: int
    matcher_run_id: Optional[int] = Field(
        default=None,
        description="If set, project a specific matcher run. Otherwise the "
        "latest run for the SKU is used.",
    )


class CandidateProjectResponse(BaseModel):
    query_set_id: int
    matcher_run_id: int
    items_written: int
    approval_state: str
    trust_state: str
    category_profile_version: Optional[str]


class CandidateApprovalRequest(BaseModel):
    approval_state: str = Field(..., description="Target state; one of draft|preview|candidate|approved")
    operator_override: bool = Field(default=False)
    has_accepted_human_review: bool = Field(default=False)


class CandidateQuerySetResponse(BaseModel):
    query_set_id: int
    project_id: int
    category_id: int
    nm_id: int
    approval_state: str
    trust_state: str
    category_profile_version: Optional[str]


@router.post(
    "/projects/{project_id}/seo/query-sets/candidate/project",
    response_model=CandidateProjectResponse,
)
async def post_project_candidate_endpoint(
    request: CandidateProjectRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> CandidateProjectResponse:
        session = SessionLocal()
        try:
            result = project_matcher_run_into_query_set(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
                nm_id=int(request.nm_id),
                matcher_run_id=request.matcher_run_id,
            )
            session.commit()
            return CandidateProjectResponse(
                query_set_id=result.query_set_id,
                matcher_run_id=result.matcher_run_id,
                items_written=result.items_written,
                approval_state=result.approval_state,
                trust_state=result.trust_state,
                category_profile_version=result.category_profile_version,
            )
        except CandidateQuerySetError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(_run)


@router.post(
    "/projects/{project_id}/seo/query-sets/candidate/{query_set_id}/approval",
    response_model=CandidateQuerySetResponse,
)
async def post_candidate_approval_endpoint(
    request: CandidateApprovalRequest,
    project_id: int = Path(..., description="Project ID"),
    query_set_id: int = Path(..., description="Candidate query-set ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    if request.approval_state not in _APPROVAL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"approval_state must be one of {sorted(_APPROVAL_STATES)}",
        )

    def _run() -> CandidateQuerySetResponse:
        session = SessionLocal()
        try:
            row = session.get(SeoSkuQuerySet, int(query_set_id))
            if row is None or int(row.project_id) != int(project_id):
                raise HTTPException(status_code=404, detail="candidate query set not found")
            if str(row.status) != "candidate":
                raise HTTPException(
                    status_code=409,
                    detail="approval transitions apply only to candidate query sets",
                )
            updated = transition_approval_state(
                session,
                query_set_id=int(query_set_id),
                new_state=request.approval_state,
                operator_override=bool(request.operator_override),
                has_accepted_human_review=bool(request.has_accepted_human_review),
            )
            session.commit()
            return CandidateQuerySetResponse(
                query_set_id=int(updated.id),
                project_id=int(updated.project_id),
                category_id=int(updated.category_id),
                nm_id=int(updated.nm_id),
                approval_state=str(updated.approval_state),
                trust_state=str(updated.trust_state),
                category_profile_version=getattr(updated, "category_profile_version", None),
            )
        except CandidateQuerySetError as exc:
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
