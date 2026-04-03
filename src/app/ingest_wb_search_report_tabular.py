"""WB Search Report (tabular) ingest using /api/v2/search-report/* methods."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

from app.db_wb_search_report import (
    create_search_report_snapshot,
    delete_search_report_snapshot,
    update_search_report_snapshot,
    upsert_search_report_products,
)
from app.utils.get_project_marketplace_token import get_wb_analytics_token_for_project
from app.wb.analytics_client import (
    WBAnalyticsBadRequestError,
    WBAnalyticsClient,
    WBAnalyticsNetworkError,
    WBAnalyticsUnauthorizedError,
)


logger = logging.getLogger(__name__)


def _parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _default_period_yesterday() -> tuple[date, date]:
    """Return yesterday as a full day period (server local date()).

    UI/manual runs should pass explicit dates (e.g. last 7 days) when needed.
    """
    today = date.today()
    y = today - timedelta(days=1)
    return (y, y)


def _build_past_period(period_from: date, period_to: date) -> Dict[str, str]:
    days = (period_to - period_from).days + 1
    past_to = period_from - timedelta(days=1)
    past_from = past_to - timedelta(days=days - 1)
    return {"start": past_from.isoformat(), "end": past_to.isoformat()}


async def ingest_wb_search_report_tabular(
    *,
    project_id: int,
    run_id: int,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest WB Search Report main page + full products table (tabular endpoints).

    Stores:
    - wb_search_report_snapshots (meta + raw main page)
    - wb_search_report_products (all products returned by table/details)
    """
    params = params or {}
    period_from = _parse_date(params.get("date_from") or params.get("period_from"))
    period_to = _parse_date(params.get("date_to") or params.get("period_to"))
    if period_from is None or period_to is None:
        period_from, period_to = _default_period_yesterday()
    if period_from > period_to:
        period_from, period_to = period_to, period_from

    include_search_texts = bool(params.get("include_search_texts", True))
    include_substituted_skus = bool(params.get("include_substituted_skus", True))
    position_cluster = str(params.get("position_cluster") or "all")
    order_by = params.get("order_by") if isinstance(params.get("order_by"), dict) else None
    if not order_by:
        order_by = {"field": "avgPosition", "mode": "asc"}

    token = get_wb_analytics_token_for_project(project_id)
    if not token:
        return {
            "ok": False,
            "reason": "no_analytics_token",
            "project_id": project_id,
            "error": "WB Analytics token not configured",
        }

    client = WBAnalyticsClient(token=token)
    current_period = {"start": period_from.isoformat(), "end": period_to.isoformat()}
    past_period = _build_past_period(period_from, period_to)

    request_params = {
        "currentPeriod": current_period,
        "pastPeriod": past_period,
        "positionCluster": position_cluster,
        "orderBy": order_by,
        "includeSubstitutedSKUs": include_substituted_skus,
        "includeSearchTexts": include_search_texts,
    }

    snapshot_id = create_search_report_snapshot(
        project_id=project_id,
        ingest_run_id=run_id,
        period_from=period_from,
        period_to=period_to,
        include_search_texts=include_search_texts,
        include_substituted_skus=include_substituted_skus,
        position_cluster=position_cluster,
        order_by=order_by,
        request_params=request_params,
    )

    pages = 0
    products_upserted = 0
    last_offset = 0
    last_fetched = 0
    last_error: Optional[str] = None
    try:
        # Main page (summary + charts). Best-effort: do not fail whole ingest if it fails.
        try:
            main = await client.search_report_main_page(
                current_period=current_period,
                past_period=past_period,
                order_by=order_by,
                position_cluster=position_cluster,
                include_substituted_skus=include_substituted_skus,
                include_search_texts=include_search_texts,
                limit=int(params.get("main_limit") or 1000),
                offset=int(params.get("main_offset") or 0),
            )
        except Exception as e:
            logger.warning("wb_search_report_tabular: main page failed: %s", e)
            main = {}
        update_search_report_snapshot(snapshot_id=snapshot_id, raw_main_page=main)

        # Details table: all products via offset pagination (limit<=1000).
        limit = int(params.get("limit") or 1000)
        if limit < 1:
            limit = 1000
        if limit > 1000:
            limit = 1000

        offset = 0
        while True:
            pages += 1
            # Extra resilience on flaky connectivity: retry a few times per page (in addition to client retries).
            resp = None
            for page_attempt in range(5):
                try:
                    resp = await client.search_report_table_details(
                        current_period=current_period,
                        past_period=past_period,
                        order_by=order_by,
                        position_cluster=position_cluster,
                        include_substituted_skus=include_substituted_skus,
                        include_search_texts=include_search_texts,
                        limit=limit,
                        offset=offset,
                    )
                    last_error = None
                    break
                except WBAnalyticsNetworkError as e:
                    last_error = f"{type(e).__name__}: {e}"
                    if page_attempt >= 4:
                        raise
                    # Backoff: 10s, 20s, 40s, 80s (plus client's own throttling).
                    await asyncio.sleep(10 * (2**page_attempt))

            if resp is None:
                raise WBAnalyticsNetworkError("Empty response after retries", request_context={"offset": offset})
            data = resp.get("data") if isinstance(resp, dict) else None
            if not isinstance(data, dict):
                data = {}
            products = data.get("products")
            if not isinstance(products, list):
                products = []
            fetched = len(products)
            last_offset = offset
            last_fetched = fetched
            if products:
                products_upserted += upsert_search_report_products(
                    snapshot_id=snapshot_id,
                    project_id=project_id,
                    ingest_run_id=run_id,
                    rows=products,
                )

            # Progress for UI
            try:
                from app.services.ingest.runs import set_run_progress

                set_run_progress(
                    run_id,
                    {
                        "snapshot_id": snapshot_id,
                        "pages": pages,
                        "offset": offset,
                        "limit": limit,
                        "last_fetched": fetched,
                        "products_upserted": products_upserted,
                        "last_error": last_error,
                    },
                )
            except Exception:
                pass
            if fetched < limit or fetched == 0:
                break
            offset += limit

        stats = {
            "pages": pages,
            "products_upserted": products_upserted,
            "last_offset": last_offset,
            "last_fetched": last_fetched,
        }

        update_search_report_snapshot(snapshot_id=snapshot_id, stats=stats)
        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_search_report_tabular",
            "snapshot_id": snapshot_id,
            "date_from": period_from.isoformat(),
            "date_to": period_to.isoformat(),
            **stats,
        }
    except WBAnalyticsUnauthorizedError as e:
        if products_upserted == 0:
            delete_search_report_snapshot(snapshot_id=snapshot_id)
        else:
            update_search_report_snapshot(
                snapshot_id=snapshot_id,
                stats={
                    "ok": False,
                    "reason": "wb_analytics_unauthorized",
                    "status_code": e.status_code,
                    "error": str(e),
                },
            )
        return {
            "ok": False,
            "reason": "wb_analytics_unauthorized",
            "project_id": project_id,
            "status_code": e.status_code,
            "error": str(e),
            "snapshot_id": snapshot_id,
            "snapshot_deleted": products_upserted == 0,
        }
    except WBAnalyticsBadRequestError as e:
        if products_upserted == 0:
            delete_search_report_snapshot(snapshot_id=snapshot_id)
        else:
            update_search_report_snapshot(
                snapshot_id=snapshot_id,
                stats={
                    "ok": False,
                    "reason": "wb_analytics_bad_request",
                    "status_code": e.status_code,
                    "error": str(e),
                    "request_summary": getattr(e, "request_summary", None),
                },
            )
        return {
            "ok": False,
            "reason": "wb_analytics_bad_request",
            "project_id": project_id,
            "status_code": e.status_code,
            "error": str(e),
            "request_summary": getattr(e, "request_summary", None),
            "snapshot_id": snapshot_id,
            "snapshot_deleted": products_upserted == 0,
        }
    except WBAnalyticsNetworkError as e:
        if products_upserted == 0:
            delete_search_report_snapshot(snapshot_id=snapshot_id)
        else:
            update_search_report_snapshot(
                snapshot_id=snapshot_id,
                stats={
                    "ok": False,
                    "reason": "wb_analytics_network_error",
                    "error": str(e),
                    "request_context": getattr(e, "request_context", None),
                },
            )
        return {
            "ok": False,
            "reason": "wb_analytics_network_error",
            "project_id": project_id,
            "error": str(e),
            "request_context": getattr(e, "request_context", None),
            "snapshot_id": snapshot_id,
            "snapshot_deleted": products_upserted == 0,
        }
    except Exception as e:
        logger.exception("ingest_wb_search_report_tabular failed: %s", e)
        if products_upserted == 0:
            delete_search_report_snapshot(snapshot_id=snapshot_id)
        else:
            update_search_report_snapshot(
                snapshot_id=snapshot_id,
                stats={"ok": False, "reason": "ingest_error", "error": str(e)},
            )
        return {
            "ok": False,
            "reason": "ingest_error",
            "project_id": project_id,
            "error": str(e),
            "snapshot_id": snapshot_id,
            "snapshot_deleted": products_upserted == 0,
        }
