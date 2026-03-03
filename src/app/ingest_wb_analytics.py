"""WB Analytics ingest: card stats daily, search query terms, search query daily."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db import engine
from app.db_wb_analytics import (
    get_wb_nm_ids_for_project,
    upsert_card_stats_daily,
    upsert_search_query_daily,
    upsert_search_query_terms,
)
from app.services.ingest.runs import get_last_wb_card_stats_daily_checkpoint, set_run_progress
from app.utils.get_project_marketplace_token import get_wb_analytics_token_for_project
from app.db_wb_backfill_state import (
    JOB_CODE_WB_CARD_STATS_DAILY,
    get_backfill_state,
    upsert_backfill_state_running,
    mark_backfill_state_paused,
    mark_backfill_state_completed,
    mark_backfill_state_failed,
    ensure_backfill_state_created,
)
from app.wb.analytics_client import (
    WBAnalyticsBadRequestError,
    WBAnalyticsClient,
    WBAnalyticsNetworkError,
    WBAnalyticsUnauthorizedError,
)

logger = logging.getLogger(__name__)

# nmIds limit per history request (swagger)
NM_IDS_BATCH_SIZE = 20
# Fast-path: chunk size for POST /api/analytics/v3/sales-funnel/products
FAST_PATH_CHUNK_SIZE = 1000
# Retries per batch before split or quarantine (hard resume)
MAX_BATCH_ATTEMPTS = 3

STRATEGY_FAST_PATH = "fast_path_products"
STRATEGY_LEGACY = "legacy_history"


def _cursor_for_json(c: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a JSON-serializable copy of cursor (date -> ISO string) for set_run_progress."""
    if not c or not isinstance(c, dict):
        return c
    d = c.get("date")
    if d is None:
        return {"date": None, "nm_offset": int(c.get("nm_offset") or 0)}
    date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
    return {"date": date_str, "nm_offset": int(c.get("nm_offset") or 0)}


def _ingest_error_stats(
    e: Exception,
    project_id: int,
    request_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build stats dict for ingest_error: error_type, error_message, error_repr, traceback (~2000 chars)."""
    from datetime import datetime as dt

    tb_full = traceback.format_exc()
    tb_out = tb_full[-2000:] if len(tb_full) > 2000 else tb_full
    out: Dict[str, Any] = {
        "ok": False,
        "reason": "ingest_error",
        "project_id": project_id,
        "error_type": type(e).__name__,
        "error_message": str(e),
        "error_repr": repr(e),
        "traceback": tb_out,
        "finished_at": dt.utcnow().isoformat(),
    }
    if request_summary is not None:
        out["request_summary"] = request_summary
    return out


# Known API -> DB column mapping for funnel history
FUNNEL_KNOWN_KEYS = {
    "date",
    "openCount",
    "cartCount",
    "orderCount",
    "orderSum",
    "buyoutCount",
    "buyoutSum",
    "buyoutPercent",
    "addToCartConversion",
    "cartToOrderConversion",
    "addToWishlistCount",
}


def _build_extra(obj: Dict[str, Any], known_keys: set) -> Dict[str, Any]:
    """extra = obj - known_keys (unknown keys only)."""
    return {k: v for k, v in obj.items() if k not in known_keys}


def _camel_to_snake(name: str) -> str:
    """openCount -> open_count."""
    result = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0:
            result.append("_")
        result.append(c.lower())
    return "".join(result)


# Keys from statistic.selected we map to columns; rest go to extra
FUNNEL_PRODUCTS_SELECTED_KNOWN = {
    "period",
    "openCount",
    "cartCount",
    "orderCount",
    "orderSum",
    "buyoutCount",
    "buyoutSum",
    "buyoutPercent",
    "addToWishlist",
    "conversions",
    "avgPrice",
    "cancelCount",
    "cancelSum",
    "timeToReady",
    "localizationPercent",
    "shareOrderPercent",
    "wbClub",
}


def _parse_sales_funnel_products_item(
    item: Dict[str, Any],
    currency: Optional[str],
    expected_stat_date: date,
) -> Dict[str, Any]:
    """Parse one element of data.products from sales-funnel/products into one row for wb_card_stats_daily."""
    product = item.get("product") or {}
    stat_block = item.get("statistic") or {}
    selected = stat_block.get("selected") or {}
    conversions = selected.get("conversions") or {}

    nm_raw = product.get("nmId") or product.get("nm_id")
    nm_id = int(nm_raw) if nm_raw is not None else 0

    extra: Dict[str, Any] = {}
    # Extra from statistic.selected (not in main columns)
    for key, value in selected.items():
        if key not in FUNNEL_PRODUCTS_SELECTED_KNOWN or value is None:
            continue
        if key in ("cancelCount", "cancelSum", "avgPrice", "timeToReady", "localizationPercent", "shareOrderPercent", "wbClub"):
            extra[key] = value
    if "stocks" in product and product["stocks"] is not None:
        extra["stocks"] = product["stocks"]
    # Optional product snapshot for debugging (keep small)
    if product:
        extra["product_snapshot"] = {
            k: product[k]
            for k in ("title", "vendorCode", "brandName", "subjectId", "subjectName", "productRating", "feedbackRating")
            if product.get(k) is not None
        }

    return {
        "nm_id": nm_id,
        "stat_date": expected_stat_date,
        "currency": currency,
        "open_count": selected.get("openCount") or 0,
        "cart_count": selected.get("cartCount") or 0,
        "order_count": selected.get("orderCount") or 0,
        "order_sum": selected.get("orderSum") or 0,
        "buyout_count": selected.get("buyoutCount") or 0,
        "buyout_sum": selected.get("buyoutSum") or 0,
        "buyout_percent": selected.get("buyoutPercent"),
        "add_to_cart_conversion": conversions.get("addToCartPercent"),
        "cart_to_order_conversion": conversions.get("cartToOrderPercent"),
        "add_to_wishlist_count": selected.get("addToWishlist") or 0,
        "extra": extra,
    }


def _rows_from_products_chunk(
    products: List[Dict[str, Any]],
    requested_nm_ids: List[int],
    stat_date: date,
    currency: Optional[str],
) -> List[Dict[str, Any]]:
    """Build rows from full chunk response: parsed products + zero-fill for missing nm_ids.
    Zero-fill only after full chunk response (no partial/truncation).
    """
    rows: List[Dict[str, Any]] = []
    returned_nm_ids = set()
    for it in products:
        row = _parse_sales_funnel_products_item(it, currency, stat_date)
        rows.append(row)
        returned_nm_ids.add(row["nm_id"])
    missing = set(requested_nm_ids) - returned_nm_ids
    for nm_id in missing:
        rows.append({
            "nm_id": nm_id,
            "stat_date": stat_date,
            "currency": currency,
            "open_count": 0,
            "cart_count": 0,
            "order_count": 0,
            "order_sum": 0,
            "buyout_count": 0,
            "buyout_sum": 0,
            "buyout_percent": None,
            "add_to_cart_conversion": None,
            "cart_to_order_conversion": None,
            "add_to_wishlist_count": 0,
            "extra": {},
        })
    return rows


def _parse_funnel_item(
    item: Dict[str, Any],
    nm_id: int,
    currency: Optional[str],
) -> List[Dict[str, Any]]:
    """Parse one product item from history response into rows for upsert."""
    rows = []
    product = item.get("product") or {}
    nm = product.get("nmId") or product.get("nm_id") or nm_id
    nm_id = int(nm) if nm is not None else nm_id
    curr = item.get("currency") or currency
    history = item.get("history") or []

    for h in history:
        stat_date = h.get("date")
        if not stat_date:
            continue
        try:
            if isinstance(stat_date, str) and len(stat_date) >= 10:
                stat_date = stat_date[:10]
            d = date.fromisoformat(stat_date) if isinstance(stat_date, str) else stat_date
        except (ValueError, TypeError):
            continue

        extra = _build_extra(h, FUNNEL_KNOWN_KEYS)
        row = {
            "nm_id": nm_id,
            "stat_date": d,
            "currency": curr,
            "open_count": h.get("openCount") or 0,
            "cart_count": h.get("cartCount") or 0,
            "order_count": h.get("orderCount") or 0,
            "order_sum": h.get("orderSum") or 0,
            "buyout_count": h.get("buyoutCount") or 0,
            "buyout_sum": h.get("buyoutSum") or 0,
            "buyout_percent": h.get("buyoutPercent"),
            "add_to_cart_conversion": h.get("addToCartConversion"),
            "cart_to_order_conversion": h.get("cartToOrderConversion"),
            "add_to_wishlist_count": h.get("addToWishlistCount") or 0,
            "extra": extra,
        }
        rows.append(row)
    return rows


def _parse_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse params_json for wb_card_stats_daily. Returns normalized dict."""
    p = (params or {}).copy()
    mode = (p.get("mode") or "daily").lower()
    if mode not in ("daily", "backfill"):
        mode = "daily"
    p["mode"] = mode

    today = date.today()

    def to_date(v: Any, default: date) -> date:
        if v is None:
            return default
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v[:10])
            except (ValueError, TypeError):
                return default
        return default

    p.setdefault("scope", "all")
    if mode == "daily":
        yesterday = today - timedelta(days=1)
        p["date_from"] = to_date(p.get("date_from"), yesterday)
        p["date_to"] = to_date(p.get("date_to"), yesterday)
    else:
        p.setdefault("max_seconds", 900)
        p.setdefault("max_batches", 200)
        p["date_to"] = to_date(p.get("date_to"), today)
        p["date_from"] = to_date(p.get("date_from"), p["date_to"] - timedelta(days=29))

    cursor = p.get("cursor")
    if isinstance(cursor, dict) and cursor.get("date") is not None:
        try:
            cursor = dict(cursor)
            cursor["date"] = to_date(cursor.get("date"), today)
            cursor["nm_offset"] = int(cursor.get("nm_offset") or 0)
            p["cursor"] = cursor
        except (ValueError, TypeError):
            p["cursor"] = None
    else:
        p["cursor"] = None

    return p


async def _run_daily_fast_path(
    project_id: int,
    run_id: int,
    client: WBAnalyticsClient,
    nm_ids: List[int],
    date_from: date,
    date_to: date,
) -> Dict[str, Any]:
    """Daily mode via POST sales-funnel/products (chunks of 1000). One strategy per run."""
    from datetime import datetime as dt

    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()
    total_rows = 0
    for offset in range(0, len(nm_ids), FAST_PATH_CHUNK_SIZE):
        chunk_nm_ids = nm_ids[offset : offset + FAST_PATH_CHUNK_SIZE]
        products, currency = await client.get_sales_funnel_products_all_pages(
            date_from=date_from_str,
            date_to=date_to_str,
            nm_ids=chunk_nm_ids,
            limit=FAST_PATH_CHUNK_SIZE,
            skip_deleted_nm=False,
        )
        rows = _rows_from_products_chunk(products, chunk_nm_ids, date_from, currency)
        with engine.begin() as conn:
            n = upsert_card_stats_daily(conn, project_id, run_id, rows)
        total_rows += n
        returned_count = len(products)
        missing_count = len(chunk_nm_ids) - returned_count
        logger.info(
            "wb_card_stats_daily fast-path daily chunk date=%s offset=%s requested_nm_ids=%s returned_products_count=%s missing_nm_ids_count=%s rows_upserted_batch=%s",
            date_from_str,
            offset,
            len(chunk_nm_ids),
            returned_count,
            missing_count,
            n,
        )
    return {
        "ok": True,
        "scope": "project",
        "project_id": project_id,
        "domain": "wb_card_stats_daily",
        "rows_upserted": total_rows,
        "nm_ids_total": len(nm_ids),
        "date_from": date_from_str,
        "date_to": date_to_str,
        "strategy": STRATEGY_FAST_PATH,
        "finished_at": dt.utcnow().isoformat(),
    }


async def ingest_wb_card_stats_daily(
    project_id: int,
    run_id: int,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest card stats (funnel history).

    Both daily and backfill modes use all known nm_ids from products so historical
    dates are not filtered by the SKU set active at ingest time.
    """
    from datetime import datetime as dt

    params = _parse_params(params)
    mode = params["mode"]
    today = date.today()

    token = get_wb_analytics_token_for_project(project_id)
    if not token:
        return {
            "ok": False,
            "reason": "no_analytics_token",
            "project_id": project_id,
            "error": "WB Analytics token not configured (settings_json.analytics_token or api_token)",
        }

    if mode == "daily":
        nm_ids = get_wb_nm_ids_for_project(project_id)
        date_from = params["date_from"]
        date_to = params["date_to"]
        if not nm_ids:
            return {
                "ok": True,
                "scope": "project",
                "project_id": project_id,
                "domain": "wb_card_stats_daily",
                "rows_upserted": 0,
                "nm_ids_total": 0,
                "reason": "no_nm_ids",
                "finished_at": dt.utcnow().isoformat(),
            }
        use_fast_path = params.get("use_fast_path") is True
        strategy = STRATEGY_FAST_PATH if use_fast_path else STRATEGY_LEGACY
        logger.info("wb_card_stats_daily: strategy=%s", strategy)
        semaphore = __import__("asyncio").Semaphore(1)
        client = WBAnalyticsClient(token=token, semaphore=semaphore)
        date_from_str = date_from.isoformat()
        date_to_str = date_to.isoformat()

        if use_fast_path:
            try:
                result = await _run_daily_fast_path(
                    project_id, run_id, client, nm_ids, date_from, date_to
                )
                return result
            except WBAnalyticsUnauthorizedError as e:
                return {
                    "ok": False,
                    "reason": "wb_analytics_unauthorized",
                    "project_id": project_id,
                    "status_code": e.status_code,
                    "error": str(e),
                }
            except WBAnalyticsBadRequestError as e:
                return {
                    "ok": False,
                    "reason": "wb_analytics_bad_request",
                    "project_id": project_id,
                    "status_code": e.status_code,
                    "error": e.detail,
                    "request_summary": e.request_summary,
                }
            except WBAnalyticsNetworkError as e:
                return {
                    "ok": False,
                    "reason": "wb_analytics_network_error",
                    "project_id": project_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e) or getattr(e, "message", ""),
                    "request_context": getattr(e, "request_context", None),
                    "finished_at": dt.utcnow().isoformat(),
                }
            except Exception as e:
                tb_full = traceback.format_exc()
                tb_tail = tb_full[-2000:] if len(tb_full) > 2000 else tb_full
                logger.exception("ingest_wb_card_stats_daily daily fast-path failed: %s", e)
                return _ingest_error_stats(e, project_id, getattr(e, "request_summary", None))

        # Legacy daily: history endpoint, batches of 20
        total_rows = 0
        try:
            for i in range(0, len(nm_ids), NM_IDS_BATCH_SIZE):
                batch = nm_ids[i : i + NM_IDS_BATCH_SIZE]
                try:
                    items = await client.get_sales_funnel_history(
                        nm_ids=batch,
                        date_from=date_from_str,
                        date_to=date_to_str,
                    )
                except WBAnalyticsUnauthorizedError as e:
                    return {
                        "ok": False,
                        "reason": "wb_analytics_unauthorized",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": str(e),
                    }
                except WBAnalyticsBadRequestError as e:
                    return {
                        "ok": False,
                        "reason": "wb_analytics_bad_request",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": e.detail,
                        "request_summary": e.request_summary,
                    }
                except WBAnalyticsNetworkError as e:
                    return {
                        "ok": False,
                        "reason": "wb_analytics_network_error",
                        "project_id": project_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e) or getattr(e, "message", ""),
                        "request_context": getattr(e, "request_context", None),
                        "finished_at": dt.utcnow().isoformat(),
                    }
                all_rows = []
                for item in items:
                    nm = (item.get("product") or {}).get("nmId") or (item.get("product") or {}).get("nm_id")
                    nm_id = int(nm) if nm is not None else (batch[0] if batch else 0)
                    curr = item.get("currency")
                    all_rows.extend(_parse_funnel_item(item, nm_id, curr))
                with engine.begin() as conn:
                    total_rows += upsert_card_stats_daily(conn, project_id, run_id, all_rows)
            return {
                "ok": True,
                "scope": "project",
                "project_id": project_id,
                "domain": "wb_card_stats_daily",
                "rows_upserted": total_rows,
                "nm_ids_total": len(nm_ids),
                "date_from": date_from_str,
                "date_to": date_to_str,
                "strategy": STRATEGY_LEGACY,
                "finished_at": dt.utcnow().isoformat(),
            }
        except Exception as e:
            tb_full = traceback.format_exc()
            tb_tail = tb_full[-2000:] if len(tb_full) > 2000 else tb_full
            logger.exception("ingest_wb_card_stats_daily daily failed: %s", e)
            logger.warning(
                "ingest_error detail: error_type=%s error_message=%s error_repr=%s traceback_len=%s",
                type(e).__name__,
                str(e),
                repr(e),
                len(tb_full),
            )
            logger.debug("ingest_error traceback (last 2000 chars): %s", tb_tail)
            return _ingest_error_stats(e, project_id, getattr(e, "request_summary", None))

    # backfill (source of truth: wb_backfill_range_state; retry/split/quarantine unchanged)
    date_from = params["date_from"]
    date_to = params["date_to"]
    max_seconds = int(params.get("max_seconds") or 900)
    max_batches = int(params.get("max_batches") or 200)
    cursor = params.get("cursor")
    loaded_cursor_source = params.pop("_loaded_cursor_source", None)

    nm_ids = get_wb_nm_ids_for_project(project_id)
    if not nm_ids:
        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_card_stats_daily",
            "rows_upserted": 0,
            "nm_ids_total": 0,
            "reason": "no_nm_ids",
            "finished_at": dt.utcnow().isoformat(),
        }

    range_state = get_backfill_state(
        project_id, JOB_CODE_WB_CARD_STATS_DAILY, date_from, date_to
    )
    range_status = (range_state or {}).get("status")
    logger.info(
        "wb_card_stats_daily backfill: range_state found status=%s date_from=%s date_to=%s",
        range_status or "none",
        date_from.isoformat(),
        date_to.isoformat(),
    )

    if range_state and range_state.get("status") == "completed":
        logger.info(
            "wb_card_stats_daily backfill: resume decision=already_completed date_from=%s date_to=%s",
            date_from.isoformat(),
            date_to.isoformat(),
        )
        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_card_stats_daily",
            "rows_upserted": 0,
            "nm_ids_total": len(nm_ids),
            "reason": "already_completed",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "cursor_end": {"date": date_to.isoformat(), "nm_offset": len(nm_ids)},
            "range_status": "completed",
            "finished_at": dt.utcnow().isoformat(),
        }

    # Guard: if range is already running, do not start second run, no WB calls
    if range_state and range_state.get("status") == "running":
        logger.info(
            "wb_card_stats_daily backfill: resume decision=already_running_for_range, "
            "ingest called but range running — second run blocked, no WB calls",
        )
        cursor_date = range_state.get("cursor_date")
        cursor_nm_offset = range_state.get("cursor_nm_offset")
        out = {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_card_stats_daily",
            "rows_upserted": 0,
            "reason": "already_running_for_range",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "loaded_cursor_source": "wb_backfill_range_state",
            "range_status": "running",
            "finished_at": dt.utcnow().isoformat(),
        }
        if cursor_date is not None and cursor_nm_offset is not None:
            out["cursor"] = {
                "date": cursor_date.isoformat() if hasattr(cursor_date, "isoformat") else str(cursor_date)[:10],
                "nm_offset": int(cursor_nm_offset),
            }
        return out

    # Strategy: fixed for whole run/range; from range_state if resumed
    meta = (range_state or {}).get("meta_json") or {}
    if not isinstance(meta, dict):
        meta = {}
    existing_strategy = meta.get("strategy")
    if existing_strategy in (STRATEGY_FAST_PATH, STRATEGY_LEGACY):
        strategy = existing_strategy
        logger.info(
            "wb_card_stats_daily backfill: strategy resumed from range_state strategy=%s",
            strategy,
        )
    else:
        strategy = STRATEGY_FAST_PATH if params.get("use_fast_path") else STRATEGY_LEGACY
        logger.info("wb_card_stats_daily backfill: strategy=%s (from params)", strategy)

    # Fallback: if no range state and no cursor, try old partial checkpoint from ingest_runs (migration only)
    if not range_state and not (isinstance(cursor, dict) and cursor and cursor.get("date") is not None):
        checkpoint = get_last_wb_card_stats_daily_checkpoint(
            project_id, date_from.isoformat(), date_to.isoformat()
        )
        if checkpoint:
            cursor = checkpoint["cursor"]
            loaded_cursor_source = f"ingest_runs:{checkpoint['run_id']}"
            logger.info(
                "wb_card_stats_daily backfill: resume decision=ingest_runs run_id=%s",
                checkpoint["run_id"],
            )
        else:
            logger.info(
                "wb_card_stats_daily backfill: resume decision=start (no state, no checkpoint)",
            )
    else:
        if not range_state and cursor and isinstance(cursor, dict) and cursor.get("date") is not None:
            logger.info(
                "wb_card_stats_daily backfill: resume decision=request (cursor in params)",
            )

    dates = [date_from + timedelta(days=k) for k in range((date_to - date_from).days + 1)]
    start_date_idx = 0
    start_nm_offset = 0

    if range_state and range_state.get("status") in ("paused", "failed"):
        logger.info(
            "wb_card_stats_daily backfill: resume decision=range_state status=%s",
            range_state.get("status"),
        )
        cursor_date = range_state.get("cursor_date")
        cursor_nm_offset = int(range_state.get("cursor_nm_offset") or 0)
        loaded_cursor_source = "wb_backfill_range_state"
        if cursor_date is not None:
            cursor_date_str = cursor_date.isoformat() if hasattr(cursor_date, "isoformat") else str(cursor_date)[:10]
            for i, d in enumerate(dates):
                if d.isoformat() == cursor_date_str:
                    start_date_idx = i
                    start_nm_offset = cursor_nm_offset
                    break
        cursor = {"date": dates[start_date_idx].isoformat() if dates else None, "nm_offset": start_nm_offset}
    else:
        if not range_state:
            ensure_backfill_state_created(
                project_id, JOB_CODE_WB_CARD_STATS_DAILY, date_from, date_to, run_id
            )
        if cursor:
            cursor_date = cursor.get("date")
            cursor_nm_offset = int(cursor.get("nm_offset") or 0)
            if cursor_date is not None:
                for i, d in enumerate(dates):
                    if d.isoformat() == str(cursor_date)[:10]:
                        start_date_idx = i
                        start_nm_offset = cursor_nm_offset
                        break
            loaded_cursor_source = loaded_cursor_source or "request"
        else:
            loaded_cursor_source = loaded_cursor_source or "start"
        cursor = {"date": dates[start_date_idx].isoformat(), "nm_offset": start_nm_offset}

    semaphore = __import__("asyncio").Semaphore(1)
    client = WBAnalyticsClient(token=token, semaphore=semaphore)
    started = time.monotonic()
    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()

    # Running stats (shared with _process_batch_with_retry / fast-path). _cursor_* = next batch to process (for failed state).
    run_context: Dict[str, Any] = {
        "processed_batches": 0,
        "processed_days": 0,
        "rows_upserted": 0,
        "failed_batches_count": 0,
        "quarantined_nm_ids": [],
        "saved_date_from": date_from_str,
        "saved_date_to": date_to_str,
        "_cursor_date": dates[start_date_idx],
        "_cursor_nm_offset": start_nm_offset,
        "strategy": strategy,
    }

    def save_progress(
        ctx: Dict[str, Any],
        next_cursor: Dict[str, Any],
        rows_this_batch: int,
    ) -> None:
        payload = {
            "loaded_cursor": _cursor_for_json(cursor),
            "loaded_cursor_source": loaded_cursor_source,
            "cursor": next_cursor,
            "saved_date_from": date_from_str,
            "saved_date_to": date_to_str,
            "range_status": range_status,
            "strategy": ctx.get("strategy") or strategy,
            "processed_batches": ctx["processed_batches"],
            "processed_days": ctx["processed_days"],
            "rows_upserted": ctx["rows_upserted"],
            "rows_upserted_batch": rows_this_batch,
            "failed_batches_count": ctx.get("failed_batches_count", 0),
            "quarantined_nm_ids": ctx.get("quarantined_nm_ids", []),
        }
        set_run_progress(run_id, payload)
        next_date = next_cursor.get("date")
        next_offset = int(next_cursor.get("nm_offset") or 0)
        try:
            next_date_obj = date.fromisoformat(str(next_date)[:10]) if next_date else date_from
        except (ValueError, TypeError):
            next_date_obj = date_from
        meta_json = {
            "strategy": ctx.get("strategy") or strategy,
            "processed_batches": ctx["processed_batches"],
            "rows_upserted": ctx["rows_upserted"],
        }
        upsert_backfill_state_running(
            project_id,
            JOB_CODE_WB_CARD_STATS_DAILY,
            date_from,
            date_to,
            run_id,
            cursor_date=next_date_obj,
            cursor_nm_offset=next_offset,
            meta_json=meta_json,
        )
        logger.info(
            "wb_card_stats_daily backfill: date=%s nm_offset=%s rows_upserted_batch=%s cursor_saved=%s",
            next_cursor.get("date"),
            next_cursor.get("nm_offset"),
            rows_this_batch,
            next_cursor,
        )

    async def _process_batch_with_retry(
        current_date_str: str,
        offset: int,
        batch: List[int],
        attempt: int = 0,
    ) -> Tuple[int, int, int]:
        """Process one batch (retry up to MAX_BATCH_ATTEMPTS, then split or quarantine). Returns (rows, delta, quarantined)."""
        try:
            items = await client.get_sales_funnel_history(
                nm_ids=batch,
                date_from=current_date_str,
                date_to=current_date_str,
            )
        except WBAnalyticsUnauthorizedError:
            raise
        except WBAnalyticsBadRequestError:
            raise
        except WBAnalyticsNetworkError as e:
            will_retry = attempt < MAX_BATCH_ATTEMPTS - 1
            will_split = not will_retry and len(batch) > 1
            will_skip_to_next = not will_retry and len(batch) == 1
            logger.warning(
                "wb_card_stats_daily backfill: network error date=%s nm_offset=%s attempt=%s will_retry=%s will_split=%s will_skip_to_next=%s",
                current_date_str,
                offset,
                attempt + 1,
                will_retry,
                will_split,
                will_skip_to_next,
            )
            if will_retry:
                return await _process_batch_with_retry(
                    current_date_str, offset, batch, attempt + 1
                )
            if len(batch) == 1:
                nm_id = batch[0]
                run_context["quarantined_nm_ids"].append(nm_id)
                run_context["failed_batches_count"] = run_context.get("failed_batches_count", 0) + 1
                logger.warning(
                    "wb_card_stats_daily backfill: quarantine date=%s nm_id=%s attempts=%s",
                    current_date_str,
                    nm_id,
                    MAX_BATCH_ATTEMPTS,
                )
                return (0, 1, 1)
            # Split into two halves
            mid = len(batch) // 2
            b1, b2 = batch[:mid], batch[mid:]
            r1, d1, q1 = await _process_batch_with_retry(
                current_date_str, offset, b1, 0
            )
            r2, d2, q2 = await _process_batch_with_retry(
                current_date_str, offset + d1, b2, 0
            )
            return (r1 + r2, d1 + d2, q1 + q2)

        all_rows = []
        for item in items:
            nm = (item.get("product") or {}).get("nmId") or (item.get("product") or {}).get("nm_id")
            nm_id = int(nm) if nm is not None else (batch[0] if batch else 0)
            curr = item.get("currency")
            all_rows.extend(_parse_funnel_item(item, nm_id, curr))
        with engine.begin() as conn:
            n = upsert_card_stats_daily(conn, project_id, run_id, all_rows)
        run_context["processed_batches"] += 1
        run_context["rows_upserted"] += n
        next_cursor = {"date": current_date_str, "nm_offset": offset + len(batch)}
        save_progress(run_context, next_cursor, n)
        return (n, len(batch), 0)

    try:
        logger.info(
            "wb_card_stats_daily backfill: start strategy=%s loaded_cursor=%s source=%s date_from=%s date_to=%s range_status=%s",
            strategy,
            cursor,
            loaded_cursor_source,
            date_from_str,
            date_to_str,
            range_status,
        )
        set_run_progress(
            run_id,
            {
                "loaded_cursor": _cursor_for_json(cursor),
                "loaded_cursor_source": loaded_cursor_source,
                "cursor": {"date": dates[start_date_idx].isoformat(), "nm_offset": start_nm_offset},
                "saved_date_from": date_from_str,
                "saved_date_to": date_to_str,
                "range_status": range_status,
                "strategy": strategy,
                "processed_batches": 0,
                "processed_days": 0,
                "rows_upserted": 0,
                "failed_batches_count": 0,
                "quarantined_nm_ids": [],
            },
        )

        if strategy == STRATEGY_FAST_PATH:
            # Fast-path: chunks of 1000 nmIds per request; zero-fill after full chunk response
            logger.info(
                "wb_card_stats_daily fast-path start date_from=%s date_to=%s nm_ids_total=%s batch_size=%s range_status=%s loaded_cursor=%s loaded_cursor_source=%s",
                date_from_str,
                date_to_str,
                len(nm_ids),
                FAST_PATH_CHUNK_SIZE,
                range_status,
                cursor,
                loaded_cursor_source,
            )
            for di in range(start_date_idx, len(dates)):
                current_date = dates[di]
                current_date_str = current_date.isoformat()
                day_start_offset = start_nm_offset if di == start_date_idx else 0
                offset = day_start_offset

                while offset < len(nm_ids):
                    run_context["_cursor_date"] = current_date
                    run_context["_cursor_nm_offset"] = offset
                    elapsed = time.monotonic() - started
                    if elapsed >= max_seconds:
                        logger.info(
                            "wb_card_stats_daily backfill fast-path: stopping max_seconds current_date=%s nm_offset=%s",
                            current_date_str,
                            offset,
                        )
                        mark_backfill_state_paused(
                            project_id,
                            JOB_CODE_WB_CARD_STATS_DAILY,
                            date_from,
                            date_to,
                            run_id,
                            cursor_date=current_date,
                            cursor_nm_offset=offset,
                            error_message="max_seconds",
                        )
                        return {
                            "ok": False,
                            "reason": "progress_saved",
                            "cursor": {"date": current_date_str, "nm_offset": offset},
                            "saved_date_from": date_from_str,
                            "saved_date_to": date_to_str,
                            "processed_days": run_context["processed_days"],
                            "processed_batches": run_context["processed_batches"],
                            "rows_upserted": run_context["rows_upserted"],
                            "project_id": project_id,
                            "domain": "wb_card_stats_daily",
                            "range_status": "paused",
                            "strategy": strategy,
                            "finished_at": dt.utcnow().isoformat(),
                        }
                    if run_context["processed_batches"] >= max_batches:
                        logger.info(
                            "wb_card_stats_daily backfill fast-path: stopping max_batches current_date=%s nm_offset=%s",
                            current_date_str,
                            offset,
                        )
                        mark_backfill_state_paused(
                            project_id,
                            JOB_CODE_WB_CARD_STATS_DAILY,
                            date_from,
                            date_to,
                            run_id,
                            cursor_date=current_date,
                            cursor_nm_offset=offset,
                            error_message="max_batches",
                        )
                        return {
                            "ok": False,
                            "reason": "progress_saved",
                            "cursor": {"date": current_date_str, "nm_offset": offset},
                            "saved_date_from": date_from_str,
                            "saved_date_to": date_to_str,
                            "processed_days": run_context["processed_days"],
                            "processed_batches": run_context["processed_batches"],
                            "rows_upserted": run_context["rows_upserted"],
                            "project_id": project_id,
                            "domain": "wb_card_stats_daily",
                            "range_status": "paused",
                            "strategy": strategy,
                            "finished_at": dt.utcnow().isoformat(),
                        }

                    chunk_nm_ids = nm_ids[offset : offset + FAST_PATH_CHUNK_SIZE]
                    try:
                        products, currency = await client.get_sales_funnel_products_all_pages(
                            date_from=current_date_str,
                            date_to=current_date_str,
                            nm_ids=chunk_nm_ids,
                            limit=FAST_PATH_CHUNK_SIZE,
                            skip_deleted_nm=False,
                        )
                    except WBAnalyticsUnauthorizedError as e:
                        err_msg = f"wb_analytics_unauthorized: {e}"
                        mark_backfill_state_failed(
                            project_id,
                            JOB_CODE_WB_CARD_STATS_DAILY,
                            date_from,
                            date_to,
                            run_id,
                            cursor_date=current_date,
                            cursor_nm_offset=offset,
                            error_message=err_msg[:2000],
                            meta_json={
                                "strategy": strategy,
                                "processed_batches": run_context["processed_batches"],
                                "rows_upserted": run_context["rows_upserted"],
                            },
                        )
                        return {
                            "ok": False,
                            "reason": "wb_analytics_unauthorized",
                            "project_id": project_id,
                            "status_code": e.status_code,
                            "error": str(e),
                            "range_status": "failed",
                            "cursor": {"date": current_date_str, "nm_offset": offset},
                            "finished_at": dt.utcnow().isoformat(),
                        }
                    except WBAnalyticsBadRequestError as e:
                        err_msg = f"wb_analytics_bad_request: {e.detail or e}"
                        mark_backfill_state_failed(
                            project_id,
                            JOB_CODE_WB_CARD_STATS_DAILY,
                            date_from,
                            date_to,
                            run_id,
                            cursor_date=current_date,
                            cursor_nm_offset=offset,
                            error_message=err_msg[:2000],
                            meta_json={
                                "strategy": strategy,
                                "processed_batches": run_context["processed_batches"],
                                "rows_upserted": run_context["rows_upserted"],
                            },
                        )
                        return {
                            "ok": False,
                            "reason": "wb_analytics_bad_request",
                            "project_id": project_id,
                            "status_code": e.status_code,
                            "error": e.detail,
                            "request_summary": e.request_summary,
                            "range_status": "failed",
                            "cursor": {"date": current_date_str, "nm_offset": offset},
                            "finished_at": dt.utcnow().isoformat(),
                        }
                    except WBAnalyticsNetworkError as e:
                        err_msg = f"wb_analytics_network_error: {e}"
                        mark_backfill_state_failed(
                            project_id,
                            JOB_CODE_WB_CARD_STATS_DAILY,
                            date_from,
                            date_to,
                            run_id,
                            cursor_date=current_date,
                            cursor_nm_offset=offset,
                            error_message=err_msg[:2000],
                            meta_json={
                                "strategy": strategy,
                                "processed_batches": run_context["processed_batches"],
                                "rows_upserted": run_context["rows_upserted"],
                            },
                        )
                        return {
                            "ok": False,
                            "reason": "wb_analytics_network_error",
                            "project_id": project_id,
                            "error": str(e),
                            "range_status": "failed",
                            "cursor": {"date": current_date_str, "nm_offset": offset},
                            "finished_at": dt.utcnow().isoformat(),
                        }

                    rows = _rows_from_products_chunk(
                        products, chunk_nm_ids, current_date, currency
                    )
                    with engine.begin() as conn:
                        n = upsert_card_stats_daily(conn, project_id, run_id, rows)
                    run_context["processed_batches"] += 1
                    run_context["rows_upserted"] += n
                    next_cursor = {"date": current_date_str, "nm_offset": offset + len(chunk_nm_ids)}
                    save_progress(run_context, next_cursor, n)
                    returned_count = len(products)
                    missing_count = len(chunk_nm_ids) - returned_count
                    logger.info(
                        "wb_card_stats_daily fast-path chunk date=%s nm_offset=%s requested_nm_ids=%s returned_products_count=%s missing_nm_ids_count=%s rows_upserted_batch=%s cursor_saved=%s",
                        current_date_str,
                        offset,
                        len(chunk_nm_ids),
                        returned_count,
                        missing_count,
                        n,
                        next_cursor,
                    )
                    offset += len(chunk_nm_ids)

                run_context["processed_days"] += 1
                start_nm_offset = 0

            logger.info(
                "wb_card_stats_daily backfill fast-path: reason=completed_range cursor_end=%s",
                {"date": date_to_str, "nm_offset": len(nm_ids)},
            )
            cursor_end = {"date": date_to_str, "nm_offset": len(nm_ids)}
            mark_backfill_state_completed(
                project_id,
                JOB_CODE_WB_CARD_STATS_DAILY,
                date_from,
                date_to,
                run_id,
                nm_ids_count=len(nm_ids),
                meta_json={
                    "strategy": strategy,
                    "processed_batches": run_context["processed_batches"],
                    "rows_upserted": run_context["rows_upserted"],
                },
            )
            return {
                "ok": True,
                "scope": "project",
                "project_id": project_id,
                "domain": "wb_card_stats_daily",
                "reason": "completed_range",
                "range_status": "completed",
                "rows_upserted": run_context["rows_upserted"],
                "nm_ids_total": len(nm_ids),
                "date_from": date_from_str,
                "date_to": date_to_str,
                "cursor_end": cursor_end,
                "processed_days": run_context["processed_days"],
                "processed_batches": run_context["processed_batches"],
                "strategy": strategy,
                "finished_at": dt.utcnow().isoformat(),
            }

        # Legacy backfill: history endpoint, batches of 20, retry/split/quarantine
        for di in range(start_date_idx, len(dates)):
            current_date = dates[di]
            current_date_str = current_date.isoformat()
            day_start_offset = start_nm_offset if di == start_date_idx else 0
            offset = day_start_offset

            while offset < len(nm_ids):
                run_context["_cursor_date"] = current_date
                run_context["_cursor_nm_offset"] = offset
                elapsed = time.monotonic() - started
                if elapsed >= max_seconds:
                    logger.info(
                        "wb_card_stats_daily backfill: stopping max_seconds current_date=%s nm_offset=%s",
                        current_date_str,
                        offset,
                    )
                    mark_backfill_state_paused(
                        project_id,
                        JOB_CODE_WB_CARD_STATS_DAILY,
                        date_from,
                        date_to,
                        run_id,
                        cursor_date=current_date,
                        cursor_nm_offset=offset,
                        error_message="max_seconds",
                    )
                    return {
                        "ok": False,
                        "reason": "progress_saved",
                        "cursor": {"date": current_date_str, "nm_offset": offset},
                        "saved_date_from": date_from_str,
                        "saved_date_to": date_to_str,
                        "processed_days": run_context["processed_days"],
                        "processed_batches": run_context["processed_batches"],
                        "rows_upserted": run_context["rows_upserted"],
                        "failed_batches_count": run_context.get("failed_batches_count", 0),
                        "quarantined_nm_ids": run_context.get("quarantined_nm_ids", []),
                        "project_id": project_id,
                        "domain": "wb_card_stats_daily",
                        "range_status": "paused",
                        "strategy": strategy,
                        "finished_at": dt.utcnow().isoformat(),
                    }
                if run_context["processed_batches"] >= max_batches:
                    logger.info(
                        "wb_card_stats_daily backfill: stopping max_batches current_date=%s nm_offset=%s",
                        current_date_str,
                        offset,
                    )
                    mark_backfill_state_paused(
                        project_id,
                        JOB_CODE_WB_CARD_STATS_DAILY,
                        date_from,
                        date_to,
                        run_id,
                        cursor_date=current_date,
                        cursor_nm_offset=offset,
                        error_message="max_batches",
                    )
                    return {
                        "ok": False,
                        "reason": "progress_saved",
                        "cursor": {"date": current_date_str, "nm_offset": offset},
                        "saved_date_from": date_from_str,
                        "saved_date_to": date_to_str,
                        "processed_days": run_context["processed_days"],
                        "processed_batches": run_context["processed_batches"],
                        "rows_upserted": run_context["rows_upserted"],
                        "failed_batches_count": run_context.get("failed_batches_count", 0),
                        "quarantined_nm_ids": run_context.get("quarantined_nm_ids", []),
                        "project_id": project_id,
                        "domain": "wb_card_stats_daily",
                        "range_status": "paused",
                        "strategy": strategy,
                        "finished_at": dt.utcnow().isoformat(),
                    }

                batch = nm_ids[offset : offset + NM_IDS_BATCH_SIZE]
                try:
                    rows, delta, quarantined = await _process_batch_with_retry(
                        current_date_str, offset, batch
                    )
                except WBAnalyticsUnauthorizedError as e:
                    err_msg = f"wb_analytics_unauthorized: {e}"
                    mark_backfill_state_failed(
                        project_id,
                        JOB_CODE_WB_CARD_STATS_DAILY,
                        date_from,
                        date_to,
                        run_id,
                        cursor_date=current_date,
                        cursor_nm_offset=offset,
                        error_message=err_msg[:2000],
                        meta_json={
                            "processed_batches": run_context["processed_batches"],
                            "processed_days": run_context["processed_days"],
                            "rows_upserted": run_context["rows_upserted"],
                            "failed_batches_count": run_context.get("failed_batches_count", 0),
                        },
                    )
                    return {
                        "ok": False,
                        "reason": "wb_analytics_unauthorized",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": str(e),
                        "range_status": "failed",
                        "cursor": {"date": current_date_str, "nm_offset": offset},
                        "finished_at": dt.utcnow().isoformat(),
                    }
                except WBAnalyticsBadRequestError as e:
                    err_msg = f"wb_analytics_bad_request: {e.detail or e}"
                    mark_backfill_state_failed(
                        project_id,
                        JOB_CODE_WB_CARD_STATS_DAILY,
                        date_from,
                        date_to,
                        run_id,
                        cursor_date=current_date,
                        cursor_nm_offset=offset,
                        error_message=err_msg[:2000],
                        meta_json={
                            "processed_batches": run_context["processed_batches"],
                            "processed_days": run_context["processed_days"],
                            "rows_upserted": run_context["rows_upserted"],
                            "failed_batches_count": run_context.get("failed_batches_count", 0),
                        },
                    )
                    return {
                        "ok": False,
                        "reason": "wb_analytics_bad_request",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": e.detail,
                        "request_summary": e.request_summary,
                        "range_status": "failed",
                        "cursor": {"date": current_date_str, "nm_offset": offset},
                        "finished_at": dt.utcnow().isoformat(),
                    }

                offset += delta

            run_context["processed_days"] += 1
            start_nm_offset = 0

        logger.info(
            "wb_card_stats_daily backfill: done processed_batches=%s processed_days=%s rows_upserted=%s cursor_end=%s failed_batches_count=%s quarantined_count=%s",
            run_context["processed_batches"],
            run_context["processed_days"],
            run_context["rows_upserted"],
            {"date": dates[-1].isoformat(), "nm_offset": len(nm_ids)},
            run_context.get("failed_batches_count", 0),
            len(run_context.get("quarantined_nm_ids", [])),
        )
        cursor_end = {"date": date_to_str, "nm_offset": len(nm_ids)}
        mark_backfill_state_completed(
            project_id,
            JOB_CODE_WB_CARD_STATS_DAILY,
            date_from,
            date_to,
            run_id,
            nm_ids_count=len(nm_ids),
            meta_json={
                "processed_batches": run_context["processed_batches"],
                "rows_upserted": run_context["rows_upserted"],
            },
        )
        logger.info(
            "wb_card_stats_daily backfill: reason=completed_range cursor_end=%s",
            cursor_end,
        )
        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_card_stats_daily",
            "reason": "completed_range",
            "range_status": "completed",
            "rows_upserted": run_context["rows_upserted"],
            "nm_ids_total": len(nm_ids),
            "date_from": date_from_str,
            "date_to": date_to_str,
            "cursor_end": cursor_end,
            "processed_days": run_context["processed_days"],
            "processed_batches": run_context["processed_batches"],
            "failed_batches_count": run_context.get("failed_batches_count", 0),
            "quarantined_count": len(run_context.get("quarantined_nm_ids", [])),
            "quarantined_nm_ids": run_context.get("quarantined_nm_ids", []),
            "strategy": strategy,
            "finished_at": dt.utcnow().isoformat(),
        }
    except Exception as e:
        tb_full = traceback.format_exc()
        tb_tail = tb_full[-2000:] if len(tb_full) > 2000 else tb_full
        logger.exception("ingest_wb_card_stats_daily backfill failed: %s", e)
        logger.warning(
            "ingest_error detail: error_type=%s error_message=%s error_repr=%s traceback_len=%s",
            type(e).__name__,
            str(e),
            repr(e),
            len(tb_full),
        )
        logger.debug("ingest_error traceback (last 2000 chars): %s", tb_tail)
        fail_cursor_date = run_context.get("_cursor_date")
        fail_cursor_offset = run_context.get("_cursor_nm_offset", 0)
        err_msg = f"{type(e).__name__}: {str(e)}"[:2000]
        mark_backfill_state_failed(
            project_id,
            JOB_CODE_WB_CARD_STATS_DAILY,
            date_from,
            date_to,
            run_id,
            cursor_date=fail_cursor_date,
            cursor_nm_offset=fail_cursor_offset,
            error_message=err_msg,
            meta_json={
                "processed_batches": run_context.get("processed_batches", 0),
                "processed_days": run_context.get("processed_days", 0),
                "rows_upserted": run_context.get("rows_upserted", 0),
                "failed_batches_count": run_context.get("failed_batches_count", 0),
            },
        )
        out = _ingest_error_stats(e, project_id, getattr(e, "request_summary", None))
        out["range_status"] = "failed"
        if fail_cursor_date is not None:
            out["cursor"] = {
                "date": fail_cursor_date.isoformat() if hasattr(fail_cursor_date, "isoformat") else str(fail_cursor_date)[:10],
                "nm_offset": fail_cursor_offset,
            }
        return out


# Known keys for search-texts (store rest in extra)
SEARCH_TERMS_KNOWN = {"searchText", "text", "frequency", "isAd"}

# Known keys for orders response (per day item)
SEARCH_ORDERS_KNOWN = {"date", "orders", "avgPosition"}


def _extract_search_text(obj: Dict[str, Any]) -> Optional[str]:
    """Get search_text from searchText or text."""
    return obj.get("searchText") or obj.get("text") or (obj.get("search_text") if isinstance(obj.get("search_text"), str) else None)


async def ingest_wb_search_queries_daily(
    project_id: int,
    run_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    top_nm_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Ingest search query terms and daily stats."""
    today = date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        date_from = today - timedelta(days=6)

    token = get_wb_analytics_token_for_project(project_id)
    if not token:
        return {
            "ok": False,
            "reason": "no_analytics_token",
            "project_id": project_id,
            "error": "WB Analytics token not configured",
        }

    nm_ids = get_wb_nm_ids_for_project(project_id, limit=top_nm_limit)
    if not nm_ids:
        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_search_queries_daily",
            "terms_upserted": 0,
            "daily_upserted": 0,
            "reason": "no_nm_ids",
        }

    semaphore = __import__("asyncio").Semaphore(1)
    client = WBAnalyticsClient(token=token, semaphore=semaphore)
    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()

    terms_total = 0
    daily_total = 0

    try:
        with engine.begin() as conn:
            for nm_id in nm_ids:
                try:
                    texts_raw = await client.get_search_texts(
                        nm_id=nm_id,
                        date_from=date_from_str,
                        date_to=date_to_str,
                    )
                except WBAnalyticsUnauthorizedError as e:
                    return {
                        "ok": False,
                        "reason": "wb_analytics_unauthorized",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": str(e),
                    }

                terms_rows = []
                texts_list: List[str] = []
                for t in texts_raw if isinstance(texts_raw, list) else []:
                    st = _extract_search_text(t) if isinstance(t, dict) else str(t)
                    if not st:
                        continue
                    texts_list.append(st)
                    extra = _build_extra(t, SEARCH_TERMS_KNOWN) if isinstance(t, dict) else {}
                    terms_rows.append({
                        "nm_id": nm_id,
                        "search_text": st,
                        "frequency": t.get("frequency") if isinstance(t, dict) else None,
                        "is_ad": t.get("isAd") if isinstance(t, dict) else None,
                        "extra": extra,
                    })

                if terms_rows:
                    terms_total += upsert_search_query_terms(conn, project_id, run_id, terms_rows)

                if not texts_list:
                    continue

                try:
                    orders_raw = await client.get_search_orders(
                        nm_id=nm_id,
                        texts=texts_list[:50],
                        date_from=date_from_str,
                        date_to=date_to_str,
                    )
                except WBAnalyticsUnauthorizedError as e:
                    return {
                        "ok": False,
                        "reason": "wb_analytics_unauthorized",
                        "project_id": project_id,
                        "status_code": e.status_code,
                        "error": str(e),
                    }

                daily_rows = []
                orders_data = orders_raw if isinstance(orders_raw, list) else []
                if isinstance(orders_raw, dict):
                    orders_data = orders_raw.get("data") or orders_raw.get("queries") or orders_raw.get("byQuery") or []

                for q in orders_data:
                    if not isinstance(q, dict):
                        continue
                    search_text = _extract_search_text(q) or ""
                    by_date = q.get("byDate") or q.get("byDay") or q.get("history") or []
                    if isinstance(q.get("items"), list):
                        by_date = q.get("items")
                    for d in by_date:
                        if not isinstance(d, dict):
                            continue
                        dt = d.get("date") or d.get("dt")
                        if not dt:
                            continue
                        try:
                            dt_str = dt[:10] if isinstance(dt, str) and len(dt) >= 10 else str(dt)
                            stat_date = date.fromisoformat(dt_str)
                        except (ValueError, TypeError):
                            continue
                        orders_val = d.get("orders") or d.get("orderCount") or 0
                        avg_pos = d.get("avgPosition")
                        extra = _build_extra(d, SEARCH_ORDERS_KNOWN)
                        daily_rows.append({
                            "nm_id": nm_id,
                            "search_text": search_text,
                            "stat_date": stat_date,
                            "orders": int(orders_val) if orders_val is not None else 0,
                            "avg_position": avg_pos,
                            "extra": extra,
                        })

                if daily_rows:
                    daily_total += upsert_search_query_daily(conn, project_id, run_id, daily_rows)

        return {
            "ok": True,
            "scope": "project",
            "project_id": project_id,
            "domain": "wb_search_queries_daily",
            "terms_upserted": terms_total,
            "daily_upserted": daily_total,
            "nm_ids_processed": len(nm_ids),
            "date_from": date_from_str,
            "date_to": date_to_str,
        }
    except Exception as e:
        logger.exception("ingest_wb_search_queries_daily failed: %s", e)
        return {
            "ok": False,
            "reason": "ingest_error",
            "project_id": project_id,
            "error": str(e),
        }
