"""Celery task for syncing frontend catalog prices."""

import asyncio
import json
from decimal import Decimal
from typing import Any, Dict, Optional

import redis
from sqlalchemy import text

from app import settings
from app.celery_app import celery_app
from app.db import engine
from app.wb.catalog_client import CatalogClient


def get_redis_client() -> redis.Redis:
    """Get Redis client for distributed locks."""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=int(settings.REDIS_PORT),
        db=0,
        decode_responses=False,  # For SET NX EX
    )


def acquire_lock(lock_key: str, ttl_seconds: int = 3600) -> bool:
    """Acquire distributed lock in Redis.
    
    Returns True if lock acquired, False if already locked.
    """
    redis_client = get_redis_client()
    try:
        # SET key value NX EX ttl - atomic operation
        result = redis_client.set(lock_key, b"1", nx=True, ex=ttl_seconds)
        return result is True
    except Exception as e:
        print(f"acquire_lock: error acquiring lock {lock_key}: {e}")
        return False


def release_lock(lock_key: str) -> None:
    """Release distributed lock."""
    redis_client = get_redis_client()
    try:
        redis_client.delete(lock_key)
    except Exception as e:
        print(f"release_lock: error releasing lock {lock_key}: {e}")


def get_setting(key: str, field: str, default: Any = None) -> Optional[Any]:
    """Get a JSON setting from app_settings table.

    NOTE: legacy helper. Prefer using dedicated settings keys like:
      - frontend_prices.brand_base_url (value.url)
      - frontend_prices.sleep_ms (value.value)
    This function is kept for backward compatibility.
    """
    sql = text(
        """
        SELECT value ->> :field AS value
        FROM app_settings
        WHERE key = :key
        """
    )

    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"key": key, "field": field}).scalar_one_or_none()
            return result if result is not None and result != "" else default
    except Exception as e:
        print(f"get_setting: error getting {key}.{field}: {e}")
        return default


@celery_app.task(name="app.tasks.frontend_prices.sync_frontend_prices_brand")
def sync_frontend_prices_brand() -> Dict[str, Any]:
    """Periodic task to sync frontend catalog prices.
    
    Uses settings from app_settings:
    - frontend_prices.brand_id (int)
    - frontend_prices.brand_base_url (str)
    - frontend_prices.sleep_ms (int, default 800)
    
    Returns dict with status and results.
    """
    lock_key = "lock:frontend_prices"
    lock_ttl = 3600  # 1 hour
    
    # Try to acquire lock
    if not acquire_lock(lock_key, lock_ttl):
        print("sync_frontend_prices_brand: lock already acquired, skipping")
        return {
            "status": "skipped",
            "reason": "lock_already_acquired",
        }
    
    try:
        # Get global settings (brand_base_url + sleep_ms)
        base_url_sql = text(
            """
            SELECT value->>'url' AS url
            FROM app_settings
            WHERE key = 'frontend_prices.brand_base_url'
            """
        )
        sleep_ms_sql = text(
            """
            SELECT value->>'value' AS value
            FROM app_settings
            WHERE key = 'frontend_prices.sleep_ms'
            """
        )

        with engine.connect() as conn:
            base_url = conn.execute(base_url_sql).scalar_one_or_none()
            sleep_ms_str = conn.execute(sleep_ms_sql).scalar_one_or_none()

        if not base_url:
            print("sync_frontend_prices_brand: brand_base_url not configured in app_settings (frontend_prices.brand_base_url)")
            return {"status": "error", "reason": "brand_base_url_not_configured"}

        # Global brand_base_url is a template: must contain {brand_id}
        if "{brand_id}" not in base_url:
            print("sync_frontend_prices_brand: brand_base_url must contain placeholder {brand_id}")
            return {
                "status": "error",
                "reason": "brand_base_url_must_contain_placeholder",
                "error": "frontend_prices.brand_base_url must contain placeholder {brand_id}. Example: https://catalog.wb.ru/brands/v4/catalog?brand={brand_id}&page=1",
            }

        try:
            sleep_ms = int(sleep_ms_str)
        except (ValueError, TypeError):
            sleep_ms = 800
            print(f"sync_frontend_prices_brand: invalid sleep_ms, using default 800")

        # For periodic job: iterate all enabled WB project brand_ids
        brand_ids_sql = text(
            """
            SELECT DISTINCT pm.settings_json->>'brand_id' AS brand_id
            FROM project_marketplaces pm
            JOIN marketplaces m ON m.id = pm.marketplace_id
            WHERE m.code = 'wildberries'
              AND pm.is_enabled = true
              AND pm.settings_json ? 'brand_id'
              AND (pm.settings_json->>'brand_id') IS NOT NULL
              AND (pm.settings_json->>'brand_id') != ''
            """
        )
        with engine.connect() as conn:
            brand_id_rows = conn.execute(brand_ids_sql).all()

        brand_ids: list[int] = []
        for (bid,) in brand_id_rows:
            try:
                brand_ids.append(int(bid))
            except Exception:
                continue

        if not brand_ids:
            print("sync_frontend_prices_brand: no enabled WB projects with settings_json.brand_id; skipping")
            return {"status": "skipped", "reason": "no_brand_ids"}

        from app.ingest_frontend_prices import resolve_base_url

        print(f"sync_frontend_prices_brand: starting for {len(brand_ids)} brand_id(s), sleep_ms={sleep_ms}")

        results: dict[str, Any] = {"per_brand": {}}
        for bid in brand_ids:
            resolved_base_url = resolve_base_url(base_url, bid)
            r = asyncio.run(
                ingest_frontend_brand_prices_task(
                    brand_id=bid,
                    base_url=resolved_base_url,
                    max_pages=0,
                    sleep_ms=sleep_ms,
                )
            )
            results["per_brand"][str(bid)] = r

        return {"status": "completed", **results}
    
    except Exception as e:
        print(f"sync_frontend_prices_brand: error: {type(e).__name__}: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
    
    finally:
        # Always release lock
        release_lock(lock_key)


async def ingest_frontend_brand_prices_task(
    brand_id: int,
    base_url: str,
    max_pages: int = 0,
    sleep_ms: int = 800,
) -> Dict[str, Any]:
    """Async function to ingest frontend prices (reused from ingest_frontend_prices.py)."""
    from app.ingest_frontend_prices import (
        extract_page_from_url,
        extract_products_from_response,
        extract_total_pages,
    )
    
    start_page = extract_page_from_url(base_url)
    
    print(f"ingest_frontend_brand_prices_task: starting, brand_id={brand_id}, start_page={start_page}, max_pages={max_pages}, sleep_ms={sleep_ms}")
    
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
        print("ingest_frontend_brand_prices_task: ERROR - table frontend_catalog_price_snapshots does not exist")
        return {"error": "Table frontend_catalog_price_snapshots does not exist. Run migrations."}
    
    # Prepare insert SQL
    insert_sql = text("""
        INSERT INTO frontend_catalog_price_snapshots 
        (snapshot_at, source, query_type, query_value, page, nm_id, vendor_code, name, 
         price_basic, price_product, sale_percent, discount_calc_percent, raw)
        VALUES 
        (now(), 'catalog_wb', 'brand', :query_value, :page, :nm_id, :vendor_code, :name,
         :price_basic, :price_product, :sale_percent, :discount_calc_percent, CAST(:raw AS jsonb))
    """)
    
    total_inserted = 0
    total_products = 0
    pages_fetched = 0
    page = start_page
    total_pages: Optional[int] = None
    empty_pages_count = 0
    
    while True:
        pages_fetched += 1
        
        if max_pages > 0 and pages_fetched > max_pages:
            print(f"ingest_frontend_brand_prices_task: reached max_pages={max_pages}, stopping")
            break
        
        print(f"ingest_frontend_brand_prices_task: fetching page {page}")
        
        # Fetch page
        data = await client.fetch_brand_catalog_page(brand_id, page, base_url)
        
        if not data:
            print(f"ingest_frontend_brand_prices_task: page {page} - HTTP status: no response, stopping")
            break
        
        # Extract total pages and total count on first page if available
        if pages_fetched == 1 and total_pages is None:
            first_page_data = data
            total_pages = extract_total_pages(data)
            if total_pages:
                print(f"ingest_frontend_brand_prices_task: detected total_pages={total_pages} from first page")
            
            # Extract expected_total (total products count)
            if isinstance(data, dict):
                expected_total = data.get("total") or data.get("totalCount")
                if expected_total:
                    try:
                        expected_total = int(expected_total)
                        print(f"ingest_frontend_brand_prices_task: detected expected_total={expected_total} from first page")
                    except (ValueError, TypeError):
                        expected_total = None
        
        # Extract products
        products = extract_products_from_response(data)
        products_count = len(products)
        
        print(f"ingest_frontend_brand_prices_task: page {page} - products_count={products_count}, total_pages={total_pages if total_pages else 'unknown'}")
        
        # If we have total_pages, use it for pagination
        if total_pages:
            if page > total_pages:
                print(f"ingest_frontend_brand_prices_task: page {page} > total_pages {total_pages}, stopping")
                break
        else:
            # If no total_pages, check for empty pages with retry
            if products_count == 0:
                empty_pages_count += 1
                if empty_pages_count >= 2:
                    response_preview = json.dumps(data, ensure_ascii=False)[:500] if data else "(empty)"
                    print(f"ingest_frontend_brand_prices_task: page {page} - stop reason: {empty_pages_count} consecutive empty pages")
                    print(f"ingest_frontend_brand_prices_task: page {page} - response preview (500 chars): {response_preview}")
                    break
                else:
                    # Retry once
                    print(f"ingest_frontend_brand_prices_task: page {page} - empty, retrying once...")
                    await asyncio.sleep(sleep_ms / 1000.0)
                    data_retry = await client.fetch_brand_catalog_page(brand_id, page, base_url)
                    if data_retry:
                        products_retry = extract_products_from_response(data_retry)
                        products_count = len(products_retry)
                        if products_count > 0:
                            products = products_retry
                            empty_pages_count = 0
                            print(f"ingest_frontend_brand_prices_task: page {page} - retry successful, products_count={products_count}")
                        else:
                            print(f"ingest_frontend_brand_prices_task: page {page} - retry also empty, will stop if next page empty")
                    continue
            else:
                empty_pages_count = 0
        
        if not products:
            if total_pages:
                print(f"ingest_frontend_brand_prices_task: page {page} - no products but total_pages={total_pages}, continuing")
            continue
        
        print(f"ingest_frontend_brand_prices_task: page {page} - processing {products_count} products")
        total_products += products_count
        
        # Process products
        rows: list[Dict[str, Any]] = []
        skipped_no_nm_id = 0
        for product in products:
            nm_id = product.get("id") or product.get("nmId") or product.get("nm_id")
            if not nm_id:
                skipped_no_nm_id += 1
                continue
            
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
            # If no sizes, price_basic and price_product remain None - still insert row
            
            # Sale percent
            sale_percent = product.get("sale")
            if sale_percent is not None:
                try:
                    sale_percent = int(sale_percent)
                except (ValueError, TypeError):
                    sale_percent = None
            
            # Calculate discount percent
            discount_calc_percent = None
            if price_basic and price_basic > 0 and price_product:
                discount_calc = (1 - price_product / price_basic) * 100
                discount_calc_percent = int(round(discount_calc))
            
            # Insert row even if price_basic/price_product are None
            row = {
                "query_value": str(brand_id),
                "page": page,
                "nm_id": int(nm_id),
                "vendor_code": vendor_code,
                "name": name,
                "price_basic": float(price_basic) if price_basic else None,
                "price_product": float(price_product) if price_product else None,
                "sale_percent": sale_percent,
                "discount_calc_percent": discount_calc_percent,
                "raw": json.dumps(product, ensure_ascii=False),
            }
            rows.append(row)
        
        if skipped_no_nm_id > 0:
            print(f"ingest_frontend_brand_prices_task: page {page} - skipped {skipped_no_nm_id} products without nm_id")
        
        # Bulk insert
        if rows:
            with engine.begin() as conn:
                conn.execute(insert_sql, rows)
            total_inserted += len(rows)
            print(f"ingest_frontend_brand_prices_task: inserted {len(rows)} records from page {page} (total: {total_inserted})")
        
        # Sleep between pages
        if sleep_ms > 0:
            await asyncio.sleep(sleep_ms / 1000.0)
        
        # Move to next page
        page += 1
        
        # If we have total_pages and reached it, stop
        if total_pages is not None and page > total_pages:
            print(f"ingest_frontend_brand_prices_task: reached total_pages={total_pages}, stopping")
            break
    
    # Check completeness
    run_started_at_sql = text("""
        SELECT MIN(snapshot_at) AS run_start
        FROM frontend_catalog_price_snapshots
        WHERE query_value = :query_value
        AND snapshot_at >= NOW() - INTERVAL '10 minutes'
    """)
    
    run_started_at = None
    uniq_nm_id = 0
    with engine.connect() as conn:
        result = conn.execute(run_started_at_sql, {"query_value": str(brand_id)}).scalar_one_or_none()
        if result:
            run_started_at = result
        
        # Count unique nm_id for this run
        if run_started_at:
            uniq_sql = text("""
                SELECT COUNT(DISTINCT nm_id) AS cnt
                FROM frontend_catalog_price_snapshots
                WHERE query_value = :query_value
                AND snapshot_at >= :run_start
            """)
            uniq_result = conn.execute(uniq_sql, {"query_value": str(brand_id), "run_start": run_started_at}).scalar_one_or_none()
            if uniq_result:
                uniq_nm_id = uniq_result
    
    # Completeness check
    expected_total = None
    if first_page_data and isinstance(first_page_data, dict):
        expected_total = first_page_data.get("total") or first_page_data.get("totalCount")
        if expected_total:
            try:
                expected_total = int(expected_total)
            except (ValueError, TypeError):
                expected_total = None
    
    print(f"ingest_frontend_brand_prices_task: COMPLETENESS CHECK - expected_total={expected_total}, uniq_nm_id={uniq_nm_id}, pages_fetched={pages_fetched}, total_pages={total_pages}")
    if expected_total and uniq_nm_id < expected_total:
        coverage_percent = (uniq_nm_id / expected_total) * 100
        print(f"ingest_frontend_brand_prices_task: WARNING - coverage={coverage_percent:.1f}% ({uniq_nm_id}/{expected_total})")
        if coverage_percent < 80:
            print(f"ingest_frontend_brand_prices_task: WARNING - coverage is less than 80%, ingestion may be incomplete")
            if pages_fetched < total_pages if total_pages else True:
                print(f"ingest_frontend_brand_prices_task: WARNING - stopped at page {page}, but total_pages={total_pages}")
    elif expected_total and uniq_nm_id >= expected_total:
        print(f"ingest_frontend_brand_prices_task: SUCCESS - coverage=100% ({uniq_nm_id}/{expected_total})")
    
    print(f"ingest_frontend_brand_prices_task: finished, pages_fetched={pages_fetched}, total_pages={total_pages}, total_products={total_products}, total_inserted={total_inserted}, uniq_nm_id={uniq_nm_id}, expected_total={expected_total}")
    
    return {
        "pages_fetched": pages_fetched,
        "total_products": total_products,
        "inserted": total_inserted,
        "uniq_nm_id": uniq_nm_id,
        "expected_total": expected_total,
    }

