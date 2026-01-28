"""Utilities for period management (minimal implementation).

Periods are identified by period_id and represent date ranges.
Currently supports only period_type='wb_week' without complex mappings.
"""

from __future__ import annotations

from datetime import date
from typing import Tuple

from fastapi import HTTPException, status
from sqlalchemy import text

from app.db import engine


def resolve_period(period_id: int) -> Tuple[date, date]:
    """Resolve period_id to (date_from, date_to) tuple.
    
    Args:
        period_id: Period ID
        
    Returns:
        Tuple of (date_from, date_to)
        
    Raises:
        HTTPException 404 if period not found
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT date_from, date_to
                FROM periods
                WHERE id = :period_id
            """),
            {"period_id": period_id},
        ).mappings().first()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Period {period_id} not found",
            )
        
        return (row["date_from"], row["date_to"])


def ensure_period(period_type: str, date_from: date, date_to: date) -> int:
    """Ensure period exists, create if needed.
    
    Args:
        period_type: Period type (e.g., 'wb_week')
        date_from: Start date
        date_to: End date
        
    Returns:
        period_id (existing or newly created)
    """
    with engine.begin() as conn:
        # Try to find existing
        row = conn.execute(
            text("""
                SELECT id
                FROM periods
                WHERE period_type = :period_type
                  AND date_from = :date_from
                  AND date_to = :date_to
            """),
            {
                "period_type": period_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().first()
        
        if row:
            return row["id"]
        
        # Insert new period
        result = conn.execute(
            text("""
                INSERT INTO periods (period_type, date_from, date_to)
                VALUES (:period_type, :date_from, :date_to)
                ON CONFLICT (period_type, date_from, date_to) DO NOTHING
                RETURNING id
            """),
            {
                "period_type": period_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        
        inserted_row = result.mappings().first()
        if inserted_row:
            return inserted_row["id"]
        
        # If conflict happened, fetch the existing one
        row = conn.execute(
            text("""
                SELECT id
                FROM periods
                WHERE period_type = :period_type
                  AND date_from = :date_from
                  AND date_to = :date_to
            """),
            {
                "period_type": period_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().first()
        
        if not row:
            raise RuntimeError(f"Failed to create or find period {period_type} {date_from} to {date_to}")
        
        return row["id"]
