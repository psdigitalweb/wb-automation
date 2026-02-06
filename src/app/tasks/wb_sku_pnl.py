"""Celery task for building WB SKU PnL snapshot."""

from __future__ import annotations

import json
import logging
from pathlib import Path as PathLib
from typing import Any, Dict

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _agent_log(location: str, message: str, data: dict, hypothesis_id: str = "H4") -> None:
    try:
        _log_path = PathLib(__file__).resolve().parent.parent.parent.parent / ".cursor" / "debug.log"
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"location": location, "message": message, "data": data, "timestamp": __import__("time").time() * 1000, "sessionId": "debug-session", "hypothesisId": hypothesis_id}) + "\n")
    except Exception:
        pass


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

    logger.info("build_wb_sku_pnl_snapshot_task start project_id=%s period=%s..%s", project_id, period_from, period_to)
    _agent_log("wb_sku_pnl.py:task", "task start", {"project_id": project_id, "period_from": period_from, "period_to": period_to}, "H4")

    period_from_obj = _date.fromisoformat(period_from)
    period_to_obj = _date.fromisoformat(period_to)

    events_stats = None
    if ensure_events:
        try:
            events_stats = build_wb_financial_events(
                project_id=project_id,
                date_from=period_from_obj,
                date_to=period_to_obj,
            )
            logger.info("build_wb_sku_pnl_snapshot_task ensure_events done events_stats=%s", events_stats)
            _agent_log("wb_sku_pnl.py:task", "ensure_events done", {"events_stats": str(events_stats)}, "H4")
        except Exception as e:
            logger.exception("build_wb_sku_pnl_snapshot_task ensure_events failed: %s", e)
            _agent_log("wb_sku_pnl.py:task", "ensure_events error", {"error": str(e)}, "H4")
            raise

    try:
        stats = build_wb_sku_pnl_snapshot(
            project_id=project_id,
            period_from=period_from_obj,
            period_to=period_to_obj,
            version=version,
            rebuild=rebuild,
        )
        logger.info("build_wb_sku_pnl_snapshot_task completed stats=%s", stats)
        if stats.get("inserted_rows") == 0 and stats.get("total_events") == 0:
            logger.warning(
                "SKU PnL snapshot built but 0 rows (project_id=%s %s..%s). Check wb_financial_events and WB reports for period.",
                project_id, period_from, period_to,
            )
        _agent_log("wb_sku_pnl.py:task", "build_wb_sku_pnl_snapshot done", {"stats": stats}, "H4")
    except Exception as e:
        logger.exception("build_wb_sku_pnl_snapshot_task builder failed: %s", e)
        _agent_log("wb_sku_pnl.py:task", "builder error", {"error": str(e)}, "H4")
        raise

    return {
        "status": "completed",
        "domain": "wb_sku_pnl_snapshots",
        "stats": stats,
        "events_stats": events_stats,
    }
