"""Ingestion endpoints for warehouses and stock balances."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Query, Path, Depends
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient
from app import db_products
from app.deps import get_current_active_user, get_project_membership
from app.utils.get_project_marketplace_token import get_wb_credentials_for_project

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
# Отдельный роутер для витринных эндпоинтов по остаткам
stocks_router = APIRouter(prefix="/api/v1", tags=["stocks"])


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


async def ingest_warehouses() -> None:
    """Fetch and upsert warehouses/offices from WB API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_warehouses: skipped (MOCK mode or no token)")
        return
    
    client = WBClient()
    warehouses = await client.fetch_warehouses()
    
    if not warehouses:
        print("ingest_warehouses: no warehouses returned from API")
        return
    
    print(f"ingest_warehouses: fetched {len(warehouses)} warehouses")
    
    upsert_sql = text("""
        INSERT INTO wb_warehouses (wb_id, name, city, address, type, raw, updated_at)
        VALUES (:wb_id, :name, :city, :address, :type, :raw, now())
        ON CONFLICT (wb_id) DO UPDATE SET
            name = EXCLUDED.name,
            city = EXCLUDED.city,
            address = EXCLUDED.address,
            type = EXCLUDED.type,
            raw = EXCLUDED.raw,
            updated_at = now()
    """)
    
    rows = []
    for wh in warehouses:
        wb_id = wh.get("id") or wh.get("wb_id") or wh.get("warehouseId")
        name = wh.get("name") or wh.get("warehouseName")
        city = wh.get("city")
        address = wh.get("address")
        wh_type = wh.get("type") or wh.get("warehouseType")
        
        if not wb_id:
            print(f"ingest_warehouses: skipping warehouse without id: {wh}")
            continue
        
        rows.append({
            "wb_id": wb_id,
            "name": name,
            "city": city,
            "address": address,
            "type": wh_type,
            "raw": _serialize_json_field(wh)
        })
    
    if rows:
        with engine.begin() as conn:
            conn.execute(upsert_sql, rows)
        print(f"ingest_warehouses: upserted {len(rows)} warehouses")
    else:
        print("ingest_warehouses: no valid warehouses to upsert")


async def ingest_stocks(project_id: int) -> None:
    """Fetch and insert stock snapshots from WB API for a specific project.
    
    Args:
        project_id: Project ID to associate stock snapshots with (required).

    Алгоритм:
    1. Получаем список складов из wb_warehouses (если нет — дергаем ingest_warehouses).
    2. Получаем список chrtIds из products (через db_products.get_chrt_ids).
    3. Для каждого склада и батча chrtIds вызываем WB API:
       POST /api/v3/stocks/{warehouseId} с body {"chrtIds": [...]}
    4. Сохраняем результаты в stock_snapshots (append-only).
    """
    # Get credentials from project_marketplaces (preferred) or fallback to env
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if credentials:
            token = credentials.get("token", "")
        else:
            # Not enabled or no connection - use env fallback
            token = os.getenv("WB_TOKEN", "") or ""
    except ValueError as e:
        # Enabled but not connected - log error and skip (error already checked at endpoint level)
        print(f"ingest_stocks: {str(e)}, skipping")
        return
    if not token or token.upper() == "MOCK":
        print("ingest_stocks: skipped (MOCK mode or no token)")
        return
    # 1. Получаем склады из wb_warehouses
    select_warehouses_sql = text(
        "SELECT wb_id, name FROM wb_warehouses ORDER BY wb_id"
    )

    with engine.connect() as conn:
        result = conn.execute(select_warehouses_sql).mappings().all()
        warehouses = [dict(row) for row in result]

    if not warehouses:
        print("ingest_stocks: wb_warehouses is empty, running ingest_warehouses first")
        await ingest_warehouses()
        with engine.connect() as conn:
            result = conn.execute(select_warehouses_sql).mappings().all()
            warehouses = [dict(row) for row in result]

    if not warehouses:
        print("ingest_stocks: no warehouses available after ingest_warehouses, aborting")
        return

    print(f"ingest_stocks: using {len(warehouses)} warehouses from wb_warehouses")

    # 2. Получаем chrtIds из products
    chrt_ids = db_products.get_chrt_ids()
    if not chrt_ids:
        print(
            "ingest_stocks: no chrtIds found in products; "
            "ensure products are ingested and contain sizes/raw.sizes"
        )
        return

    print(f"ingest_stocks: chrtIds total = {len(chrt_ids)} (first 5: {chrt_ids[:5] if len(chrt_ids) >= 5 else chrt_ids})")

    client = WBClient()

    insert_sql = text(
        """
        INSERT INTO stock_snapshots (nm_id, warehouse_wb_id, quantity, snapshot_at, raw, project_id)
        VALUES (:nm_id, :warehouse_wb_id, :quantity, now(), :raw, :project_id)
        """
    )

    # Для сопоставления chrtId -> nm_id используем products.raw->'sizes' из данного проекта
    chrt_to_nm_sql = text(
        """
        SELECT (elem->>'chrtID')::bigint AS chrt_id,
               nm_id
        FROM products
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(sizes, raw->'sizes')
        ) AS elem
        WHERE elem ? 'chrtID'
          AND (elem->>'chrtID') ~ '^[0-9]+'
          AND products.project_id = :project_id
        """
    )

    with engine.connect() as conn:
        mapping_rows = conn.execute(chrt_to_nm_sql, {"project_id": project_id}).mappings().all()
        chrt_to_nm: Dict[int, int] = {
            int(row["chrt_id"]): int(row["nm_id"]) for row in mapping_rows if row.get("chrt_id") is not None
        }

    print(f"ingest_stocks: built chrtId->nm_id mapping for {len(chrt_to_nm)} sizes")

    # 3. Для каждого склада и батча chrtIds запрашиваем остатки
    # Лимит WB API: максимум 1000 chrtIds на запрос
    batch_size = 1000
    total_api_records = 0
    total_inserted = 0

    for wh in warehouses:
        warehouse_id = wh["wb_id"]
        print(f"ingest_stocks: fetching stocks for warehouse {warehouse_id}")

        for i in range(0, len(chrt_ids), batch_size):
            batch_chrt_ids = chrt_ids[i : i + batch_size]
            print(
                f"ingest_stocks: warehouse={warehouse_id}, chrtIds_chunk={len(batch_chrt_ids)}"
            )
            stocks = await client.fetch_stocks(warehouse_id, batch_chrt_ids)

            if not stocks:
                print(
                    f"ingest_stocks: warehouse={warehouse_id}, chunk_size={len(batch_chrt_ids)}, stocks=0"
                )
                continue

            print(
                f"ingest_stocks: warehouse={warehouse_id}, chunk_size={len(batch_chrt_ids)}, stocks={len(stocks)}"
            )
            total_api_records += len(stocks)

            rows: List[Dict[str, Any]] = []
            for stock in stocks:
                # WB API возвращает chrtId (с маленькой 'd')
                chrt_id = (
                    stock.get("chrtId")
                    or stock.get("chrtID")
                    or stock.get("chrt_id")
                )
                # nm_id может быть в ответе или через mapping chrtId->nm_id
                nm_id = (
                    stock.get("nmId")
                    or stock.get("nm_id")
                    or stock.get("nmID")
                    or (chrt_to_nm.get(int(chrt_id)) if chrt_id is not None else None)
                )
                warehouse_wb_id = (
                    stock.get("warehouseId")
                    or stock.get("warehouse_id")
                    or stock.get("warehouse_wb_id")
                    or warehouse_id
                )
                quantity = (
                    stock.get("quantity")
                    or stock.get("qty")
                    or stock.get("stock")
                    or stock.get("amount")
                    or 0
                )

                if nm_id is None:
                    print(
                        f"ingest_stocks: skipping stock without nm_id and mapping, chrt_id={chrt_id}"
                    )
                    continue

                rows.append(
                    {
                        "nm_id": int(nm_id),
                        "warehouse_wb_id": int(warehouse_wb_id)
                        if warehouse_wb_id is not None
                        else None,
                        "quantity": int(quantity),
                        "raw": _serialize_json_field(stock),
                        "project_id": project_id,
                    }
                )

            if rows:
                with engine.begin() as conn:
                    conn.execute(insert_sql, rows)
                    total_inserted += len(rows)

    print(
        f"ingest_stocks: finished. api_records={total_api_records} inserted={total_inserted}"
    )


@router.get("/warehouses")
async def get_warehouses_info():
    """Get information about warehouses ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://content-api.wildberries.ru/api/v1/warehouses"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK"
    }


@router.post("/warehouses")
async def start_ingest_warehouses(background_tasks: BackgroundTasks):
    """Start ingestion of warehouses from Wildberries API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Warehouses ingestion skipped (MOCK mode or no token configured)"
        }
    
    background_tasks.add_task(ingest_warehouses)
    return {"status": "started", "message": "Warehouses ingestion started in background"}


@router.get("/stocks")
async def get_stocks_info():
    """Get information about stocks ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouseId}"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK"
    }


@router.post("/projects/{project_id}/stocks")
async def start_ingest_stocks(
    project_id: int = Path(..., description="Project ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)
):
    """Start ingestion of stock balances from Wildberries API for a specific project.
    
    Requires project membership.
    """
    # Check credentials before starting background task
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if credentials is None:
            # Not enabled or no connection - allow env fallback
            pass
    except ValueError as e:
        # Enabled but not connected - return error
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Stocks ingestion skipped (MOCK mode or no token configured)"
        }
    
    background_tasks.add_task(ingest_stocks, project_id)
    return {"status": "started", "message": f"Stocks ingestion started in background for project {project_id}"}


@stocks_router.get("/projects/{project_id}/stocks/latest")
async def get_latest_stocks(
    project_id: int = Path(..., description="Project ID"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)
):
    """Return latest stock snapshots with pagination for a specific project.

    Возвращает последние записи из stock_snapshots для проекта, отсортированные по snapshot_at DESC.
    Requires project membership.
    """
    sql = text(
        """
        SELECT nm_id, warehouse_wb_id, quantity, snapshot_at
        FROM stock_snapshots
        WHERE project_id = :project_id
        ORDER BY snapshot_at DESC, nm_id
        LIMIT :limit OFFSET :offset
        """
    )

    try:
        with engine.connect() as conn:
            # Get total count filtered by project_id
            count_sql = text("SELECT COUNT(*) as total FROM stock_snapshots WHERE project_id = :project_id")
            total_result = conn.execute(count_sql, {"project_id": project_id}).scalar()
            total = int(total_result) if total_result else 0
            
            # Get paginated data
            result = conn.execute(sql, {"project_id": project_id, "limit": limit, "offset": offset}).mappings().all()
            rows = [dict(row) for row in result]

        return {
            "data": rows,
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "total": total
        }
    except Exception as e:
        # Handle case when table doesn't exist
        print(f"get_latest_stocks: error: {e}")
        return {
            "data": [],
            "limit": limit,
            "offset": offset,
            "count": 0,
            "error": "Table not found or error occurred"
        }

