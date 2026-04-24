"""SEO eval endpoints — Iteration 2 (WS-E).

Exposes the matcher eval harness to the operator UI and CLI:

* ``POST /api/v1/projects/{project_id}/seo/eval/matcher/run`` — trigger an
  eval computation. Body accepts ``category_id``, optional ``nm_ids``, and
  optional ``label_set_id`` (defaults to 1).
* ``GET /api/v1/projects/{project_id}/seo/eval/runs?category_id=...`` —
  paginated history of eval runs for a category (operator UI: eval page for
  812).
* ``GET /api/v1/projects/{project_id}/seo/eval/labels/stats?category_id=...``
  — summary of label-set coverage (labels per bucket, labels per SKU).

The router is the only caller of ``app.services.seo.eval.harness.run_matcher_eval``
that is exposed to the frontend. The harness, in turn, is the single writer
of ``SeoCategoryMatchingReadiness.eligibility_tier`` (enforced by
``tests/seo/test_seo_eval_harness.py``).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoCategoryMatchingReadiness, SeoEvalLabel, SeoEvalRun
from app.services.seo.eval import EvalHarnessError, run_matcher_eval


router = APIRouter(prefix="/api/v1", tags=["seo-eval"])


class SeoEvalRunRequest(BaseModel):
    """Request body for ``POST /seo/eval/matcher/run``."""

    category_id: int = Field(..., description="WB category scope.")
    nm_ids: Optional[list[int]] = Field(
        None,
        description="Optional SKU-scoped eval. When omitted, the harness uses "
        "whatever matcher runs are already persisted for the category.",
    )
    matcher_run_ids: Optional[list[int]] = Field(
        None,
        description="Optional explicit matcher-run IDs (replay mode).",
    )
    label_set_id: int = Field(default=1, description="Label-set identifier; defaults to 1.")
    notes: Optional[str] = Field(default=None, max_length=2000)


class SeoEvalRunResponse(BaseModel):
    eval_run_id: int
    project_id: int
    category_id: int
    label_set_id: int
    verdict: str
    metrics: dict[str, Any]
    thresholds: dict[str, float]
    matcher_run_ids: list[int]
    nm_ids: list[int]
    labels_used: int
    labels_missing: int
    eligibility_tier_after: str


class SeoEvalRunListItem(BaseModel):
    eval_run_id: int
    category_id: int
    label_set_id: int
    verdict: str
    metrics: dict[str, Any]
    thresholds: dict[str, float]
    matcher_run_ids: list[int]
    nm_ids: list[int]
    notes: Optional[str]
    created_by: Optional[str]
    created_at: str


class SeoEvalRunListResponse(BaseModel):
    items: list[SeoEvalRunListItem]
    eligibility_tier: str


class SeoEvalLabelStatsResponse(BaseModel):
    category_id: int
    label_set_id: int
    total_labels: int
    by_bucket: dict[str, int]
    by_nm_id: dict[str, int]


def _readiness_tier(session: Session, *, project_id: int, category_id: int) -> str:
    row = session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()
    if row is None:
        return "preview_only"
    return str(row.eligibility_tier or "preview_only")


@router.post(
    "/projects/{project_id}/seo/eval/matcher/run",
    response_model=SeoEvalRunResponse,
)
async def post_seo_eval_matcher_run_endpoint(
    request: SeoEvalRunRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> SeoEvalRunResponse:
        session = SessionLocal()
        try:
            result = run_matcher_eval(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
                label_set_id=int(request.label_set_id),
                nm_ids=list(request.nm_ids or []) or None,
                matcher_run_ids=list(request.matcher_run_ids or []) or None,
                notes=request.notes,
            )
            tier = _readiness_tier(
                session,
                project_id=int(project_id),
                category_id=int(request.category_id),
            )
            session.commit()
            return SeoEvalRunResponse(
                eval_run_id=result.run_id,
                project_id=int(project_id),
                category_id=int(request.category_id),
                label_set_id=int(request.label_set_id),
                verdict=result.verdict,
                metrics=result.metrics,
                thresholds=result.thresholds,
                matcher_run_ids=result.matcher_run_ids,
                nm_ids=result.nm_ids,
                labels_used=result.labels_used,
                labels_missing=result.labels_missing,
                eligibility_tier_after=tier,
            )
        except EvalHarnessError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return await run_in_threadpool(_run)


@router.get(
    "/projects/{project_id}/seo/eval/runs",
    response_model=SeoEvalRunListResponse,
)
async def get_seo_eval_runs_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category scope"),
    limit: int = Query(default=50, ge=1, le=200),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> SeoEvalRunListResponse:
        session = SessionLocal()
        try:
            rows = session.scalars(
                select(SeoEvalRun)
                .where(
                    SeoEvalRun.project_id == int(project_id),
                    SeoEvalRun.category_id == int(category_id),
                )
                .order_by(desc(SeoEvalRun.created_at), desc(SeoEvalRun.id))
                .limit(int(limit))
            ).all()
            items = [
                SeoEvalRunListItem(
                    eval_run_id=int(row.id),
                    category_id=int(row.category_id),
                    label_set_id=int(row.label_set_id),
                    verdict=str(row.verdict),
                    metrics=dict(row.metrics or {}),
                    thresholds=dict(row.thresholds or {}),
                    matcher_run_ids=list(row.matcher_run_ids or []),
                    nm_ids=list(row.nm_ids or []),
                    notes=row.notes,
                    created_by=row.created_by,
                    created_at=row.created_at.isoformat() if row.created_at else "",
                )
                for row in rows
            ]
            tier = _readiness_tier(
                session, project_id=int(project_id), category_id=int(category_id)
            )
            return SeoEvalRunListResponse(items=items, eligibility_tier=tier)
        finally:
            session.close()

    return await run_in_threadpool(_fetch)


@router.get(
    "/projects/{project_id}/seo/eval/labels/stats",
    response_model=SeoEvalLabelStatsResponse,
)
async def get_seo_eval_label_stats_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category scope"),
    label_set_id: int = Query(default=1, description="Label-set identifier"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> SeoEvalLabelStatsResponse:
        session = SessionLocal()
        try:
            rows = session.scalars(
                select(SeoEvalLabel).where(
                    SeoEvalLabel.project_id == int(project_id),
                    SeoEvalLabel.category_id == int(category_id),
                    SeoEvalLabel.label_set_id == int(label_set_id),
                )
            ).all()
            by_bucket: dict[str, int] = {}
            by_nm: dict[str, int] = {}
            for row in rows:
                bucket = str(row.expected_bucket or "")
                by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
                nm_id = str(row.nm_id) if row.nm_id is not None else "global"
                by_nm[nm_id] = by_nm.get(nm_id, 0) + 1
            return SeoEvalLabelStatsResponse(
                category_id=int(category_id),
                label_set_id=int(label_set_id),
                total_labels=len(rows),
                by_bucket=by_bucket,
                by_nm_id=by_nm,
            )
        finally:
            session.close()

    return await run_in_threadpool(_fetch)
