"""Ingestion endpoint for prices."""

import asyncio
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

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


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


async def ingest_prices() -> None:
    """Fetch and insert price snapshots from WB API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_prices: skipped (MOCK mode or no token)")
        return

    # Get all nm_ids from products
    sql = text("SELECT DISTINCT nm_id FROM products ORDER BY nm_id")
    with engine.connect() as conn:
        result = conn.execute(sql).mappings().all()
        nm_ids = [int(row["nm_id"]) for row in result if row.get("nm_id") is not None]

    if not nm_ids:
        print("ingest_prices: no products found, skipping")
        return

    print(f"ingest_prices: found {len(nm_ids)} products")

    client = WBClient()
    
    # Fetch prices from WB API
    prices_data = await client.get_prices(nm_ids)
    
    if not prices_data:
        print("ingest_prices: no prices data received from WB API")
        return

    print(f"ingest_prices: received prices for {len(prices_data)} products")

    # Prepare rows for insertion
    # Проверяем, есть ли колонка raw в таблице
    check_raw_sql = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'price_snapshots' AND column_name = 'raw'
    """)
    has_raw_column = False
    with engine.connect() as conn:
        result = conn.execute(check_raw_sql).scalar_one_or_none()
        has_raw_column = result is not None
    
    if has_raw_column:
        insert_sql = text("""
            INSERT INTO price_snapshots (nm_id, wb_price, wb_discount, spp, customer_price, rrc, raw)
            VALUES (:nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc, :raw)
        """)
    else:
        insert_sql = text("""
            INSERT INTO price_snapshots (nm_id, wb_price, wb_discount, spp, customer_price, rrc)
            VALUES (:nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc)
        """)

    rows: List[Dict[str, Any]] = []
    for nm_id in nm_ids:
        price_info = prices_data.get(nm_id, {})
        if not price_info:
            print(f"ingest_prices: no price data for nm_id={nm_id}, skipping")
            continue

        # Извлекаем данные из ответа WB
        raw_product = price_info.get("raw", {})
        wb_price = Decimal(str(price_info.get("price", 0)))
        wb_discount = Decimal(str(price_info.get("discount", 0)))
        
        if wb_price == 0:
            print(f"ingest_prices: zero price for nm_id={nm_id}, skipping")
            continue

        spp = Decimal("0")
        customer_price = (wb_price * (Decimal(1) - wb_discount / Decimal(100))) * (
            Decimal(1) - spp / Decimal(100)
        )
        customer_price = customer_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rrc = round_to_49_99(wb_price)

        row_data = {
            "nm_id": int(nm_id),
            "wb_price": float(wb_price),
            "wb_discount": float(wb_discount),
            "spp": float(spp),
            "customer_price": float(customer_price),
            "rrc": float(rrc),
        }
        if has_raw_column:
            row_data["raw"] = _serialize_json_field(raw_product if raw_product else price_info)
        rows.append(row_data)

    if rows:
        with engine.begin() as conn:
            conn.execute(insert_sql, rows)
        print(f"ingest_prices: inserted {len(rows)} price snapshots")
    else:
        print("ingest_prices: no rows to insert")


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

