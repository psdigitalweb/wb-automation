"""Celery execution for an operator-created review-opinion run."""

from __future__ import annotations

from app.celery_app import celery_app
from app.services.review_opinion.service import execute_review_opinion_run


@celery_app.task(name="app.tasks.wb_review_opinion.execute")
def execute_review_opinion_task(run_id: int) -> dict:
    return execute_review_opinion_run(int(run_id))
