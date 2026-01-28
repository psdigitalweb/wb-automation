"""Database helpers for Warehouse Labor Days.

This module provides CRUD and summary aggregation for warehouse_labor_days and warehouse_labor_day_rates.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def _validate_rates(rates: List[Dict[str, Any]]) -> None:
    """Validate rates data.
    
    Args:
        rates: List of rate dictionaries
        
    Raises:
        ValueError: If any rate is invalid
    """
    if not rates:
        raise ValueError("At least one rate is required")
    
    for i, rate in enumerate(rates):
        if not rate.get("rate_name") or not rate["rate_name"].strip():
            raise ValueError(f"Rate {i+1}: rate_name must be non-empty")
        if not isinstance(rate.get("employees_count"), int) or rate.get("employees_count", 0) <= 0:
            raise ValueError(f"Rate {i+1}: employees_count must be > 0")
        rate_amount = rate.get("rate_amount")
        # Convert to Decimal if needed (from Pydantic model_dump, it should already be Decimal)
        if isinstance(rate_amount, str):
            try:
                rate_amount = Decimal(rate_amount.replace(' ', '').replace(',', '.'))
            except (ValueError, TypeError):
                raise ValueError(f"Rate {i+1}: rate_amount must be a valid number")
        elif isinstance(rate_amount, (int, float)):
            rate_amount = Decimal(str(rate_amount))
        elif not isinstance(rate_amount, Decimal):
            raise ValueError(f"Rate {i+1}: rate_amount must be a number")
        
        if rate_amount <= 0:
            raise ValueError(f"Rate {i+1}: rate_amount must be > 0")


def upsert_warehouse_labor_day(project_id: int, data: dict) -> dict:
    """Upsert a warehouse labor day with rates.
    
    Manual upsert (not using ON CONFLICT due to partial unique indexes):
    - SELECT existing record by (project_id, work_date, marketplace_code IS NOT DISTINCT FROM)
    - If found: UPDATE (including updated_at = now())
    - If not found: INSERT
    - In the same transaction: delete old rates, insert new rates
    
    Args:
        project_id: Project ID
        data: Dictionary with work_date, marketplace_code, notes, rates
        
    Returns:
        Created/updated day with nested rates as dict
        
    Raises:
        ValueError: If rates validation fails
    """
    work_date = data.get("work_date")
    marketplace_code = data.get("marketplace_code")
    notes = data.get("notes")
    rates = data.get("rates", [])
    
    if not work_date:
        raise ValueError("work_date is required")
    
    # Validate rates
    _validate_rates(rates)
    
    with engine.begin() as conn:
        # Check if day exists using IS NOT DISTINCT FROM for NULL comparison
        if marketplace_code is None:
            check_sql = text("""
                SELECT id
                FROM warehouse_labor_days
                WHERE project_id = :project_id
                  AND work_date = :work_date
                  AND marketplace_code IS NULL
            """)
        else:
            check_sql = text("""
                SELECT id
                FROM warehouse_labor_days
                WHERE project_id = :project_id
                  AND work_date = :work_date
                  AND marketplace_code IS NOT DISTINCT FROM :marketplace_code
            """)
        
        result = conn.execute(check_sql, {
            "project_id": project_id,
            "work_date": work_date,
            "marketplace_code": marketplace_code,
        })
        existing = result.fetchone()
        
        if existing:
            # UPDATE existing day
            day_id = existing[0]
            update_sql = text("""
                UPDATE warehouse_labor_days
                SET notes = :notes,
                    updated_at = now()
                WHERE id = :day_id
                RETURNING id, project_id, work_date, marketplace_code, notes, created_at, updated_at
            """)
            result = conn.execute(update_sql, {
                "day_id": day_id,
                "notes": notes,
            })
        else:
            # INSERT new day
            insert_sql = text("""
                INSERT INTO warehouse_labor_days (project_id, work_date, marketplace_code, notes)
                VALUES (:project_id, :work_date, :marketplace_code, :notes)
                RETURNING id, project_id, work_date, marketplace_code, notes, created_at, updated_at
            """)
            result = conn.execute(insert_sql, {
                "project_id": project_id,
                "work_date": work_date,
                "marketplace_code": marketplace_code,
                "notes": notes,
            })
        
        day_row = result.fetchone()
        day_id = day_row[0]
        
        # Delete old rates
        delete_rates_sql = text("""
            DELETE FROM warehouse_labor_day_rates
            WHERE labor_day_id = :day_id
        """)
        conn.execute(delete_rates_sql, {"day_id": day_id})
        
        # Insert new rates
        if rates:
            for rate in rates:
                insert_rate_sql = text("""
                    INSERT INTO warehouse_labor_day_rates (
                        labor_day_id, rate_name, employees_count, rate_amount, currency
                    )
                    VALUES (:labor_day_id, :rate_name, :employees_count, :rate_amount, :currency)
                """)
                conn.execute(insert_rate_sql, {
                    "labor_day_id": day_id,
                    "rate_name": rate["rate_name"],
                    "employees_count": rate["employees_count"],
                    "rate_amount": rate["rate_amount"],
                    "currency": rate.get("currency", "RUB"),
                })
        
        # Fetch complete day with rates
        return get_warehouse_labor_day_by_id(day_id)


def list_warehouse_labor_days(
    project_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    marketplace_code: Optional[str] = None,
) -> List[dict]:
    """List warehouse labor days with rates.
    
    Args:
        project_id: Project ID
        date_from: Start date filter (optional)
        date_to: End date filter (optional)
        marketplace_code: Marketplace code filter (optional)
        
    Returns:
        List of days with nested rates
    """
    where_clauses = ["project_id = :project_id"]
    params: Dict[str, Any] = {"project_id": project_id}
    
    if date_from:
        where_clauses.append("work_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("work_date <= :date_to")
        params["date_to"] = date_to
    if marketplace_code is not None:
        if marketplace_code:
            where_clauses.append("marketplace_code = :marketplace_code")
            params["marketplace_code"] = marketplace_code
        else:
            where_clauses.append("marketplace_code IS NULL")
    
    where_sql = " AND ".join(where_clauses)
    
    sql = text(f"""
        SELECT 
            d.id, d.project_id, d.work_date, d.marketplace_code, d.notes,
            d.created_at, d.updated_at,
            r.id AS rate_id, r.rate_name, r.employees_count, r.rate_amount, r.currency,
            r.created_at AS rate_created_at, r.updated_at AS rate_updated_at
        FROM warehouse_labor_days d
        LEFT JOIN warehouse_labor_day_rates r ON r.labor_day_id = d.id
        WHERE {where_sql}
        ORDER BY d.work_date DESC, d.id, r.id
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        
        # Group by day
        days_dict: Dict[int, dict] = {}
        for row in rows:
            day_id = row[0]
            if day_id not in days_dict:
                days_dict[day_id] = {
                    "id": day_id,
                    "project_id": row[1],
                    "work_date": row[2],
                    "marketplace_code": row[3],
                    "notes": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                    "rates": [],
                }
            
            # Add rate if exists
            if row[7] is not None:  # rate_id
                days_dict[day_id]["rates"].append({
                    "id": row[7],
                    "labor_day_id": day_id,
                    "rate_name": row[8],
                    "employees_count": row[9],
                    "rate_amount": row[10],
                    "currency": row[11],
                    "created_at": row[12],
                    "updated_at": row[13],
                })
        
        # Calculate total_amount for each day
        for day in days_dict.values():
            total = Decimal("0")
            for rate in day["rates"]:
                total += Decimal(str(rate["rate_amount"])) * Decimal(str(rate["employees_count"]))
            day["total_amount"] = total
        
        return list(days_dict.values())


def get_warehouse_labor_day_by_id(day_id: int) -> Optional[dict]:
    """Get warehouse labor day by ID with rates.
    
    Args:
        day_id: Day ID
        
    Returns:
        Day with nested rates as dict, or None if not found
    """
    sql = text("""
        SELECT 
            d.id, d.project_id, d.work_date, d.marketplace_code, d.notes,
            d.created_at, d.updated_at,
            r.id AS rate_id, r.rate_name, r.employees_count, r.rate_amount, r.currency,
            r.created_at AS rate_created_at, r.updated_at AS rate_updated_at
        FROM warehouse_labor_days d
        LEFT JOIN warehouse_labor_day_rates r ON r.labor_day_id = d.id
        WHERE d.id = :day_id
        ORDER BY r.id
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, {"day_id": day_id}).fetchall()
        
        if not rows:
            return None
        
        day = {
            "id": rows[0][0],
            "project_id": rows[0][1],
            "work_date": rows[0][2],
            "marketplace_code": rows[0][3],
            "notes": rows[0][4],
            "created_at": rows[0][5],
            "updated_at": rows[0][6],
            "rates": [],
        }
        
        # Add rates
        for row in rows:
            if row[7] is not None:  # rate_id
                day["rates"].append({
                    "id": row[7],
                    "labor_day_id": day_id,
                    "rate_name": row[8],
                    "employees_count": row[9],
                    "rate_amount": row[10],
                    "currency": row[11],
                    "created_at": row[12],
                    "updated_at": row[13],
                })
        
        # Calculate total_amount
        total = Decimal("0")
        for rate in day["rates"]:
            total += Decimal(str(rate["rate_amount"])) * Decimal(str(rate["employees_count"]))
        day["total_amount"] = total
        
        return day


def delete_warehouse_labor_day(project_id: int, day_id: int) -> bool:
    """Delete warehouse labor day (rates are deleted by CASCADE).
    
    Args:
        project_id: Project ID (for validation)
        day_id: Day ID
        
    Returns:
        True if deleted, False if not found
    """
    # First check if day exists and belongs to project
    check_sql = text("""
        SELECT id
        FROM warehouse_labor_days
        WHERE id = :day_id AND project_id = :project_id
    """)
    
    with engine.begin() as conn:
        result = conn.execute(check_sql, {"day_id": day_id, "project_id": project_id})
        if not result.fetchone():
            return False
        
        # Delete day (rates will be deleted by CASCADE)
        delete_sql = text("""
            DELETE FROM warehouse_labor_days
            WHERE id = :day_id
        """)
        conn.execute(delete_sql, {"day_id": day_id})
        return True


def get_warehouse_labor_summary(
    project_id: int,
    date_from: date,
    date_to: date,
    group_by: str = "day",
    marketplace_code: Optional[str] = None,
) -> dict:
    """Get summary of warehouse labor costs.
    
    Args:
        project_id: Project ID
        date_from: Start date for summary period
        date_to: End date for summary period
        group_by: Aggregation level ('day', 'marketplace', or 'project')
        marketplace_code: Optional marketplace code filter
        
    Returns:
        Dict with total_amount (Decimal) and breakdown (List[dict])
        
    Raises:
        ValueError: If group_by is invalid
    """
    if group_by not in ["day", "marketplace", "project"]:
        raise ValueError(f"Invalid group_by: {group_by}. Must be 'day', 'marketplace', or 'project'")
    
    where_clauses = [
        "d.project_id = :project_id",
        "d.work_date >= :date_from",
        "d.work_date <= :date_to",
    ]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    
    if marketplace_code is not None:
        if marketplace_code:
            where_clauses.append("d.marketplace_code = :marketplace_code")
            params["marketplace_code"] = marketplace_code
        else:
            where_clauses.append("d.marketplace_code IS NULL")
    
    where_sql = " AND ".join(where_clauses)
    
    # Build GROUP BY clause
    if group_by == "day":
        group_by_sql = "d.work_date"
        select_fields = "d.work_date, NULL::text AS marketplace_code"
    elif group_by == "marketplace":
        group_by_sql = "d.marketplace_code"
        select_fields = "NULL::date AS work_date, d.marketplace_code"
    else:  # project
        group_by_sql = "1"  # Constant for single group
        select_fields = "NULL::date AS work_date, NULL::text AS marketplace_code"
    
    sql = text(f"""
        SELECT
            {select_fields},
            SUM(r.employees_count * r.rate_amount) AS total_amount
        FROM warehouse_labor_days d
        INNER JOIN warehouse_labor_day_rates r ON r.labor_day_id = d.id
        WHERE {where_sql}
        GROUP BY {group_by_sql}
        ORDER BY total_amount DESC
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
        breakdown = [dict(row) for row in rows]
        
        # Calculate total (keep as Decimal for precision)
        total_amount = sum(Decimal(str(row.get("total_amount", 0) or 0)) for row in breakdown)
        
        return {
            "total_amount": total_amount,
            "breakdown": breakdown,
        }


__all__ = [
    "upsert_warehouse_labor_day",
    "list_warehouse_labor_days",
    "get_warehouse_labor_day_by_id",
    "delete_warehouse_labor_day",
    "get_warehouse_labor_summary",
]
