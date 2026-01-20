"""Celery tasks for WB finances ingestion (project-level)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.wb_finances.ingest_wb_finance_reports_by_period")
def ingest_wb_finance_reports_by_period_task(
    project_id: int,
    date_from: str,
    date_to: str,
) -> Dict[str, Any]:
    """Celery task wrapper for WB finance reports ingestion.
    
    Args:
        project_id: Project ID
        date_from: Start date in format YYYY-MM-DD
        date_to: End date in format YYYY-MM-DD
        
    Returns:
        Dict with status and result summary
    """
    from datetime import date as _date
    from app.ingest_wb_finances import ingest_wb_finance_reports_by_period

    date_from_obj = _date.fromisoformat(date_from)
    date_to_obj = _date.fromisoformat(date_to)
    
    result = asyncio.run(
        ingest_wb_finance_reports_by_period(
            project_id=project_id,
            date_from=date_from_obj,
            date_to=date_to_obj,
        )
    )
    
    print(
        f"ingest_wb_finance_reports_by_period_task: completed "
        f"project_id={project_id} date_from={date_from} date_to={date_to} "
        f"result={result}"
    )
    
    return {
        "status": "completed",
        "domain": "wb_finance_reports",
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
        "result": result,
    }
