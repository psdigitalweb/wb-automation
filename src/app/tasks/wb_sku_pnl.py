"""Celery task for building WB SKU PnL snapshot."""

from __future__ import annotations

from typing import Any, Dict

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.wb_sku_pnl.build_wb_sku_pnl_snapshot_task")
def build_wb_sku_pnl_snapshot_task(
    project_id: int,
    period_from: str,
    period_to: str,
    version: int = 1,
    rebuild: bool = True,
    ensure_events: bool = True,
) -> Dict[str, Any]:
    """Build WB SKU PnL snapshot for period."""
    from datetime import date as _date

    from app.services.wb_financial.sku_pnl_builder import build_wb_sku_pnl_snapshot
    from app.services.wb_financial.builder import build_wb_financial_events

    period_from_obj = _date.fromisoformat(period_from)
    period_to_obj = _date.fromisoformat(period_to)

    events_stats = None
    if ensure_events:
        events_stats = build_wb_financial_events(
            project_id=project_id,
            date_from=period_from_obj,
            date_to=period_to_obj,
        )

    stats = build_wb_sku_pnl_snapshot(
        project_id=project_id,
        period_from=period_from_obj,
        period_to=period_to_obj,
        version=version,
        rebuild=rebuild,
    )

    return {
        "status": "completed",
        "domain": "wb_sku_pnl_snapshots",
        "stats": stats,
        "events_stats": events_stats,
    }
