"""Celery task for building WB financial events."""

from __future__ import annotations

from typing import Any, Dict

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.wb_financial_events.build_wb_financial_events_task")
def build_wb_financial_events_task(
    project_id: int,
    date_from: str,
    date_to: str,
) -> Dict[str, Any]:
    """Build wb_financial_events from raw lines for given period."""
    from datetime import date as _date

    from app.services.wb_financial.builder import build_wb_financial_events

    date_from_obj = _date.fromisoformat(date_from)
    date_to_obj = _date.fromisoformat(date_to)

    stats = build_wb_financial_events(
        project_id=project_id,
        date_from=date_from_obj,
        date_to=date_to_obj,
    )

    print(
        f"build_wb_financial_events_task: completed "
        f"project_id={project_id} date_from={date_from} date_to={date_to} "
        f"inserted={stats.get('inserted')} deleted={stats.get('deleted')} "
        f"unmapped_count={stats.get('unmapped_count')}"
    )

    return {
        "status": "completed",
        "domain": "wb_financial_events",
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
        "stats": stats,
    }
