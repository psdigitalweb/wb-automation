from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Tuple, List, TypedDict, Optional
from datetime import datetime
import time
import logging

from app.ingest_stocks import ingest_stocks as _ingest_stocks
from app.ingest_prices import ingest_prices as _ingest_prices
# Warehouses ingestion is not project-scoped; reuse existing helper.
from app.ingest_stocks import ingest_warehouses as _ingest_warehouses
from app.ingest_products import ingest as _ingest_products
from app.ingest_supplier_stocks import ingest_supplier_stocks as _ingest_supplier_stocks
from app.tasks.ingestion import ingest_rrp_xml_task


RunCallable = Callable[..., Awaitable[Dict[str, Any]]]
logger = logging.getLogger(__name__)


class IngestJobNotFound(Exception):
    """Raised when no ingestion job is registered for (marketplace, job_code)."""


async def _wrap_ingest_warehouses(project_id: int, run_id: int) -> Dict[str, Any]:
    """Adapter to call global warehouses ingestion in a project-scoped context."""
    await _ingest_warehouses()
    return {
        "ok": True,
        "scope": "global",
        "project_id": project_id,
        "message": "Warehouses ingested (global)",
    }


async def _wrap_ingest_stocks(project_id: int, run_id: int) -> Dict[str, Any]:
    # run_id is currently unused in legacy implementation,
    # but is accepted for compatibility with ingest_runs-based jobs.
    result = await _ingest_stocks(project_id=project_id, run_id=run_id)
    if isinstance(result, dict):
        # Preserve explicit ok=False from ingestion logic.
        if "finished_at" not in result:
            result = {**result, "finished_at": datetime.utcnow().isoformat()}
        return result
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "stocks",
        "finished_at": datetime.utcnow().isoformat(),
    }


async def _wrap_ingest_prices(project_id: int, run_id: int) -> Dict[str, Any]:
    await _ingest_prices(project_id=project_id, run_id=run_id)
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "prices",
        "finished_at": datetime.utcnow().isoformat(),
    }


async def _wrap_ingest_products(project_id: int, run_id: int) -> Dict[str, Any]:
    await _ingest_products(project_id, loop_delay_s=0)
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "products",
        "finished_at": datetime.utcnow().isoformat(),
    }


async def _wrap_ingest_supplier_stocks(project_id: int, run_id: int) -> Dict[str, Any]:
    await _ingest_supplier_stocks(project_id=project_id, run_id=run_id)
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "supplier_stocks",
        "finished_at": datetime.utcnow().isoformat(),
    }


async def _wrap_frontend_prices(project_id: int, run_id: int) -> Dict[str, Any]:
    """Call frontend_prices ingestion directly (async) to avoid nested asyncio.run() calls.
    
    This avoids the issue where ingest_frontend_prices_task.run() calls asyncio.run()
    inside an already-running event loop (from run_async_safe).
    """
    # Step A) Refresh WB admin prices snapshot synchronously (strict: fail-fast).
    # This ensures frontend_prices report has fresh wb_discount/customer_price for SPP calc.
    try:
        from app.services.ingest import runs as runs_service
        from app.tasks.ingest_execute import execute_ingest as execute_ingest_task

        logger.info(
            f"frontend_prices: Refreshing WB prices snapshot before frontend prices ingest "
            f"(project_id={project_id}, run_id={run_id})"
        )
        print(
            f"frontend_prices: Refreshing WB prices snapshot before frontend prices ingest "
            f"(project_id={project_id}, run_id={run_id})"
        )

        # Avoid overlapping prices runs; strict mode treats this as failure to refresh.
        if runs_service.has_active_run(project_id=project_id, marketplace_code="wildberries", job_code="prices"):
            msg = (
                "Failed to refresh WB admin prices (job 'prices') before frontend prices ingest; "
                "prices job is already running or queued; retry later."
            )
            logger.warning(f"frontend_prices: {msg} project_id={project_id} run_id={run_id}")
            return {"ok": False, "reason": msg, "error_summary": msg}

        prices_run = runs_service.create_run_queued(
            project_id=project_id,
            marketplace_code="wildberries",
            job_code="prices",
            schedule_id=None,
            triggered_by="chained",
            params_json={
                "chained_from_job": "frontend_prices",
                "chained_from_run_id": int(run_id),
            },
        )

        t0 = time.monotonic()
        prices_result = execute_ingest_task(int(prices_run["id"]))
        dt_ms = int(round((time.monotonic() - t0) * 1000))

        logger.info(
            f"frontend_prices: prices refresh completed "
            f"status={prices_result.get('status')} prices_run_id={prices_run['id']} duration_ms={dt_ms} "
            f"project_id={project_id} run_id={run_id}"
        )
        print(
            f"frontend_prices: prices refresh completed "
            f"status={prices_result.get('status')} prices_run_id={prices_run['id']} duration_ms={dt_ms} "
            f"project_id={project_id} run_id={run_id}"
        )

        if prices_result.get("status") != "success":
            msg = (
                "Failed to refresh WB admin prices (job 'prices') before frontend prices ingest; retry later."
            )
            logger.warning(
                f"frontend_prices: {msg} project_id={project_id} run_id={run_id} "
                f"prices_run_id={prices_run['id']} prices_status={prices_result.get('status')}"
            )
            return {
                "ok": False,
                "reason": msg,
                "error_summary": msg,
                "prices_refresh_run_id": int(prices_run["id"]),
                "prices_refresh_status": prices_result.get("status"),
                "prices_refresh_duration_ms": dt_ms,
            }
    except Exception as e:
        # Strict mode: do not continue.
        msg = (
            "Failed to refresh WB admin prices (job 'prices') before frontend prices ingest; retry later."
        )
        logger.exception(
            f"frontend_prices: refresh prices failed (exception), project_id={project_id}, run_id={run_id}: "
            f"{type(e).__name__}: {e}"
        )
        print(
            f"frontend_prices: refresh prices failed (exception), project_id={project_id}, run_id={run_id}: "
            f"{type(e).__name__}: {e}"
        )
        return {"ok": False, "reason": msg, "error_summary": msg}

    from sqlalchemy import text
    from app.db import engine
    from app.ingest_frontend_prices import ingest_frontend_brand_prices
    from app.services.ingest.runs import get_run
    
    brand_id: int | None = None
    sleep_ms: int = 800
    max_pages: int = 0
    
    # Get configuration (same logic as ingest_frontend_prices_task)
    with engine.connect() as conn:
        brand_id_str = conn.execute(
            text(
                """
                SELECT pm.settings_json->>'brand_id' AS brand_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).scalar_one_or_none()
        
        sleep_ms_str = conn.execute(
            text(
                """
                SELECT value->>'value' AS value
                FROM app_settings
                WHERE key = 'frontend_prices.sleep_ms'
                """
            )
        ).scalar_one_or_none()
        
        max_pages_str = conn.execute(
            text(
                """
                SELECT value->>'value' AS value
                FROM app_settings
                WHERE key = 'frontend_prices.max_pages'
                """
            )
        ).scalar_one_or_none()
    
    if brand_id_str:
        try:
            brand_id = int(brand_id_str)
        except (ValueError, TypeError):
            return {
                "ok": False,
                "scope": "project",
                "project_id": project_id,
                "domain": "frontend_prices",
                "reason": "invalid_brand_id",
                "brand_id": brand_id_str,
            }
    else:
        return {
            "ok": False,
            "scope": "project",
            "project_id": project_id,
            "domain": "frontend_prices",
            "reason": "brand_id_not_configured_for_project",
        }
    
    if sleep_ms_str:
        try:
            sleep_ms = int(sleep_ms_str)
        except (ValueError, TypeError):
            sleep_ms = 800
    
    if max_pages_str:
        try:
            max_pages = int(max_pages_str)
        except (ValueError, TypeError):
            max_pages = 0
    
    # Hard safety cap
    if max_pages > 0:
        max_pages = min(max_pages, 50)
    
    # Get run_started_at for stable snapshot buckets
    run_started_at = None
    if run_id is not None:
        run = get_run(run_id)
        if run:
            run_started_at = run.get("started_at") or run.get("created_at")
    
    # Call async function directly (no nested asyncio.run())
    result = await ingest_frontend_brand_prices(
        brand_id=brand_id,
        base_url=None,
        max_pages=max_pages,
        sleep_ms=sleep_ms,
        run_id=run_id,
        project_id=project_id,
        run_started_at=run_started_at,
    )
    
    if isinstance(result, dict) and "error" in result:
        return {
            "ok": False,
            "scope": "project",
            "project_id": project_id,
            "domain": "frontend_prices",
            "brand_id": brand_id,
            **result,
        }
    
    # Normalize stats_json contract (same as ingest_frontend_prices_task)
    stats: Dict[str, Any] = {
        "ok": "error" not in result,
        "project_id": project_id,
        "brand_id": brand_id,
        "max_pages": max_pages,
        "items_total": result.get("distinct_nm_id") or result.get("items_saved") or 0,
        "current_upserts": result.get("current_upserts_total", 0),
        "snapshots_inserted": result.get("showcase_snapshots_inserted_total", 0),
        "spp_events_inserted": result.get("spp_events_inserted_total", 0),
        **{k: v for k, v in result.items() if k not in {
            "current_upserts_total",
            "showcase_snapshots_inserted_total",
            "spp_events_inserted_total",
        }},
    }
    
    return stats


async def _wrap_rrp_xml(project_id: int, run_id: int) -> Dict[str, Any]:
    result = ingest_rrp_xml_task.run(project_id, run_id=run_id)
    if isinstance(result, dict):
        return result
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "rrp_xml",
        "result": result,
        "finished_at": datetime.utcnow().isoformat(),
    }


async def _wrap_build_tax_statement(project_id: int, run_id: int) -> Dict[str, Any]:
    """Wrapper for build_tax_statement job.
    
    Reads period_id from run.params_json and calls build_tax_statement service.
    """
    from app.services.ingest.runs import get_run
    from app.services.financial.build_tax import build_tax_statement
    
    # Get run to extract params_json
    run = get_run(run_id)
    if not run:
        return {
            "ok": False,
            "reason": "run_not_found",
            "run_id": run_id,
        }
    
    params_json = run.get("params_json") or {}
    period_id = params_json.get("period_id")
    
    if not period_id:
        return {
            "ok": False,
            "reason": "period_id_missing",
            "run_id": run_id,
            "project_id": project_id,
        }
    
    # Call build service (sync function)
    result = build_tax_statement(project_id=project_id, period_id=period_id, run_id=run_id)
    return result


async def _wrap_wb_finances(project_id: int, run_id: int) -> Dict[str, Any]:
    """Wrapper for WB finances ingestion job.
    
    Reads date_from and date_to from run.params_json and calls ingestion.
    """
    from app.services.ingest.runs import get_run
    from app.tasks.wb_finances import ingest_wb_finance_reports_by_period_task
    from datetime import date as _date
    
    # Get run to extract params_json
    run = get_run(run_id)
    if not run:
        return {
            "ok": False,
            "reason": "run_not_found",
            "run_id": run_id,
        }
    
    params_json = run.get("params_json") or {}
    date_from_str = params_json.get("date_from")
    date_to_str = params_json.get("date_to")
    
    if not date_from_str or not date_to_str:
        return {
            "ok": False,
            "reason": "date_from_and_date_to_required",
            "run_id": run_id,
            "project_id": project_id,
        }
    
    # Validate date format
    try:
        date_from_obj = _date.fromisoformat(date_from_str)
        date_to_obj = _date.fromisoformat(date_to_str)
    except ValueError as e:
        return {
            "ok": False,
            "reason": "invalid_date_format",
            "error": str(e),
            "run_id": run_id,
            "project_id": project_id,
        }
    
    # Call Celery task synchronously (using .run() method)
    result = ingest_wb_finance_reports_by_period_task.run(
        project_id=project_id,
        date_from=date_from_str,
        date_to=date_to_str,
    )
    
    if isinstance(result, dict):
        return {
            "ok": result.get("status") == "completed",
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_finances",
            "result": result,
            "finished_at": datetime.utcnow().isoformat(),
        }
    
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "wb_finances",
        "result": result,
        "finished_at": datetime.utcnow().isoformat(),
    }


class JobDefinition(TypedDict):
    job_code: str
    title: str
    source_code: str
    supports_schedule: bool
    supports_manual: bool


_JOB_DEFINITIONS: Dict[str, JobDefinition] = {
    # Wildberries jobs
    "products": {
        "job_code": "products",
        "title": "Загрузка каталога товаров",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "warehouses": {
        "job_code": "warehouses",
        "title": "Загрузка складов",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "stocks": {
        "job_code": "stocks",
        "title": "Загрузка остатков FBS",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "supplier_stocks": {
        "job_code": "supplier_stocks",
        "title": "Загрузка остатков FBO",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "prices": {
        "job_code": "prices",
        "title": "Загрузка цен WB",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "frontend_prices": {
        "job_code": "frontend_prices",
        "title": "Загрузка цен с витрины",
        "source_code": "wildberries",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "wb_finances": {
        "job_code": "wb_finances",
        "title": "Загрузка финансовых отчётов WB",
        "source_code": "wildberries",
        "supports_schedule": False,  # Не поддерживает расписание (требует параметры)
        "supports_manual": True,
    },
    # Internal jobs
    "rrp_xml": {
        "job_code": "rrp_xml",
        "title": "Загрузка XML цен (1C)",
        "source_code": "internal",
        "supports_schedule": True,
        "supports_manual": True,
    },
    "build_tax_statement": {
        "job_code": "build_tax_statement",
        "title": "Расчёт налогового отчёта",
        "source_code": "internal",
        "supports_schedule": False,
        "supports_manual": True,
    },
}


_REGISTRY: Dict[Tuple[str, str], RunCallable] = {
    # marketplace_code (source_code), job_code -> callable(project_id) -> stats_json
    ("wildberries", "products"): _wrap_ingest_products,
    ("wildberries", "warehouses"): _wrap_ingest_warehouses,
    ("wildberries", "stocks"): _wrap_ingest_stocks,
    ("wildberries", "supplier_stocks"): _wrap_ingest_supplier_stocks,
    ("wildberries", "prices"): _wrap_ingest_prices,
    ("wildberries", "frontend_prices"): _wrap_frontend_prices,
    ("wildberries", "wb_finances"): _wrap_wb_finances,
    ("internal", "rrp_xml"): _wrap_rrp_xml,
    ("internal", "build_tax_statement"): _wrap_build_tax_statement,
}


async def execute_ingest_job(
    project_id: int,
    marketplace_code: str,
    job_code: str,
    run_id: int,
) -> Dict[str, Any]:
    """Execute ingestion job for given (project, marketplace, job_code).

    Returns stats_json dict.
    """
    key = (marketplace_code, job_code)
    fn = _REGISTRY.get(key)
    if not fn:
        raise IngestJobNotFound(
            f"No ingestion job registered for marketplace={marketplace_code}, job_code={job_code}"
        )
    # Pass run_id so ingestion can attribute writes to a specific ingest_runs row.
    return await fn(project_id, run_id)


def list_job_definitions() -> List[JobDefinition]:
    """Return all job definitions for public API / validation."""
    # Stable sort by source_code then title for nicer UX.
    return sorted(
        _JOB_DEFINITIONS.values(),
        key=lambda j: (j["source_code"], j["title"]),
    )


def get_job_definition(job_code: str) -> Optional[JobDefinition]:
    return _JOB_DEFINITIONS.get(job_code)

