"""Ingestion endpoints for WB Statistics API supplier stock balances."""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Query, Path, Depends
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient
from app.deps import get_current_active_user, get_project_membership
from app.utils.get_project_marketplace_token import get_wb_credentials_for_project

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
# Отдельный роутер для витринных эндпоинтов по supplier stocks
supplier_stocks_router = APIRouter(prefix="/api/v1", tags=["supplier-stocks"])


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _parse_rfc3339_to_datetime(date_str: str) -> datetime:
    """Parse RFC3339 date string to datetime object.
    
    Handles formats like:
    - "2019-06-20T00:00:00Z"
    - "2019-06-20T00:00:00+03:00"
    """
    # Try parsing with timezone
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            if fmt.endswith("Z"):
                # Replace Z with +00:00 for parsing
                date_str_z = date_str.replace("Z", "+00:00")
                return datetime.strptime(date_str_z, fmt.replace("Z", "%z"))
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Fallback: try without timezone
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse RFC3339 date: {date_str}")


async def ingest_supplier_stocks(project_id: int, run_id: int | None = None) -> None:
    """Fetch and insert supplier stock snapshots from WB Statistics API.
    
    Алгоритм:
    1. Определить начальный dateFrom:
       - Если в БД есть записи: MAX(last_change_date)
       - Иначе: из WB_STOCKS_DATE_FROM_DEFAULT или "2019-06-20T00:00:00Z"
    2. Цикл пагинации:
       - Вызвать fetch_supplier_stocks(dateFrom)
       - Если [] -> завершить
       - Сохранить все строки в supplier_stock_snapshots
       - Взять lastChangeDate последней строки как следующий dateFrom
       - Sleep 60 секунд (rate limit: 1 req/min)
    3. Обработка ошибок:
       - 429: backoff 60-90 секунд и повторить
       - 5xx: retry с exponential backoff
    """
    # Prefer per-project credentials; fallback to env for backward compatibility
    try:
        credentials = get_wb_credentials_for_project(project_id)
        token = credentials.get("token", "") if credentials else (os.getenv("WB_TOKEN", "") or "")
    except ValueError as e:
        print(f"ingest_supplier_stocks: {str(e)}, skipping (run_id={run_id})")
        return

    if not token or token.upper() == "MOCK":
        print(f"ingest_supplier_stocks: skipped (MOCK mode or no token), run_id={run_id}")
        return
    
    # 1. Определить начальный dateFrom
    default_date_from = os.getenv("WB_STOCKS_DATE_FROM_DEFAULT", "2019-06-20T00:00:00Z")
    
    # Проверить, есть ли уже данные в БД
    max_date_sql = text("""
        SELECT MAX(last_change_date) AS max_date
        FROM supplier_stock_snapshots
    """)
    
    with engine.connect() as conn:
        result = conn.execute(max_date_sql).mappings().all()
        max_date = result[0]["max_date"] if result and result[0].get("max_date") else None
    
    if max_date:
        # Инкрементальная загрузка с overlap window (2 минуты) для защиты от потери данных
        # из-за задержек/часовых поясов. Дубликаты уберёт уникальный индекс.
        from datetime import timedelta
        overlap_minutes = 2
        date_from_dt = max_date - timedelta(minutes=overlap_minutes)
        # Преобразуем datetime в RFC3339 с правильным форматом timezone
        if date_from_dt.tzinfo:
            # Format: 2026-01-13T13:10:26+03:00
            tz_offset = date_from_dt.strftime("%z")
            tz_formatted = f"{tz_offset[:3]}:{tz_offset[3:]}" if len(tz_offset) == 5 else "+00:00"
            date_from = date_from_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_formatted
        else:
            date_from = date_from_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        print(f"ingest_supplier_stocks: incremental mode, starting from {date_from} (max_date: {max_date}, overlap: -{overlap_minutes}min)")
    else:
        date_from = default_date_from
        print(f"ingest_supplier_stocks: full mode, starting from {date_from}")
    
    client = WBClient(token=token)
    
    insert_sql = text("""
        INSERT INTO supplier_stock_snapshots (
            snapshot_at, last_change_date, warehouse_name, nm_id,
            supplier_article, barcode, tech_size, quantity, quantity_full,
            in_way_to_client, in_way_from_client, is_supply, is_realization,
            price, discount, raw
        )
        VALUES (
            now(), :last_change_date, :warehouse_name, :nm_id,
            :supplier_article, :barcode, :tech_size, :quantity, :quantity_full,
            :in_way_to_client, :in_way_from_client, :is_supply, :is_realization,
            :price, :discount, :raw
        )
        ON CONFLICT (last_change_date, nm_id, barcode, warehouse_name) DO NOTHING
    """)
    
    total_pages = 0
    total_received = 0
    total_inserted = 0
    rate_limit_delay = 60  # 1 request per minute
    max_pages_per_run = 200  # Защита от зацикливания
    
    # 2. Цикл пагинации
    while total_pages < max_pages_per_run:
        print(f"ingest_supplier_stocks: fetching page {total_pages + 1}, dateFrom={date_from}")
        
        stocks = await client.fetch_supplier_stocks(date_from)
        
        if not stocks or len(stocks) == 0:
            print("ingest_supplier_stocks: empty response, pagination complete")
            break
        
        print(f"ingest_supplier_stocks: received {len(stocks)} records for page {total_pages + 1}")
        total_pages += 1
        total_received += len(stocks)
        
        # Сохранить записи и вычислить min/max lastChangeDate для страницы
        rows: List[Dict[str, Any]] = []
        page_last_change_dates: List[datetime] = []
        
        for stock in stocks:
            # Извлечь lastChangeDate
            last_change_date_str = stock.get("lastChangeDate") or stock.get("last_change_date")
            
            # Парсим lastChangeDate в datetime для БД
            try:
                last_change_date_dt = _parse_rfc3339_to_datetime(last_change_date_str) if last_change_date_str else None
                if last_change_date_dt:
                    page_last_change_dates.append(last_change_date_dt)
            except Exception as e:
                print(f"ingest_supplier_stocks: error parsing lastChangeDate '{last_change_date_str}': {e}")
                continue
            
            # Извлекаем поля из ответа WB
            nm_id = stock.get("nmId") or stock.get("nm_id") or stock.get("nmID")
            warehouse_name = stock.get("warehouseName") or stock.get("warehouse_name")
            supplier_article = stock.get("supplierArticle") or stock.get("supplier_article")
            barcode = stock.get("barcode")
            tech_size = stock.get("techSize") or stock.get("tech_size")
            quantity = stock.get("quantity") or stock.get("Quantity") or 0
            quantity_full = stock.get("quantityFull") or stock.get("quantity_full")
            in_way_to_client = stock.get("inWayToClient") or stock.get("in_way_to_client")
            in_way_from_client = stock.get("inWayFromClient") or stock.get("in_way_from_client")
            is_supply = stock.get("isSupply") or stock.get("is_supply")
            is_realization = stock.get("isRealization") or stock.get("is_realization")
            price = stock.get("Price") or stock.get("price")
            discount = stock.get("Discount") or stock.get("discount")
            
            if not nm_id:
                print(f"ingest_supplier_stocks: skipping stock without nm_id: {stock}")
                continue
            
            rows.append({
                "last_change_date": last_change_date_dt,
                "warehouse_name": warehouse_name,
                "nm_id": int(nm_id),
                "supplier_article": supplier_article,
                "barcode": barcode,
                "tech_size": tech_size,
                "quantity": int(quantity),
                "quantity_full": int(quantity_full) if quantity_full is not None else None,
                "in_way_to_client": int(in_way_to_client) if in_way_to_client is not None else None,
                "in_way_from_client": int(in_way_from_client) if in_way_from_client is not None else None,
                "is_supply": bool(is_supply) if is_supply is not None else None,
                "is_realization": bool(is_realization) if is_realization is not None else None,
                "price": float(price) if price is not None else None,
                "discount": int(discount) if discount is not None else None,
                "raw": _serialize_json_field(stock),
            })
        
        if rows:
            with engine.begin() as conn:
                result = conn.execute(insert_sql, rows)
                # ON CONFLICT DO NOTHING: rowcount reflects actual inserts
                inserted = int(result.rowcount or 0)
                total_inserted += inserted
            print(f"ingest_supplier_stocks: inserted {inserted} records (page {total_pages})")
        else:
            print(f"ingest_supplier_stocks: no valid rows to insert for page {total_pages}")
        
        # Вычислить min/max lastChangeDate для страницы
        if not page_last_change_dates:
            print("ingest_supplier_stocks: no valid lastChangeDate in page, pagination complete")
            break
        
        page_min_last_change_date = min(page_last_change_dates)
        page_max_last_change_date = max(page_last_change_dates)
        
        print(f"ingest_supplier_stocks: page {total_pages} lastChangeDate range: min={page_min_last_change_date}, max={page_max_last_change_date}")
        
        # Защита от зацикливания: если не сдвигаемся вперёд, остановиться
        current_date_from_dt = _parse_rfc3339_to_datetime(date_from)
        # Убедимся, что оба datetime имеют timezone для сравнения
        if current_date_from_dt.tzinfo is None:
            # Если naive, добавим UTC
            from datetime import timezone
            current_date_from_dt = current_date_from_dt.replace(tzinfo=timezone.utc)
        if page_max_last_change_date.tzinfo is None:
            from datetime import timezone
            page_max_last_change_date = page_max_last_change_date.replace(tzinfo=timezone.utc)
        
        if page_max_last_change_date <= current_date_from_dt:
            print(f"ingest_supplier_stocks: WARNING - page_max_last_change_date ({page_max_last_change_date}) <= current_dateFrom ({current_date_from_dt}), stopping to prevent infinite loop")
            break
        
        # Следующий dateFrom = page_max_last_change_date минус 1 секунда для overlap
        # (чтобы не пропустить пограничные записи, дубликаты уберёт уникальный индекс)
        from datetime import timedelta
        next_date_from_dt = page_max_last_change_date - timedelta(seconds=1)
        # IMPORTANT: if overlap produces the same (or older) dateFrom, it will loop forever.
        # In this case, move dateFrom forward to page_max_last_change_date (no -1s overlap).
        if next_date_from_dt <= current_date_from_dt:
            next_date_from_dt = page_max_last_change_date
        # If we STILL can't move forward, stop to prevent infinite loop.
        if next_date_from_dt <= current_date_from_dt:
            print(
                f"ingest_supplier_stocks: WARNING - cannot advance dateFrom "
                f"(current={current_date_from_dt}, page_max={page_max_last_change_date}), stopping"
            )
            break
        # Форматируем в RFC3339 с правильным timezone
        if next_date_from_dt.tzinfo:
            tz_offset = next_date_from_dt.strftime("%z")
            tz_formatted = f"{tz_offset[:3]}:{tz_offset[3:]}" if len(tz_offset) == 5 else "+00:00"
            date_from = next_date_from_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_formatted
        else:
            date_from = next_date_from_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        
        print(f"ingest_supplier_stocks: next dateFrom={date_from} (page_max - 1s for overlap)")

        # Best-effort progress update in ingest_runs.stats_json for UI (no secrets).
        if run_id is not None:
            try:
                from app.services.ingest import runs as runs_service
                runs_service.set_run_progress(
                    int(run_id),
                    {
                        "ok": None,
                        "phase": "supplier_stocks",
                        "page": total_pages,
                        "received": total_received,
                        "inserted": total_inserted,
                        "last_page_inserted": inserted if "inserted" in locals() else None,
                        "date_from": date_from,
                        "page_max_last_change_date": page_max_last_change_date.isoformat()
                        if hasattr(page_max_last_change_date, "isoformat")
                        else str(page_max_last_change_date),
                    },
                )
            except Exception:
                pass
        
        # Rate limit: sleep 60 секунд между запросами
        print(f"ingest_supplier_stocks: rate limit throttling, sleeping {rate_limit_delay} seconds...")
        await asyncio.sleep(rate_limit_delay)
    
    if total_pages >= max_pages_per_run:
        print(f"ingest_supplier_stocks: WARNING - reached max_pages limit ({max_pages_per_run}), stopping")
    
    # Финальная проверка: получить max(last_change_date) из БД
    with engine.connect() as conn:
        result = conn.execute(max_date_sql).mappings().all()
        final_max_date = result[0]["max_date"] if result and result[0].get("max_date") else None
    
    print(f"ingest_supplier_stocks: finished. pages={total_pages}, total_received={total_received}, total_inserted={total_inserted}, max(last_change_date)={final_max_date}")


@router.get("/supplier-stocks")
async def get_supplier_stocks_info():
    """Get information about supplier stocks ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK",
        "rate_limit": "1 request per minute",
        "pagination": "via lastChangeDate parameter"
    }


@router.post("/projects/{project_id}/supplier-stocks")
async def start_ingest_supplier_stocks_for_project(
    project_id: int = Path(..., description="Project ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Start supplier stocks ingestion for a project.

    Matches frontend dashboard button:
      POST /api/v1/ingest/projects/{project_id}/supplier-stocks
    """
    # Check credentials early for a better UX (don't start a background task that immediately skips)
    try:
        credentials = get_wb_credentials_for_project(project_id)
        token = credentials.get("token", "") if credentials else (os.getenv("WB_TOKEN", "") or "")
    except ValueError as e:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Supplier stocks ingestion skipped (MOCK mode or no token configured)",
        }

    background_tasks.add_task(ingest_supplier_stocks, project_id)
    return {"status": "started", "message": f"Supplier stocks ingestion started in background for project {project_id}"}


# Backward-compatible alias: some clients may use underscore in the path.
@router.post("/projects/{project_id}/supplier_stocks")
async def start_ingest_supplier_stocks_for_project_alias(
    project_id: int = Path(..., description="Project ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    return await start_ingest_supplier_stocks_for_project(
        project_id=project_id,
        background_tasks=background_tasks,
        current_user=current_user,
        membership=membership,
    )


# Backward-compatible unscoped endpoint (kept for older clients)
@router.post("/supplier-stocks")
async def start_ingest_supplier_stocks(background_tasks: BackgroundTasks):
    """Start supplier stocks ingestion (uses env token, no project scoping)."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Supplier stocks ingestion skipped (MOCK mode or no token configured)",
        }

    # Use Legacy project_id=1 as a neutral scope (token comes from env anyway)
    background_tasks.add_task(ingest_supplier_stocks, 1)
    return {"status": "started", "message": "Supplier stocks ingestion started in background"}


@supplier_stocks_router.get("/supplier-stocks/latest")
async def get_latest_supplier_stocks(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Return latest supplier stock snapshots with pagination.
    
    Возвращает последние записи из supplier_stock_snapshots,
    отсортированные по last_change_date DESC.
    """
    sql = text("""
        SELECT 
            snapshot_at, last_change_date, warehouse_name, nm_id,
            supplier_article, barcode, tech_size, quantity, quantity_full,
            in_way_to_client, in_way_from_client, is_supply, is_realization,
            price, discount
        FROM supplier_stock_snapshots
        ORDER BY last_change_date DESC, nm_id
        LIMIT :limit OFFSET :offset
    """)
    
    try:
        with engine.connect() as conn:
            # Get total count
            count_sql = text("SELECT COUNT(*) as total FROM supplier_stock_snapshots")
            total_result = conn.execute(count_sql).scalar()
            total = int(total_result) if total_result else 0
            
            # Get paginated data
            result = conn.execute(sql, {"limit": limit, "offset": offset}).mappings().all()
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
        print(f"get_latest_supplier_stocks: error: {e}")
        return {
            "data": [],
            "limit": limit,
            "offset": offset,
            "count": 0,
            "error": "Table not found or error occurred"
        }

