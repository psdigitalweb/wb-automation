"""Matcher-run retention admin endpoint (Iteration 2, WS-G).

Exposes the retention helper through an admin-only POST so operators can
trigger cleanup without opening a shell. The same helper is also callable
from the CLI via ``scripts/run_seo_matcher_retention.py``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.services.seo.matcher_retention import (
    KEEP_NEWEST_PER_SKU,
    KEEP_WINDOW_DAYS,
    cleanup_matcher_runs,
)


router = APIRouter(prefix="/api/v1", tags=["seo-retention"])


class MatcherRetentionResponse(BaseModel):
    scanned_runs: int
    kept_by_recency_count: int
    kept_by_reference_count: int
    deleted_run_ids: list[int]
    deleted_result_rows: int
    dry_run: bool
    keep_newest: int
    keep_days: int


@router.post(
    "/seo/matcher/retention/cleanup",
    response_model=MatcherRetentionResponse,
)
async def post_seo_matcher_retention_cleanup_endpoint(
    dry_run: bool = Query(default=False),
    keep_newest: int = Query(default=KEEP_NEWEST_PER_SKU, ge=1, le=500),
    keep_days: int = Query(default=KEEP_WINDOW_DAYS, ge=1, le=365),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _run() -> MatcherRetentionResponse:
        session = SessionLocal()
        try:
            report = cleanup_matcher_runs(
                session,
                dry_run=bool(dry_run),
                keep_newest=int(keep_newest),
                keep_days=int(keep_days),
            )
            if not dry_run:
                session.commit()
            else:
                session.rollback()
            return MatcherRetentionResponse(
                scanned_runs=report.scanned_runs,
                kept_by_recency_count=report.kept_by_recency_count,
                kept_by_reference_count=report.kept_by_reference_count,
                deleted_run_ids=list(report.deleted_run_ids),
                deleted_result_rows=report.deleted_result_rows,
                dry_run=report.dry_run,
                keep_newest=int(keep_newest),
                keep_days=int(keep_days),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
