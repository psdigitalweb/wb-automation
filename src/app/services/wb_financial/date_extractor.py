"""Extract event_date from WB payload with priority and quality flag."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Tuple

# Priority 1: operation/doc date keys
OPERATION_DATE_KEYS = [
    "operation_date", "operation_dt", "doc_date", "date_from", "date",
    "operationDate", "operationDt", "docDate", "dateFrom",
]
# Priority 2: sale/return date keys
SALE_RETURN_DATE_KEYS = [
    "sale_dt", "sale_date", "return_dt", "return_date", "report_date",
    "saleDt", "saleDate", "returnDt", "returnDate", "reportDate",
]


def _parse_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s:
        return None
    # Try YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    try:
        return date.fromisoformat(s.split("T")[0])
    except (ValueError, TypeError):
        return None


def extract_event_date(
    payload: dict,
    period_to: Optional[date],
    fetched_at: Optional[datetime],
) -> Tuple[Optional[date], str]:
    """Extract event date from payload with priority.

    Priority:
      1. operation/doc date keys
      2. sale/return date keys
      3. fallback: period_to from report
      4. fallback: fetched_at.date()

    Returns:
        (event_date, quality) where quality is 'exact' or 'fallback'
    """
    for key in OPERATION_DATE_KEYS:
        v = payload.get(key)
        d = _parse_date(v)
        if d is not None:
            return (d, "exact")

    for key in SALE_RETURN_DATE_KEYS:
        v = payload.get(key)
        d = _parse_date(v)
        if d is not None:
            return (d, "exact")

    if period_to is not None:
        return (period_to, "fallback")
    if fetched_at is not None:
        return (fetched_at.date(), "fallback")
    return (None, "fallback")
