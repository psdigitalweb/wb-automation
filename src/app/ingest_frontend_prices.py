"""Ingestion endpoint for frontend catalog prices from WB public API."""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, BackgroundTasks, Body
from pydantic import BaseModel
from sqlalchemy import text

from app.db import engine
from app.services.wb_current import (
    compute_hour_bucket_utc,
    upsert_wb_current_metrics_on_conn,
)
from app import settings
from app.wb.catalog_client import CatalogClient

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


class FrontendBrandPricesRequest(BaseModel):
    brand_id: int
    base_url: Optional[str] = None  # If not provided, will be read from app_settings
    max_pages: int = 0  # 0 or null = until empty
    sleep_ms: int = 800


def compute_retry_sleep_seconds(retry_count: int) -> int:
    """Compute exponential backoff with jitter for rate-limited retries.

    base = min(20 * (2 ** (retry_count - 1)), 120)
    jitter = random.uniform(-0.25, +0.25)
    sleep = clamp(base * (1 + jitter), 10, 120)
    """
    if retry_count <= 0:
        retry_count = 1
    base = min(20 * (2 ** (retry_count - 1)), 120)
    jitter = random.uniform(-0.25, 0.25)
    sleep = base * (1.0 + jitter)
    sleep = max(10.0, min(float(settings.FRONTEND_PRICES_MAX_RETRY_SLEEP_SECONDS), sleep))
    return int(round(sleep))


async def sleep_with_heartbeat(
    *,
    run_id: int | None,
    total_seconds: float,
    tick: int = 10,
    progress: Dict[str, Any] | None = None,
) -> None:
    """Sleep in small chunks while touching heartbeat and updating stats_json."""
    if total_seconds <= 0:
        return
    if run_id is None:
        await asyncio.sleep(float(total_seconds))
        return

    remaining = float(total_seconds)
    while remaining > 0:
        chunk = float(min(float(tick), remaining))
        await asyncio.sleep(chunk)
        remaining = max(0.0, remaining - chunk)

        try:
            from app.services.ingest import runs as runs_service

            runs_service.touch_run(int(run_id))

            if progress is not None:
                now_iso = datetime.now(timezone.utc).isoformat()
                runs_service.set_run_progress(
                    int(run_id),
                    {
                        **progress,
                        "last_progress_at": now_iso,
                        "sleeping": True,
                        "sleep_remaining_seconds": int(round(remaining)),
                    },
                )
        except Exception:
            # Never break ingestion due to heartbeat/stats updates.
            pass

def extract_products_from_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract products array from various response formats (universal, like pickProducts in Apps Script).
    
    Tries in order:
    1. data.products (most common for catalog.wb.ru)
    2. data.data.products
    3. data.data.products.products (nested)
    4. data.data.catalog.products
    5. data.data.list (if list of objects)
    6. data.catalog.products
    7. data.listGoods
    8. data.data.listGoods
    """
    if isinstance(data, dict):
        # Try data.products first (most common for catalog.wb.ru)
        if "products" in data:
            products = data["products"]
            if isinstance(products, list):
                print(f"extract_products: found {len(products)} products in data.products")
                return products
        
        # Try data.data.products
        if "data" in data and isinstance(data["data"], dict):
            # Try data.data.products
            if "products" in data["data"]:
                products = data["data"]["products"]
                if isinstance(products, list):
                    print(f"extract_products: found {len(products)} products in data.data.products")
                    return products
                elif isinstance(products, dict) and "products" in products:
                    # Nested: data.data.products.products
                    nested = products["products"]
                    if isinstance(nested, list):
                        print(f"extract_products: found {len(nested)} products in data.data.products.products")
                        return nested
            
            # Try data.data.catalog.products
            if "catalog" in data["data"] and isinstance(data["data"]["catalog"], dict):
                if "products" in data["data"]["catalog"]:
                    products = data["data"]["catalog"]["products"]
                    if isinstance(products, list):
                        print(f"extract_products: found {len(products)} products in data.data.catalog.products")
                        return products
            
            # Try data.data.list (if list of objects)
            if "list" in data["data"]:
                products = data["data"]["list"]
                if isinstance(products, list):
                    print(f"extract_products: found {len(products)} products in data.data.list")
                    return products
            
            # Try data.data.listGoods
            if "listGoods" in data["data"]:
                products = data["data"]["listGoods"]
                if isinstance(products, list):
                    print(f"extract_products: found {len(products)} products in data.data.listGoods")
                    return products
        
        # Try data.catalog.products
        if "catalog" in data and isinstance(data["catalog"], dict):
            if "products" in data["catalog"]:
                products = data["catalog"]["products"]
                if isinstance(products, list):
                    print(f"extract_products: found {len(products)} products in data.catalog.products")
                    return products
        
        # Try data.listGoods
        if "listGoods" in data:
            products = data["listGoods"]
            if isinstance(products, list):
                print(f"extract_products: found {len(products)} products in data.listGoods")
                return products
        
        # Log structure for debugging
        print(f"extract_products: no products found, top-level keys: {list(data.keys())}")
        if "data" in data and isinstance(data["data"], dict):
            print(f"extract_products: data.data keys: {list(data['data'].keys())}")
    
    elif isinstance(data, list):
        # Root level is list
        print(f"extract_products: root level is list with {len(data)} items")
        return data
    
    print("extract_products: no products found, returning empty list")
    return []


def extract_total_pages(data: Dict[str, Any], products_per_page: int = 100) -> Optional[int]:
    """Extract total pages count from response.
    
    Tries:
    - totalPages / pages / pageCount (direct)
    - total / totalCount (calculate pages = ceil(total / products_per_page))
    - data.totalPages / data.pages / data.pageCount
    - data.total / data.totalCount (calculate)
    - data.pager.total / data.pager.pages
    """
    if not isinstance(data, dict):
        return None
    
    # Try direct fields
    for field in ["totalPages", "pages", "pageCount"]:
        if field in data:
            value = data[field]
            if isinstance(value, (int, float)) and value > 0:
                print(f"extract_total_pages: found {field}={int(value)}")
                return int(value)
    
    # Try total/totalCount and calculate pages
    for field in ["total", "totalCount"]:
        if field in data:
            value = data[field]
            if isinstance(value, (int, float)) and value > 0:
                pages = (int(value) + products_per_page - 1) // products_per_page  # ceil division
                print(f"extract_total_pages: found {field}={int(value)}, calculated pages={pages}")
                return pages
    
    # Try data.totalPages / data.pages / data.pageCount
    if "data" in data and isinstance(data["data"], dict):
        for field in ["totalPages", "pages", "pageCount"]:
            if field in data["data"]:
                value = data["data"][field]
                if isinstance(value, (int, float)) and value > 0:
                    print(f"extract_total_pages: found data.{field}={int(value)}")
                    return int(value)
        
        # Try data.total / data.totalCount
        for field in ["total", "totalCount"]:
            if field in data["data"]:
                value = data["data"][field]
                if isinstance(value, (int, float)) and value > 0:
                    pages = (int(value) + products_per_page - 1) // products_per_page
                    print(f"extract_total_pages: found data.{field}={int(value)}, calculated pages={pages}")
                    return pages
        
        # Try data.pager.total / data.pager.pages
        if "pager" in data["data"] and isinstance(data["data"]["pager"], dict):
            if "pages" in data["data"]["pager"]:
                value = data["data"]["pager"]["pages"]
                if isinstance(value, (int, float)) and value > 0:
                    print(f"extract_total_pages: found data.pager.pages={int(value)}")
                    return int(value)
            if "total" in data["data"]["pager"]:
                value = data["data"]["pager"]["total"]
                if isinstance(value, (int, float)) and value > 0:
                    pages = (int(value) + products_per_page - 1) // products_per_page
                    print(f"extract_total_pages: found data.pager.total={int(value)}, calculated pages={pages}")
                    return pages
    
    print(f"extract_total_pages: no total pages found, top-level keys: {list(data.keys())}")
    return None


def extract_page_from_url(url: str) -> int:
    """Extract page number from URL (defaults to 1 if not found)."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    page_str = query_params.get("page", ["1"])[0]
    try:
        return int(page_str)
    except (ValueError, TypeError):
        return 1


def get_brand_base_url_from_settings() -> Optional[str]:
    """Get frontend prices brand base URL from app_settings."""
    sql = text("""
        SELECT value->>'url' AS url
        FROM app_settings
        WHERE key = 'frontend_prices.brand_base_url'
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(sql).scalar_one_or_none()
            return result if result else None
    except Exception as e:
        print(f"get_brand_base_url_from_settings: error: {e}")
        return None


async def ingest_frontend_brand_prices(
    brand_id: int,
    base_url: Optional[str] = None,
    max_pages: int = 0,
    sleep_ms: int = 800,
    run_id: int | None = None,
    project_id: int | None = None,
    run_started_at: datetime | None = None,
) -> Dict[str, Any]:
    """Fetch and insert frontend catalog price snapshots from WB public API."""
    # If base_url not provided, get it from settings
    if not base_url or not base_url.strip():
        base_url = get_brand_base_url_from_settings()
        if not base_url:
            return {
                "error": "brand_base_url not configured. Please set it via PUT /api/v1/settings/frontend-prices/brand-url or provide base_url in request."
            }
        print(f"ingest_frontend_brand_prices: using base_url from settings: {base_url[:100]}...")
    
    start_page = extract_page_from_url(base_url)
    
    # Fallback for run_started_at: use \"now\" if not provided (e.g. manual HTTP run)
    if run_started_at is None:
        run_started_at = datetime.now(timezone.utc)
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=timezone.utc)

    run_at = run_started_at
    run_at_iso = run_started_at.isoformat()

    print(
        f"ingest_frontend_prices: starting, brand_id={brand_id}, start_page={start_page}, "
        f"max_pages={max_pages}, sleep_ms={sleep_ms}, run_at={run_at_iso}, run_id={run_id}"
    )
    
    client = CatalogClient()
    
    # Check if table exists
    check_table_sql = text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'frontend_catalog_price_snapshots'
        )
    """)
    
    table_exists = False
    with engine.connect() as conn:
        result = conn.execute(check_table_sql).scalar_one_or_none()
        table_exists = result is True
    
    if not table_exists:
        print("ingest_frontend_prices: ERROR - table frontend_catalog_price_snapshots does not exist")
        return {"error": "Table frontend_catalog_price_snapshots does not exist. Run migrations."}
    
    # Prepare insert SQL
    insert_sql = text("""
        INSERT INTO frontend_catalog_price_snapshots 
        (snapshot_at, source, query_type, query_value, page, nm_id, vendor_code, name, 
         price_basic, price_product, sale_percent, discount_calc_percent, raw)
        VALUES 
        (:snapshot_at, 'catalog_wb', 'brand', :query_value, :page, :nm_id, :vendor_code, :name,
         :price_basic, :price_product, :sale_percent, :discount_calc_percent, CAST(:raw AS jsonb))
    """)
    
    total_inserted = 0
    total_products = 0
    pages_fetched = 0
    page = start_page
    total_pages: Optional[int] = None
    expected_total: Optional[int] = None
    failed_pages: list[int] = []
    empty_pages_count = 0  # Count consecutive empty pages
    seen_nm_ids: set[int] = set()
    dup_in_run = 0
    spp_events_inserted_total = 0
    showcase_snapshots_inserted_total = 0
    current_upserts_total = 0

    # Retry accounting (rate limit)
    total_retry_wait_seconds = 0
    started_monotonic = time.monotonic()

    # If run is linked to a schedule, we can reschedule it when rate-limited.
    schedule_id: int | None = None
    if run_id is not None:
        try:
            from app.services.ingest import runs as runs_service

            run_row = runs_service.get_run(int(run_id))
            if run_row and run_row.get("schedule_id") is not None:
                schedule_id = int(run_row["schedule_id"])
        except Exception:
            schedule_id = None
    
    while True:
        pages_fetched += 1

        if max_pages > 0 and pages_fetched > max_pages:
            print(f"ingest_frontend_prices: reached max_pages={max_pages}, stopping")
            break

        # Progress log: current state + next step
        print(
            f"ingest_frontend_prices: progress: next_step=fetch_page "
            f"page={page}"
            f"{f'/{total_pages}' if total_pages else ''} "
            f"saved={total_inserted} distinct_nm_id={len(seen_nm_ids)} "
            f"failed_pages={failed_pages}"
        )

        # Fetch page with bounded page-level retries (WB can rate-limit/flake).
        # We keep it bounded and visible in stats_json so "running" is explainable.
        data = None
        last_meta: dict | None = None
        page_attempts = 6
        retry_count_429 = 0
        for page_attempt in range(1, page_attempts + 1):
            data = await client.fetch_brand_catalog_page(brand_id, page, base_url)
            last_meta = getattr(client, "last_request_meta", None)
            if data:
                break

            status_code = None
            try:
                status_code = int(last_meta.get("status_code")) if isinstance(last_meta, dict) and last_meta.get("status_code") is not None else None
            except Exception:
                status_code = None

            # Rate limit (429): apply exponential backoff with jitter (heartbeat-aware).
            if status_code == 429:
                retry_count_429 += 1
                sleep_s = compute_retry_sleep_seconds(retry_count_429)
                runtime_s = time.monotonic() - started_monotonic

                # Limits: stop gracefully (skipped rate_limited) instead of running forever.
                if (
                    (total_retry_wait_seconds + sleep_s) > settings.FRONTEND_PRICES_MAX_TOTAL_RETRY_WAIT_SECONDS
                    or runtime_s > settings.FRONTEND_PRICES_MAX_RUNTIME_SECONDS
                ):
                    if run_id is not None:
                        try:
                            from app.services.ingest import runs as runs_service

                            runs_service.mark_run_skipped(
                                int(run_id),
                                reason_code="rate_limited",
                                actor="frontend_prices",
                                reason_text="Exceeded retry wait/runtime limits",
                            )
                        except Exception:
                            pass

                    # Reschedule the linked schedule (if any) to back off rate limit pressure.
                    if schedule_id is not None:
                        try:
                            from datetime import timedelta

                            next_run_at = datetime.now(timezone.utc) + timedelta(
                                minutes=int(settings.FRONTEND_PRICES_RATE_LIMIT_BACKOFF_MINUTES)
                            )
                            with engine.begin() as conn:
                                conn.execute(
                                    text(
                                        """
                                        UPDATE ingest_schedules
                                        SET next_run_at = :next_run_at,
                                            updated_at = now()
                                        WHERE id = :id
                                        """
                                    ),
                                    {"id": schedule_id, "next_run_at": next_run_at},
                                )
                        except Exception:
                            pass

                    return {
                        "ok": True,
                        "domain": "frontend_prices",
                        "skipped": True,
                        "reason": "rate_limited",
                        "detail": "Exceeded retry wait/runtime limits",
                        "page": page,
                        "total_pages": total_pages,
                        "retry_count": retry_count_429,
                        "total_retry_wait": total_retry_wait_seconds,
                        "runtime_seconds": runtime_s,
                    }

                total_retry_wait_seconds += sleep_s
                print(
                    f"frontend_prices rate_limited retry={retry_count_429} sleep={sleep_s}s "
                    f"page={page}{f'/{total_pages}' if total_pages else ''}"
                )

                progress_payload = {
                    "ok": None,
                    "phase": "rate_limit_sleep",
                    "page": page,
                    "total_pages": total_pages,
                    "expected_total": expected_total,
                    "saved": total_inserted,
                    "distinct_nm_id": len(seen_nm_ids),
                    "failed_pages": failed_pages[-10:],
                    "last_request": last_meta,
                    "frontend_prices": {
                        "page": page,
                        "total_pages": total_pages,
                        "retry_count": retry_count_429,
                        "last_http_status": 429,
                        "sleep_seconds": sleep_s,
                        "total_retry_wait": total_retry_wait_seconds,
                        "runtime_seconds": int(runtime_s),
                    },
                }
                await sleep_with_heartbeat(
                    run_id=int(run_id) if run_id is not None else None,
                    total_seconds=float(sleep_s),
                    tick=10,
                    progress=progress_payload,
                )
                continue

            # Update progress with wait step
            sleep_s = min(10 * page_attempt, 60)  # 10,20,30,... capped 60
            progress_payload = {
                "ok": None,
                "phase": "retry_wait",
                "page": page,
                "page_attempt": page_attempt,
                "page_attempts": page_attempts,
                "sleep_s": sleep_s,
                "total_pages": total_pages,
                "expected_total": expected_total,
                "saved": total_inserted,
                "distinct_nm_id": len(seen_nm_ids),
                "failed_pages": failed_pages[-10:],
                "last_request": last_meta,
            }
            await sleep_with_heartbeat(
                run_id=int(run_id) if run_id is not None else None,
                total_seconds=float(sleep_s),
                tick=10,
                progress=progress_payload,
            )

        if not data:
            failed_pages.append(page)
            print(
                f"ingest_frontend_prices: page {page} - HTTP status: no response, "
                f"STOP REASON: failed to fetch page (failed_pages={failed_pages})"
            )
            # IMPORTANT: do not silently skip pages when total_pages is known,
            # otherwise we report success with incomplete dataset.
            return {
                "error": "incomplete_run_failed_to_fetch_page",
                "failed_pages": failed_pages,
                "total_pages": total_pages,
                "expected_total": expected_total,
                "distinct_nm_id": len(seen_nm_ids),
                "items_saved": total_inserted,
                "last_request": last_meta,
            }
        
        # Extract total pages and total count on first page if available
        if pages_fetched == 1 and total_pages is None:
            first_page_data = data
            total_pages = extract_total_pages(data)
            if total_pages:
                print(f"ingest_frontend_prices: detected total_pages={total_pages} from first page")
            
            # Extract expected_total (total products count)
            if isinstance(data, dict):
                _expected_total = data.get("total") or data.get("totalCount")
                if _expected_total:
                    try:
                        expected_total = int(_expected_total)
                        print(f"ingest_frontend_prices: detected expected_total={expected_total} from first page")
                    except (ValueError, TypeError):
                        expected_total = None
        
        # Extract products
        products = extract_products_from_response(data)
        products_count = len(products)

        # Update running progress in ingest_runs.stats_json for UI.
        # Keep it compact and safe (no secrets).
        if run_id is not None:
            try:
                from app.services.ingest import runs as runs_service

                runs_service.set_run_progress(
                    int(run_id),
                    {
                        "ok": None,
                        "phase": "fetch_page",
                        "page": page,
                        "total_pages": total_pages,
                        "expected_total": expected_total,
                        "saved": total_inserted,
                        "distinct_nm_id": len(seen_nm_ids),
                        "failed_pages": failed_pages[-10:],  # keep last few only
                    },
                )
            except Exception:
                # Progress updates should never break ingestion
                pass
        
        # Log page info with total/totalPages detection
        total_info = ""
        if isinstance(data, dict):
            total_val = data.get("total") or data.get("totalCount")
            total_pages_val = data.get("totalPages") or data.get("pages") or data.get("pageCount")
            if total_val:
                total_info = f", total={total_val}"
            if total_pages_val:
                total_info += f", totalPages={total_pages_val}"
        
        print(
            f"ingest_frontend_prices: page_result: status=200 "
            f"page={page}{f'/{total_pages}' if total_pages else ''} "
            f"products_count={products_count}, total_pages={total_pages if total_pages else 'unknown'}{total_info}"
        )
        
        # If we have total_pages, use it for pagination - DO NOT stop on empty products
        if total_pages:
            if page > total_pages:
                print(f"ingest_frontend_prices: page {page} > total_pages {total_pages}, stopping")
                break
            # Continue even if products_count == 0, because we know there should be more pages
        else:
            # If no total_pages, check for empty pages with retry
            if products_count == 0:
                empty_pages_count += 1
                if empty_pages_count >= 2:
                    # Log stop reason
                    response_preview = json.dumps(data, ensure_ascii=False)[:500] if data else "(empty)"
                    print(f"ingest_frontend_prices: page {page} - STOP REASON: {empty_pages_count} consecutive empty pages")
                    print(f"ingest_frontend_prices: page {page} - response preview (500 chars): {response_preview}")
                    break
                else:
                    # Retry once with backoff
                    print(f"ingest_frontend_prices: page {page} - empty, retrying once with backoff...")
                    await sleep_with_heartbeat(
                        run_id=int(run_id) if run_id is not None else None,
                        total_seconds=float(sleep_ms) / 1000.0 * 2.0,  # 2x backoff
                        tick=10,
                        progress={
                            "ok": None,
                            "phase": "empty_page_retry_wait",
                            "page": page,
                            "total_pages": total_pages,
                            "expected_total": expected_total,
                            "saved": total_inserted,
                            "distinct_nm_id": len(seen_nm_ids),
                            "failed_pages": failed_pages[-10:],
                            "last_request": last_meta,
                        },
                    )
                    data_retry = await client.fetch_brand_catalog_page(brand_id, page, base_url)
                    if data_retry:
                        products_retry = extract_products_from_response(data_retry)
                        products_count = len(products_retry)
                        if products_count > 0:
                            products = products_retry
                            empty_pages_count = 0
                            print(f"ingest_frontend_prices: page {page} - retry successful, products_count={products_count}")
                        else:
                            print(f"ingest_frontend_prices: page {page} - retry also empty, will stop if next page empty")
                    continue
            else:
                empty_pages_count = 0  # Reset counter on successful page
        
        # Process products even if empty (for logging), but skip insert if empty
        if not products:
            if total_pages:
                print(f"ingest_frontend_prices: page {page} - no products but total_pages={total_pages}, continuing to next page")
            # Sleep and continue to next page
            if sleep_ms > 0:
                await sleep_with_heartbeat(
                    run_id=int(run_id) if run_id is not None else None,
                    total_seconds=float(sleep_ms) / 1000.0,
                    tick=10,
                    progress={
                        "ok": None,
                        "phase": "between_pages_sleep",
                        "page": page,
                        "total_pages": total_pages,
                        "expected_total": expected_total,
                        "saved": total_inserted,
                        "distinct_nm_id": len(seen_nm_ids),
                        "failed_pages": failed_pages[-10:],
                    },
                )
            page += 1
            continue
        
        print(f"ingest_frontend_prices: page {page} - processing {products_count} products")
        total_products += products_count
        
        # Process products - DO NOT skip products without sizes/price
        rows: List[Dict[str, Any]] = []
        metrics_rows: List[Dict[str, Any]] = []
        snapshots_rows: List[Dict[str, Any]] = []
        skipped_no_nm_id = 0
        for product in products:
            nm_id = product.get("id") or product.get("nmId") or product.get("nm_id")
            if not nm_id:
                skipped_no_nm_id += 1
                continue
            try:
                nm_id_int = int(nm_id)
            except Exception:
                skipped_no_nm_id += 1
                continue

            # De-duplicate within a single run (WB catalog pages may overlap for popular sorting)
            if nm_id_int in seen_nm_ids:
                dup_in_run += 1
                continue
            seen_nm_ids.add(nm_id_int)
            
            vendor_code = product.get("supplierVendorCode") or product.get("vendorCode")
            name = product.get("name")
            
            # Extract prices from sizes[0] - but don't skip if sizes/price missing
            price_basic = None
            price_product = None
            sizes = product.get("sizes", [])
            if sizes and len(sizes) > 0:
                first_size = sizes[0]
                price_obj = first_size.get("price", {})
                
                # Prices are in kopecks, convert to rubles
                if isinstance(price_obj, dict):
                    basic_kopecks = price_obj.get("basic")
                    product_kopecks = price_obj.get("product")
                    if basic_kopecks is not None:
                        price_basic = Decimal(str(basic_kopecks)) / 100
                    if product_kopecks is not None:
                        price_product = Decimal(str(product_kopecks)) / 100
            
            # Sale percent
            sale_percent = product.get("sale")
            if sale_percent is not None:
                try:
                    sale_percent = int(sale_percent)
                except (ValueError, TypeError):
                    sale_percent = None
            
            # Calculate discount percent (only if we have both prices)
            discount_calc_percent = None
            if price_basic and price_basic > 0 and price_product:
                discount_calc = (1 - price_product / price_basic) * 100
                discount_calc_percent = int(round(discount_calc))
            
            # Insert row even if price_basic/price_product are None
            row = {
                "snapshot_at": run_at,
                "query_value": str(brand_id),
                "page": page,
                "nm_id": nm_id_int,
                "vendor_code": vendor_code,
                "name": name,
                "price_basic": float(price_basic) if price_basic else None,
                "price_product": float(price_product) if price_product else None,
                "sale_percent": sale_percent,
                "discount_calc_percent": discount_calc_percent,
                "raw": json.dumps(product, ensure_ascii=False)
            }
            rows.append(row)

            # Prepare current+history rows only if we have project context
            if project_id is not None:
                # Treat discount_calc_percent as SPP approximation for showcase prices.
                spp_percent_val: int | None = None
                if discount_calc_percent is not None:
                    try:
                        spp_percent_val = int(discount_calc_percent)
                    except Exception:
                        spp_percent_val = None

                metrics_rows.append(
                    {
                        "project_id": project_id,
                        "nm_id": nm_id_int,
                        "current_price_showcase": float(price_product) if price_product else None,
                        "current_spp_percent": spp_percent_val,
                    }
                )
                # snapshot_at bucket is per-run, per-project
                snapshot_at = compute_hour_bucket_utc(project_id=project_id, now_utc=run_started_at)
                snapshots_rows.append(
                    {
                        "project_id": project_id,
                        "nm_id": nm_id_int,
                        "price_showcase": float(price_product) if price_product else None,
                        "spp_percent": spp_percent_val,
                        "snapshot_at": snapshot_at,
                    }
                )
        
        if skipped_no_nm_id > 0:
            print(f"ingest_frontend_prices: page {page} - skipped {skipped_no_nm_id} products without nm_id")
        
        # Bulk insert
        if rows:
            with engine.begin() as conn:
                # 1) Append-only snapshots into frontend_catalog_price_snapshots
                conn.execute(insert_sql, rows)

                # 2) WB current + history + SPP events, only when we have project_id & run_id
                if project_id is not None and run_id is not None and metrics_rows:
                    # Load old SPP for keys in a single query
                    nm_ids = sorted({m["nm_id"] for m in metrics_rows})
                    old_spp_by_nm: Dict[int, int | None] = {}
                    if nm_ids:
                        old_sql = text(
                            """
                            SELECT nm_id, current_spp_percent
                            FROM wb_current_metrics
                            WHERE project_id = :project_id
                              AND nm_id = ANY(:nm_ids)
                            """
                        )
                        rows_old = conn.execute(
                            old_sql, {"project_id": project_id, "nm_ids": nm_ids}
                        ).mappings().all()
                        for r in rows_old:
                            old_spp_by_nm[int(r["nm_id"])] = r["current_spp_percent"]

                    # Build SPP events where IS DISTINCT FROM
                    spp_events: List[Dict[str, Any]] = []
                    for m in metrics_rows:
                        nm = int(m["nm_id"])
                        new_spp = m.get("current_spp_percent")
                        old_spp = old_spp_by_nm.get(nm)
                        if old_spp is None and new_spp is None:
                            continue
                        if old_spp == new_spp:
                            continue
                        spp_events.append(
                            {
                                "project_id": project_id,
                                "nm_id": nm,
                                "prev_spp_percent": old_spp,
                                "spp_percent": new_spp,
                                "changed_at": run_started_at,
                                "ingest_run_id": run_id,
                            }
                        )

                    if spp_events:
                        spp_sql = text(
                            """
                            INSERT INTO wb_spp_events (
                                project_id,
                                nm_id,
                                prev_spp_percent,
                                spp_percent,
                                changed_at,
                                ingest_run_id
                            )
                            VALUES (
                                :project_id,
                                :nm_id,
                                :prev_spp_percent,
                                :spp_percent,
                                :changed_at,
                                :ingest_run_id
                            )
                            """
                        )
                        conn.execute(spp_sql, spp_events)
                        spp_events_inserted_total += len(spp_events)

                    # Upsert current metrics (price_showcase + SPP) in same transaction
                    current_upserts = upsert_wb_current_metrics_on_conn(
                        conn=conn,
                        rows=metrics_rows,
                        run_id=run_id,
                    )
                    current_upserts_total += current_upserts

                    # Hourly showcase snapshots with ON CONFLICT DO NOTHING
                    if snapshots_rows:
                        snapshots_sql = text(
                            """
                            INSERT INTO wb_showcase_price_snapshots (
                                project_id,
                                nm_id,
                                price_showcase,
                                spp_percent,
                                snapshot_at,
                                ingest_run_id
                            )
                            VALUES (
                                :project_id,
                                :nm_id,
                                :price_showcase,
                                :spp_percent,
                                :snapshot_at,
                                :ingest_run_id
                            )
                            ON CONFLICT (project_id, nm_id, snapshot_at)
                            DO NOTHING
                            """
                        )
                        # add ingest_run_id to each row
                        snapshots_with_run = [
                            {
                                **row_snap,
                                "ingest_run_id": run_id,
                            }
                            for row_snap in snapshots_rows
                        ]
                        conn.execute(snapshots_sql, snapshots_with_run)
                        # We count attempted inserts as snapshots_inserted semantics
                        showcase_snapshots_inserted_total += len(snapshots_with_run)

            total_inserted += len(rows)
            print(
                f"ingest_frontend_prices: inserted {len(rows)} records from page {page} "
                f"(total_saved={total_inserted}, distinct_nm_id={len(seen_nm_ids)}, dup_in_run={dup_in_run})"
            )

        # After DB writes: update running progress with real counters.
        if run_id is not None:
            try:
                from app.services.ingest import runs as runs_service
                runs_service.set_run_progress(
                    int(run_id),
                    {
                        "ok": None,
                        "phase": "processed_page",
                        "page": page,
                        "total_pages": total_pages,
                        "expected_total": expected_total,
                        "saved": total_inserted,
                        "distinct_nm_id": len(seen_nm_ids),
                        "failed_pages": failed_pages[-10:],
                    },
                )
            except Exception:
                pass
        
        # Sleep between pages
        if sleep_ms > 0:
            await sleep_with_heartbeat(
                run_id=int(run_id) if run_id is not None else None,
                total_seconds=float(sleep_ms) / 1000.0,
                tick=10,
                progress={
                    "ok": None,
                    "phase": "between_pages_sleep",
                    "page": page,
                    "total_pages": total_pages,
                    "expected_total": expected_total,
                    "saved": total_inserted,
                    "distinct_nm_id": len(seen_nm_ids),
                    "failed_pages": failed_pages[-10:],
                },
            )
        
        # Move to next page
        page += 1
        
        # If we have total_pages and reached it, stop
        if total_pages and page > total_pages:
            print(f"ingest_frontend_prices: reached total_pages={total_pages}, stopping")
            break
    
    print(
        f"ingest_frontend_prices: finished, run_at={run_at_iso}, pages_fetched={pages_fetched}, "
        f"total_pages={total_pages}, items_fetched={total_products}, items_saved={total_inserted}, "
        f"distinct_nm_id={len(seen_nm_ids)}, dup_in_run={dup_in_run}, "
        f"current_upserts_total={current_upserts_total}, "
        f"showcase_snapshots_inserted_total={showcase_snapshots_inserted_total}, "
        f"spp_events_inserted_total={spp_events_inserted_total}"
    )

    # Completeness check: if WB says total=N but we saved much less, treat as failure.
    coverage = None
    if expected_total and expected_total > 0:
        coverage = float(len(seen_nm_ids)) / float(expected_total)
        if coverage < 0.95:
            return {
                "error": "incomplete_run_low_coverage",
                "expected_total": expected_total,
                "distinct_nm_id": len(seen_nm_ids),
                "coverage": coverage,
                "total_pages": total_pages,
                "pages_processed": pages_fetched,
                "items_saved": total_inserted,
                "failed_pages": failed_pages,
            }
    
    return {
        "run_at": run_at_iso,
        "pages_processed": pages_fetched,
        "total_pages": total_pages,
        "expected_total": expected_total,
        "coverage": coverage,
        "failed_pages": failed_pages,
        "items_fetched": total_products,
        "items_saved": total_inserted,
        "distinct_nm_id": len(seen_nm_ids),
        "dup_in_run": dup_in_run,
        "current_upserts_total": current_upserts_total,
        "showcase_snapshots_inserted_total": showcase_snapshots_inserted_total,
        "spp_events_inserted_total": spp_events_inserted_total,
    }


@router.post("/frontend-prices/brand")
async def start_ingest_frontend_brand_prices(
    request: FrontendBrandPricesRequest = Body(...),
    background_tasks: BackgroundTasks = None
):
    """Start ingestion of frontend catalog prices from WB public API."""
    # Run in background
    result = await ingest_frontend_brand_prices(
        brand_id=request.brand_id,
        base_url=request.base_url,
        max_pages=request.max_pages,
        sleep_ms=request.sleep_ms
    )
    
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    
    return {
        "status": "completed",
        "message": "Frontend prices ingestion completed",
        **result
    }

