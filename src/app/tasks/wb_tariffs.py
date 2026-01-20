"""Celery tasks for WB tariffs ingestion (marketplace-level, not project-scoped)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_commission")
def ingest_wb_tariffs_commission_task(locale: str = "ru") -> Dict[str, Any]:
    from app.ingest_wb_tariffs import ingest_wb_tariffs_commission

    result = asyncio.run(ingest_wb_tariffs_commission(locale=locale))
    return {"status": "completed", "domain": "wb_tariffs_commission", "result": result}


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_box")
def ingest_wb_tariffs_box_task(date_str: str) -> Dict[str, Any]:
    from datetime import date as _date
    from app.ingest_wb_tariffs import ingest_wb_tariffs_box

    target_date = _date.fromisoformat(date_str)
    result = asyncio.run(ingest_wb_tariffs_box(target_date))
    return {
        "status": "completed",
        "domain": "wb_tariffs_box",
        "date": date_str,
        "result": result,
    }


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_pallet")
def ingest_wb_tariffs_pallet_task(date_str: str) -> Dict[str, Any]:
    from datetime import date as _date
    from app.ingest_wb_tariffs import ingest_wb_tariffs_pallet

    target_date = _date.fromisoformat(date_str)
    result = asyncio.run(ingest_wb_tariffs_pallet(target_date))
    return {
        "status": "completed",
        "domain": "wb_tariffs_pallet",
        "date": date_str,
        "result": result,
    }


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_return")
def ingest_wb_tariffs_return_task(date_str: str) -> Dict[str, Any]:
    from datetime import date as _date
    from app.ingest_wb_tariffs import ingest_wb_tariffs_return

    target_date = _date.fromisoformat(date_str)
    result = asyncio.run(ingest_wb_tariffs_return(target_date))
    return {
        "status": "completed",
        "domain": "wb_tariffs_return",
        "date": date_str,
        "result": result,
    }


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_acceptance_coefficients")
def ingest_wb_tariffs_acceptance_coefficients_task(
    warehouse_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    from app.ingest_wb_tariffs import ingest_wb_tariffs_acceptance_coefficients

    result = asyncio.run(
        ingest_wb_tariffs_acceptance_coefficients(warehouse_ids=warehouse_ids)
    )
    return {
        "status": "completed",
        "domain": "wb_tariffs_acceptance_coefficients",
        "warehouse_ids": warehouse_ids,
        "result": result,
    }


@celery_app.task(name="app.tasks.wb_tariffs.ingest_wb_tariffs_all")
def ingest_wb_tariffs_all_task(days_ahead: int = 14) -> Dict[str, Any]:
    """Orchestrator: commission, acceptance, box/pallet/return for today..today+days_ahead."""
    from app.ingest_wb_tariffs import ingest_wb_tariffs_all

    result = asyncio.run(ingest_wb_tariffs_all(days_ahead=days_ahead))
    return {
        "status": "completed",
        "domain": "wb_tariffs_all",
        "days_ahead": days_ahead,
        "result": result,
    }

