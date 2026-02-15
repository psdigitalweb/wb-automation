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
    stats: Dict[str, Any] = {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "products",
        "finished_at": datetime.utcnow().isoformat(),
    }

    # Optional chaining: after products ingestion, build RRP snapshots from Internal Data.
    # This covers the common order on fresh DBs: Internal Data already imported, then products arrive.
    try:
        from sqlalchemy import text
        from app.db import engine
        from app.services.ingest import runs as runs_service
        from app.tasks.ingest_execute import execute_ingest as execute_ingest_task

        with engine.connect() as conn:
            has_internal_rrp = conn.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM internal_product_prices ipp
                    JOIN internal_data_snapshots ids ON ids.id = ipp.snapshot_id
                    WHERE ids.project_id = :project_id
                      AND ids.status IN ('success', 'partial')
                      AND ipp.rrp IS NOT NULL
                    LIMIT 1
                    """
                ),
                {"project_id": project_id},
            ).scalar() or 0

        if int(has_internal_rrp) > 0:
            if not runs_service.has_active_run(
                project_id=project_id,
                marketplace_code="internal",
                job_code="build_rrp_snapshots",
            ):
                build_run = runs_service.create_run_queued(
                    project_id=project_id,
                    marketplace_code="internal",
                    job_code="build_rrp_snapshots",
                    schedule_id=None,
                    triggered_by="chained",
                    params_json={
                        "chained_from_job": "products",
                        "chained_from_run_id": int(run_id),
                    },
                )
                build_run_id = int(build_run["id"])
                res = execute_ingest_task.delay(build_run_id)
                runs_service.set_run_celery_task_id(build_run_id, res.id)
                stats["chained_build_rrp_snapshots_run_id"] = build_run_id
            else:
                stats["chained_build_rrp_snapshots_skipped"] = "already_running_or_queued"
        else:
            stats["chained_build_rrp_snapshots_skipped"] = "no_internal_rrp_rows"
    except Exception as e:
        # Best-effort: do not fail products ingestion if chaining fails.
        logger.warning(
            f"products: failed to chain build_rrp_snapshots for project_id={project_id} run_id={run_id}: {e}",
            exc_info=True,
        )
        stats["chained_build_rrp_snapshots_error"] = f"{type(e).__name__}: {e}"

    return stats


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
        # #region agent log
        _has_active = runs_service.has_active_run(project_id=project_id, marketplace_code="wildberries", job_code="prices")
        try:
            with open(r"d:\Work\EcomCore\.cursor\debug.log", "a", encoding="utf-8") as _f:
                _f.write(__import__("json").dumps({"location": "registry.py:_wrap_frontend_prices:has_active_run", "message": "has_active_run(prices)", "data": {"project_id": project_id, "run_id": run_id, "has_active_run": _has_active}, "timestamp": int(time.time() * 1000), "hypothesisId": "H1"}) + "\n")
        except Exception:
            pass
        # #endregion
        if _has_active:
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
        # #region agent log
        try:
            with open(r"d:\Work\EcomCore\.cursor\debug.log", "a", encoding="utf-8") as _f:
                _f.write(__import__("json").dumps({"location": "registry.py:_wrap_frontend_prices:before_execute", "message": "before execute_ingest_task(prices_run_id)", "data": {"prices_run_id": prices_run["id"], "project_id": project_id}, "timestamp": int(time.time() * 1000), "hypothesisId": "H3"}) + "\n")
        except Exception:
            pass
        # #endregion
        # Run prices job synchronously and get dict result (Celery .apply() runs in current process)
        prices_result = execute_ingest_task.apply(args=(int(prices_run["id"]),))
        if not isinstance(prices_result, dict):
            prices_result = getattr(prices_result, "result", None) or {}
        dt_ms = int(round((time.monotonic() - t0) * 1000))
        # #region agent log
        try:
            with open(r"d:\Work\EcomCore\.cursor\debug.log", "a", encoding="utf-8") as _f:
                _f.write(__import__("json").dumps({"location": "registry.py:_wrap_frontend_prices:after_execute", "message": "prices_result", "data": {"prices_run_id": prices_run["id"], "result_type": type(prices_result).__name__, "result_status": prices_result.get("status") if isinstance(prices_result, dict) else None, "result_keys": list(prices_result.keys()) if isinstance(prices_result, dict) else [], "duration_ms": dt_ms}, "timestamp": int(time.time() * 1000), "hypothesisId": "H2_H4_H5"}) + "\n")
        except Exception:
            pass
        # #endregion

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
        # #region agent log
        try:
            with open(r"d:\Work\EcomCore\.cursor\debug.log", "a", encoding="utf-8") as _f:
                _f.write(__import__("json").dumps({"location": "registry.py:_wrap_frontend_prices:exception", "message": "exception in refresh prices", "data": {"project_id": project_id, "run_id": run_id, "exc_type": type(e).__name__, "exc_msg": str(e)[:500]}, "timestamp": int(time.time() * 1000), "hypothesisId": "H3"}) + "\n")
        except Exception:
            pass
        # #endregion
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

    import random
    import asyncio
    from sqlalchemy import text
    from app.db import engine
    from app.ingest_frontend_prices import ingest_frontend_brand_prices
    from app.services.ingest.runs import get_run, set_run_progress
    from app.tasks.ingestion import _get_frontend_prices_proxy_config

    # Load WB settings: brand_id, base_url_template, frontend_prices (limit, max_pages, sleep, brands[])
    with engine.connect() as conn:
        wb_row = conn.execute(
            text(
                """
                SELECT pm.settings_json->>'brand_id' AS brand_id,
                       pm.settings_json->'frontend_prices'->>'base_url_template' AS base_url_template,
                       pm.settings_json->'frontend_prices'->'brands' AS fp_brands,
                       pm.settings_json->'frontend_prices'->>'limit' AS fp_limit,
                       pm.settings_json->'frontend_prices'->>'max_pages' AS fp_max_pages,
                       pm.settings_json->'frontend_prices'->>'sleep_base_ms' AS fp_sleep_base_ms,
                       pm.settings_json->'frontend_prices'->>'sleep_jitter_ms' AS fp_sleep_jitter_ms,
                       pm.settings_json->'frontend_prices'->>'sleep_ms' AS fp_sleep_ms,
                       pm.settings_json->'frontend_prices'->>'http_min_retries' AS fp_http_min_retries,
                       pm.settings_json->'frontend_prices'->>'http_timeout_jitter_sec' AS fp_http_timeout_jitter_sec,
                       pm.settings_json->'frontend_prices'->>'min_coverage_ratio' AS fp_min_coverage_ratio,
                       pm.settings_json->'frontend_prices'->>'max_runtime_seconds' AS fp_max_runtime_seconds
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).mappings().first()

        sleep_ms_str = conn.execute(
            text("SELECT value->>'value' AS value FROM app_settings WHERE key = 'frontend_prices.sleep_ms'")
        ).scalar_one_or_none()
        max_pages_str = conn.execute(
            text("SELECT value->>'value' AS value FROM app_settings WHERE key = 'frontend_prices.max_pages'")
        ).scalar_one_or_none()

        base_url_template = (wb_row or {}).get("base_url_template") or ""
        if not base_url_template or not str(base_url_template).strip():
            base_url_template = conn.execute(
                text("SELECT value->>'url' AS url FROM app_settings WHERE key = 'frontend_prices.brand_base_url'")
            ).scalar_one_or_none()
    base_url_template = (base_url_template or "").strip()

    # Build brand_ids: (a) settings frontend_prices.brands with enabled=true, (b) else legacy settings_json.brand_id
    brand_ids: List[int] = []
    fp_brands = (wb_row or {}).get("fp_brands")
    if fp_brands is not None and isinstance(fp_brands, list):
        for b in fp_brands:
            if not isinstance(b, dict):
                continue
            if not b.get("enabled", True):
                continue
            bid = b.get("brand_id")
            if bid is not None:
                try:
                    brand_ids.append(int(bid))
                except (ValueError, TypeError):
                    pass
    if not brand_ids:
        brand_id_str = (wb_row or {}).get("brand_id")
        if brand_id_str:
            try:
                brand_ids = [int(brand_id_str)]
            except (ValueError, TypeError):
                return {
                    "ok": False,
                    "scope": "project",
                    "project_id": project_id,
                    "domain": "frontend_prices",
                    "reason": "invalid_brand_id",
                    "error": f"Invalid brand_id: {brand_id_str}",
                }

    if not brand_ids:
        return {
            "ok": False,
            "scope": "project",
            "project_id": project_id,
            "domain": "frontend_prices",
            "reason": "no_brands_configured",
            "error": "Добавьте бренды в Настройках Wildberries (блок «Бренды»).",
        }

    if not base_url_template:
        return {
            "ok": False,
            "scope": "project",
            "project_id": project_id,
            "domain": "frontend_prices",
            "reason": "base_url_template_not_configured",
            "error": "frontend_prices.base_url_template not set (WB marketplace settings or app_settings) with {brand_id} placeholder.",
        }

    limit = 50
    max_pages = 0
    sleep_base_ms = 800
    sleep_jitter_ms = 400
    if wb_row:
        try:
            if wb_row.get("fp_limit") is not None:
                limit = int(wb_row["fp_limit"])
        except (ValueError, TypeError):
            pass
        try:
            if wb_row.get("fp_max_pages") is not None:
                max_pages = int(wb_row["fp_max_pages"])
        except (ValueError, TypeError):
            pass
        try:
            if wb_row.get("fp_sleep_base_ms") is not None:
                sleep_base_ms = int(wb_row["fp_sleep_base_ms"])
            elif wb_row.get("fp_sleep_ms") is not None:
                sleep_base_ms = int(wb_row["fp_sleep_ms"])
        except (ValueError, TypeError):
            pass
        try:
            if wb_row.get("fp_sleep_jitter_ms") is not None:
                sleep_jitter_ms = int(wb_row["fp_sleep_jitter_ms"])
        except (ValueError, TypeError):
            pass
    fp_http_min_retries: Optional[int] = None
    fp_http_timeout_jitter_sec: Optional[int] = None
    if wb_row:
        try:
            if wb_row.get("fp_http_min_retries") is not None:
                fp_http_min_retries = int(wb_row["fp_http_min_retries"])
        except (ValueError, TypeError):
            pass
        try:
            if wb_row.get("fp_http_timeout_jitter_sec") is not None:
                fp_http_timeout_jitter_sec = int(wb_row["fp_http_timeout_jitter_sec"])
        except (ValueError, TypeError):
            pass
    fp_min_coverage_ratio: Optional[float] = None
    fp_max_runtime_seconds: Optional[int] = None
    if wb_row:
        try:
            if wb_row.get("fp_min_coverage_ratio") is not None:
                fp_min_coverage_ratio = float(wb_row["fp_min_coverage_ratio"])
        except (ValueError, TypeError):
            pass
        try:
            if wb_row.get("fp_max_runtime_seconds") is not None:
                fp_max_runtime_seconds = int(wb_row["fp_max_runtime_seconds"])
        except (ValueError, TypeError):
            pass
    # app_settings.sleep_ms only as fallback when project did not set sleep_base_ms/fp_sleep_ms
    project_has_sleep = wb_row and (
        wb_row.get("fp_sleep_base_ms") is not None or wb_row.get("fp_sleep_ms") is not None
    )
    if sleep_ms_str and not project_has_sleep:
        try:
            sleep_base_ms = int(sleep_ms_str)
        except (ValueError, TypeError):
            pass
    # app_settings.max_pages only as fallback when project did not set fp_max_pages
    project_has_max_pages = wb_row and wb_row.get("fp_max_pages") is not None
    if max_pages_str and not project_has_max_pages:
        try:
            max_pages = int(max_pages_str)
        except (ValueError, TypeError):
            max_pages = 0
    if max_pages > 0:
        max_pages = min(max_pages, 50)

    run = get_run(run_id) if run_id else None
    run_started_at = (run.get("started_at") or run.get("created_at")) if run else None
    proxy_url, proxy_scheme = _get_frontend_prices_proxy_config(int(project_id))

    # Optional debug: run only one brand
    params_json = (run.get("params_json") or {}) if run else {}
    debug_brand_id = params_json.get("brand_id")
    if debug_brand_id is not None:
        try:
            brand_ids = [int(debug_brand_id)]
        except (ValueError, TypeError):
            pass

    succeeded_brands: List[Dict[str, Any]] = []
    failed_brands: List[Dict[str, Any]] = []
    items_total = 0

    for i, bid in enumerate(brand_ids):
        if i > 0:
            await asyncio.sleep(random.uniform(0.4, 1.2))
        if run_id:
            set_run_progress(
                run_id,
                {
                    "phase": "frontend_prices",
                    "current_brand_id": bid,
                    "brands_done": len(succeeded_brands) + len(failed_brands),
                    "brands_total": len(brand_ids),
                    "succeeded_brands": succeeded_brands,
                    "failed_brands": failed_brands,
                },
            )
        logger.info(f"frontend_prices: brand {i+1}/{len(brand_ids)} brand_id={bid} project_id={project_id} run_id={run_id}")
        result = await ingest_frontend_brand_prices(
            brand_id=bid,
            base_url=base_url_template,
            max_pages=max_pages,
            sleep_ms=sleep_base_ms,
            sleep_jitter_ms=sleep_jitter_ms,
            limit=limit,
            run_id=run_id,
            project_id=project_id,
            run_started_at=run_started_at,
            proxy_url=proxy_url,
            proxy_scheme=proxy_scheme,
            http_min_retries=fp_http_min_retries,
            http_timeout_jitter_sec=fp_http_timeout_jitter_sec,
            min_coverage_ratio=fp_min_coverage_ratio,
            max_runtime_seconds=fp_max_runtime_seconds,
        )
        if isinstance(result, dict) and result.get("error"):
            failed_brands.append({
                "brand_id": bid,
                "reason": result.get("error"),
                "detail": result.get("detail"),
            })
            logger.warning(f"frontend_prices: brand_id={bid} failed: {result.get('error')}")
        else:
            cnt = result.get("distinct_nm_id") or result.get("items_saved") or 0
            succeeded_brands.append({
                "brand_id": bid,
                "products_count": cnt,
                "pages_count": result.get("pages_processed") or 0,
            })
            items_total += cnt

    failed_n = len(failed_brands)
    ok = failed_n == 0
    status_kind = "partial" if (failed_n > 0 and len(succeeded_brands) > 0) else ("success" if ok else "failed")
    stats: Dict[str, Any] = {
        "ok": ok,
        "scope": "project",
        "project_id": project_id,
        "domain": "frontend_prices",
        "brands_total": len(brand_ids),
        "succeeded_brands": succeeded_brands,
        "failed_brands": failed_brands,
        "items_total": items_total,
        "status": status_kind,
        "finished_at": datetime.utcnow().isoformat(),
    }
    # So run error_message shows real cause (execute_ingest uses stats.reason/error/message)
    if not ok and failed_brands:
        first = failed_brands[0]
        stats["reason"] = first.get("reason") or first.get("error") or "brand_failed"
        stats["error"] = first.get("reason") or first.get("detail")
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


async def _wrap_build_rrp_snapshots(project_id: int, run_id: int) -> Dict[str, Any]:
    """Build RRP snapshots from Internal Data.

    This is the preferred production workflow (no dependency on local XML files).
    """
    from app.services.internal_data.sync_rrp import sync_internal_data_to_rrp_snapshots

    result = sync_internal_data_to_rrp_snapshots(project_id=project_id)
    return {
        # Treat as ok=True even if data is missing; surface details in `result.errors`.
        # This mirrors other ingestion jobs that may legitimately produce 0 rows.
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "build_rrp_snapshots",
        "had_errors": bool((result or {}).get("errors")),
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
    "build_rrp_snapshots": {
        "job_code": "build_rrp_snapshots",
        "title": "Построение RRP snapshots (из Internal Data)",
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
    ("internal", "build_rrp_snapshots"): _wrap_build_rrp_snapshots,
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

