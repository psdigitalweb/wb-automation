"""Celery task created only by a manual competitor-review API command."""

from __future__ import annotations

from app.celery_app import celery_app
from app.services.competitor_analysis.service import execute_competitor_analysis
from app.services.wb_competitor_reviews import collect_competitor_review_run
from app.utils.asyncio_runner import run_async_safe


@celery_app.task(name="app.tasks.wb_competitor_reviews.collect")
def collect_competitor_reviews_task(run_id: int) -> dict:
    return run_async_safe(
        collect_competitor_review_run(int(run_id)),
        context_info={"run_id": int(run_id), "job_code": "wb_competitor_reviews"},
        force_thread=True,
    )


@celery_app.task(name="app.tasks.wb_competitor_reviews.analyze")
def analyze_competitor_reviews_task(run_id: int) -> dict:
    return execute_competitor_analysis(int(run_id))
