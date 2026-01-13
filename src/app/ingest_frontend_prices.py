"""Ingestion endpoint for frontend catalog prices from WB public API."""

import asyncio
import json
import os
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, BackgroundTasks, Body
from pydantic import BaseModel
from sqlalchemy import text

from app.db import engine
from app.wb.catalog_client import CatalogClient

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


class FrontendBrandPricesRequest(BaseModel):
    brand_id: int
    base_url: Optional[str] = None  # If not provided, will be read from app_settings
    max_pages: int = 0  # 0 or null = until empty
    sleep_ms: int = 800


def extract_products_from_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract products array from various response formats (universal, like pickProducts in Apps Script).
    
    Tries:
    - data.listGoods (catalog.wb.ru format)
    - data.data.listGoods
    - data.products
    - data.data.products
    - data.data.catalog.products
    - data.catalog.products
    - products (root level)
    """
    if isinstance(data, dict):
        # Try data.listGoods (catalog.wb.ru format)
        if "listGoods" in data:
            products = data["listGoods"]
            if isinstance(products, list):
                print(f"extract_products_from_response: found {len(products)} products in data.listGoods")
                return products
        
        # Try data.data.listGoods
        if "data" in data and isinstance(data["data"], dict):
            if "listGoods" in data["data"]:
                products = data["data"]["listGoods"]
                if isinstance(products, list):
                    print(f"extract_products_from_response: found {len(products)} products in data.data.listGoods")
                    return products
            
            # Try data.data.products
            if "products" in data["data"]:
                products = data["data"]["products"]
                if isinstance(products, list):
                    print(f"extract_products_from_response: found {len(products)} products in data.data.products")
                    return products
            
            # Try data.data.catalog.products
            if "catalog" in data["data"] and isinstance(data["data"]["catalog"], dict):
                if "products" in data["data"]["catalog"]:
                    products = data["data"]["catalog"]["products"]
                    if isinstance(products, list):
                        print(f"extract_products_from_response: found {len(products)} products in data.data.catalog.products")
                        return products
        
        # Try data.products
        if "products" in data:
            products = data["products"]
            if isinstance(products, list):
                print(f"extract_products_from_response: found {len(products)} products in data.products")
                return products
        
        # Try data.catalog.products
        if "catalog" in data and isinstance(data["catalog"], dict):
            if "products" in data["catalog"]:
                products = data["catalog"]["products"]
                if isinstance(products, list):
                    print(f"extract_products_from_response: found {len(products)} products in data.catalog.products")
                    return products
        
        # Log structure for debugging
        print(f"extract_products_from_response: no products found, data keys: {list(data.keys())}")
        if "data" in data and isinstance(data["data"], dict):
            print(f"extract_products_from_response: data.data keys: {list(data['data'].keys())}")
    
    elif isinstance(data, list):
        # Root level is list
        print(f"extract_products_from_response: root level is list with {len(data)} items")
        return data
    
    print("extract_products_from_response: no products found, returning empty list")
    return []


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
    sleep_ms: int = 800
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
    
    print(f"ingest_frontend_prices: starting, brand_id={brand_id}, start_page={start_page}, max_pages={max_pages}, sleep_ms={sleep_ms}")
    
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
        (now(), 'catalog_wb', 'brand', :query_value, :page, :nm_id, :vendor_code, :name,
         :price_basic, :price_product, :sale_percent, :discount_calc_percent, CAST(:raw AS jsonb))
    """)
    
    total_inserted = 0
    total_products = 0
    pages_fetched = 0
    page = start_page
    
    while True:
        pages_fetched += 1
        
        if max_pages > 0 and pages_fetched > max_pages:
            print(f"ingest_frontend_prices: reached max_pages={max_pages}, stopping")
            break
        
        print(f"ingest_frontend_prices: fetching page {page}")
        
        # Fetch page
        data = await client.fetch_brand_catalog_page(brand_id, page, base_url)
        
        if not data:
            print(f"ingest_frontend_prices: no data returned for page {page}, stopping")
            break
        
        # Extract products
        products = extract_products_from_response(data)
        
        if not products:
            print(f"ingest_frontend_prices: no products found in response for page {page}, stopping")
            break
        
        print(f"ingest_frontend_prices: found {len(products)} products on page {page}")
        total_products += len(products)
        
        # Process products
        rows: List[Dict[str, Any]] = []
        for product in products:
            nm_id = product.get("id") or product.get("nmId") or product.get("nm_id")
            if not nm_id:
                print(f"ingest_frontend_prices: skipping product without nm_id: {product.get('name', 'unknown')}")
                continue
            
            vendor_code = product.get("supplierVendorCode") or product.get("vendorCode")
            name = product.get("name")
            
            # Extract prices from sizes[0]
            sizes = product.get("sizes", [])
            if not sizes:
                print(f"ingest_frontend_prices: product {nm_id} has no sizes, skipping")
                continue
            
            first_size = sizes[0]
            price_obj = first_size.get("price", {})
            
            # Prices are in kopecks, convert to rubles
            price_basic = None
            price_product = None
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
            
            # Calculate discount percent
            discount_calc_percent = None
            if price_basic and price_basic > 0 and price_product:
                discount_calc = (1 - price_product / price_basic) * 100
                discount_calc_percent = int(round(discount_calc))
            
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
                "raw": json.dumps(product, ensure_ascii=False)
            }
            rows.append(row)
        
        # Bulk insert
        if rows:
            with engine.begin() as conn:
                conn.execute(insert_sql, rows)
            total_inserted += len(rows)
            print(f"ingest_frontend_prices: inserted {len(rows)} records from page {page} (total: {total_inserted})")
        
        # Sleep between pages
        if sleep_ms > 0:
            await asyncio.sleep(sleep_ms / 1000.0)
        
        # Move to next page
        page += 1
    
    print(f"ingest_frontend_prices: finished, pages_fetched={pages_fetched}, total_products={total_products}, total_inserted={total_inserted}")
    
    return {
        "pages_fetched": pages_fetched,
        "total_products": total_products,
        "inserted": total_inserted
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

