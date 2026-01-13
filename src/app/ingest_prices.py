"""Ingestion endpoint for prices."""

import asyncio
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def round_to_49_99(value: Decimal) -> Decimal:
    """Round price to nearest .49 or .99."""
    v = int(value)
    base = (v // 100) * 100
    candidates = [base + 49, base + 99, base + 149, base + 199]
    best = min(candidates, key=lambda x: abs(x - v))
    return Decimal(best)


async def ingest_prices() -> None:
    """Fetch and insert price snapshots from WB Prices and Discounts API.
    
    Uses GET /api/v2/list/goods/filter with pagination via offset.
    Iterates until listGoods becomes empty.
    """
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_prices: skipped (MOCK mode or no token)")
        return

    # Check if raw column exists in price_snapshots table
    check_raw_sql = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'price_snapshots' AND column_name = 'raw'
    """)
    
    has_raw_column = False
    with engine.connect() as conn:
        result = conn.execute(check_raw_sql).scalar_one_or_none()
        has_raw_column = result is not None
    
    if not has_raw_column:
        print("ingest_prices: WARNING - raw column not found in price_snapshots, will not save raw JSON")
    
    # Prepare insert SQL
    if has_raw_column:
        insert_sql = text("""
            INSERT INTO price_snapshots (nm_id, wb_price, wb_discount, spp, customer_price, rrc, raw)
            VALUES (:nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc, CAST(:raw AS jsonb))
        """)
    else:
        insert_sql = text("""
            INSERT INTO price_snapshots (nm_id, wb_price, wb_discount, spp, customer_price, rrc)
            VALUES (:nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc)
        """)

    client = WBClient()
    limit = 1000
    offset = 0
    total_inserted = 0
    page_count = 0
    max_pages = 1000  # Safety limit
    
    print(f"ingest_prices: starting pagination, limit={limit}")
    
    while page_count < max_pages:
        page_count += 1
        print(f"ingest_prices: fetching page {page_count}, offset={offset}")
        
        # Fetch prices from WB API
        list_goods = await client.fetch_prices(limit=limit, offset=offset)
        
        if not list_goods:
            print(f"ingest_prices: no goods returned at offset {offset}, pagination complete")
            break
        
        print(f"ingest_prices: received {len(list_goods)} goods from WB API")
        
        # Process each good
        rows: List[Dict[str, Any]] = []
        for good in list_goods:
            nm_id = good.get("nmID") or good.get("nm_id")
            if not nm_id:
                print(f"ingest_prices: skipping good without nmID: {good.get('vendorCode', 'unknown')}")
                continue
            
            # Extract discount from good level
            discount = good.get("discount") or good.get("clubDiscount") or 0
            
            # Extract prices from sizes array
            sizes = good.get("sizes", [])
            if not sizes:
                print(f"ingest_prices: good {nm_id} has no sizes, skipping")
                continue
            
            # Get minimum price from all sizes
            prices = []
            discounted_prices = []
            for size in sizes:
                price = size.get("price")
                discounted_price = size.get("discountedPrice")
                if price is not None:
                    prices.append(Decimal(str(price)))
                if discounted_price is not None:
                    discounted_prices.append(Decimal(str(discounted_price)))
            
            if not prices:
                print(f"ingest_prices: good {nm_id} has no prices in sizes, skipping")
                continue
            
            # Use minimum price as base price
            min_price = min(prices)
            min_discounted_price = min(discounted_prices) if discounted_prices else min_price
            
            # Calculate fields
            wb_price = min_price
            wb_discount = Decimal(str(discount))
            spp = Decimal("0")
            
            # Calculate customer price (price after discount)
            customer_price = min_discounted_price if discounted_prices else (wb_price * (Decimal(1) - wb_discount / Decimal(100)))
            customer_price = customer_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rrc = round_to_49_99(wb_price)

            row = {
                "nm_id": int(nm_id),
                "wb_price": float(wb_price),
                "wb_discount": float(wb_discount),
                "spp": float(spp),
                "customer_price": float(customer_price),
                "rrc": float(rrc),
            }
            
            # Add raw data if column exists
            if has_raw_column:
                import json
                row["raw"] = json.dumps(good, ensure_ascii=False)
            
            rows.append(row)
        
        # Insert batch
        if rows:
            with engine.begin() as conn:
                conn.execute(insert_sql, rows)
            total_inserted += len(rows)
            print(f"ingest_prices: inserted {len(rows)} price snapshots (total: {total_inserted})")
        else:
            print(f"ingest_prices: no rows to insert from page {page_count}")
        
        # Move to next page
        offset += limit
        
        # If we got fewer items than limit, we're done
        if len(list_goods) < limit:
            print(f"ingest_prices: received {len(list_goods)} < {limit} items, pagination complete")
            break
    
    print(f"ingest_prices: finished, total pages={page_count}, total inserted={total_inserted}")


@router.get("/prices")
async def get_prices_info():
    """Get information about prices ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    return {
        "endpoint": "POST /api/v1/ingest/prices",
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK",
    }


@router.post("/prices")
async def start_ingest_prices(background_tasks: BackgroundTasks):
    """Start ingestion of prices from Wildberries API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Prices ingestion skipped (MOCK mode or no token configured)",
        }

    background_tasks.add_task(ingest_prices)
    return {"status": "started", "message": "Prices ingestion started in background"}

