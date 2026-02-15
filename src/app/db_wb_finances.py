"""DB service layer for WB finance reports (project-level storage)."""

import json
import hashlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine


def compute_payload_hash(payload: Any) -> str:
    """Compute deterministic SHA256 hash of JSON payload for deduplication."""
    # Normalize JSON: sort keys, no extra whitespace, keep non-ASCII as-is
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upsert_report_header(
    project_id: int,
    report_id: int,
    marketplace_code: str,
    period_from: Optional[date],
    period_to: Optional[date],
    currency: Optional[str],
    total_amount: Optional[float],
    rows_count: int,
    payload_meta: Any,
) -> Tuple[bool, bool]:
    """Upsert report header (insert new or update existing).
    
    Args:
        project_id: Project ID
        report_id: Report ID from API (realizationreport_id - ID of the report)
        marketplace_code: Marketplace code (default 'wildberries')
        period_from: Start date of report period
        period_to: End date of report period
        currency: Currency code
        total_amount: Total amount (if available at report level)
        rows_count: Number of lines in report
        payload_meta: Sample/meta payload for header (stored as JSONB)
        
    Returns:
        Tuple of (inserted: bool, updated: bool)
        - (True, False) if new record inserted
        - (False, True) if existing record updated
        - (False, False) if no changes
    """
    payload_hash = compute_payload_hash(payload_meta) if payload_meta is not None else ""
    payload_json = json.dumps(payload_meta, ensure_ascii=False) if payload_meta is not None else "{}"

    with engine.begin() as conn:
        # Check if report exists
        existing = conn.execute(
            text("""
                SELECT id, payload_hash, rows_count
                FROM wb_finance_reports
                WHERE project_id = :project_id
                  AND marketplace_code = :marketplace_code
                  AND report_id = :report_id
            """),
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
                "report_id": report_id,
            },
        ).mappings().first()

        if existing:
            # Update existing record
            existing_hash = existing.get("payload_hash", "")
            existing_rows = existing.get("rows_count", 0)
            
            # Update last_seen_at always, update payload/rows_count if changed
            conn.execute(
                text("""
                    UPDATE wb_finance_reports
                    SET last_seen_at = now(),
                        period_from = :period_from,
                        period_to = :period_to,
                        currency = :currency,
                        total_amount = :total_amount,
                        rows_count = :rows_count,
                        payload = CAST(:payload AS jsonb),
                        payload_hash = :payload_hash
                    WHERE project_id = :project_id
                      AND marketplace_code = :marketplace_code
                      AND report_id = :report_id
                """),
                {
                    "project_id": project_id,
                    "marketplace_code": marketplace_code,
                    "report_id": report_id,
                    "period_from": period_from,
                    "period_to": period_to,
                    "currency": currency,
                    "total_amount": total_amount,
                    "rows_count": rows_count,
                    "payload": payload_json,
                    "payload_hash": payload_hash,
                },
            )
            updated = existing_hash != payload_hash or existing_rows != rows_count
            return (False, updated)
        else:
            # Insert new record
            conn.execute(
                text("""
                    INSERT INTO wb_finance_reports (
                        project_id,
                        marketplace_code,
                        report_id,
                        period_from,
                        period_to,
                        currency,
                        total_amount,
                        rows_count,
                        payload,
                        payload_hash
                    )
                    VALUES (
                        :project_id,
                        :marketplace_code,
                        :report_id,
                        :period_from,
                        :period_to,
                        :currency,
                        :total_amount,
                        :rows_count,
                        CAST(:payload AS jsonb),
                        :payload_hash
                    )
                """),
                {
                    "project_id": project_id,
                    "marketplace_code": marketplace_code,
                    "report_id": report_id,
                    "period_from": period_from,
                    "period_to": period_to,
                    "currency": currency,
                    "total_amount": total_amount,
                    "rows_count": rows_count,
                    "payload": payload_json,
                    "payload_hash": payload_hash,
                },
            )
            return (True, False)


def insert_report_line_if_new(
    project_id: int,
    report_id: int,
    line_id: int,
    payload: Any,
) -> bool:
    """Insert report line if it doesn't exist yet (idempotent).
    
    Args:
        project_id: Project ID
        report_id: Report ID (realizationreport_id from API, same as in wb_finance_reports)
        line_id: Line ID (rrd_id from API, unique identifier for the line within report)
        payload: Raw line payload from API
        
    Returns:
        True if inserted, False if already exists (skipped)
    """
    payload_hash = compute_payload_hash(payload) if payload is not None else ""
    payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else "{}"

    with engine.begin() as conn:
        # Try to insert, ignore if conflict
        # Unique constraint: (project_id, report_id, line_id)
        result = conn.execute(
            text("""
                INSERT INTO wb_finance_report_lines (
                    project_id,
                    report_id,
                    line_id,
                    line_uid,
                    payload,
                    payload_hash
                )
                VALUES (
                    :project_id,
                    :report_id,
                    :line_id,
                    :line_uid,
                    CAST(:payload AS jsonb),
                    :payload_hash
                )
                ON CONFLICT (project_id, report_id, line_id) DO NOTHING
                RETURNING id
            """),
            {
                "project_id": project_id,
                "report_id": report_id,
                "line_id": line_id,
                "line_uid": payload_hash,  # Keep line_uid for backward compatibility, use hash
                "payload": payload_json,
                "payload_hash": payload_hash,
            },
        )
        inserted_id = result.scalar_one_or_none()
        return inserted_id is not None


def list_reports(
    project_id: int,
    marketplace_code: str = "wildberries",
) -> List[Dict[str, Any]]:
    """List all finance reports for a project.
    
    Args:
        project_id: Project ID
        marketplace_code: Marketplace code (default 'wildberries')
        
    Returns:
        List of report headers, sorted by last_seen_at desc
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    report_id,
                    period_from,
                    period_to,
                    currency,
                    total_amount,
                    rows_count,
                    first_seen_at,
                    last_seen_at
                FROM wb_finance_reports
                WHERE project_id = :project_id
                  AND marketplace_code = :marketplace_code
                ORDER BY last_seen_at DESC
            """),
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
            },
        ).mappings().all()

        return [dict(row) for row in rows]


def get_latest_report(
    project_id: int,
    marketplace_code: str = "wildberries",
) -> Optional[Dict[str, Any]]:
    """Get the latest finance report by period_to DESC (fallback: last_seen_at DESC).

    Returns:
        Single report dict or None if no reports
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT
                    report_id,
                    period_from,
                    period_to,
                    currency,
                    total_amount,
                    rows_count,
                    first_seen_at,
                    last_seen_at
                FROM wb_finance_reports
                WHERE project_id = :project_id
                  AND marketplace_code = :marketplace_code
                ORDER BY
                    period_to DESC NULLS LAST,
                    last_seen_at DESC NULLS LAST,
                    report_id DESC
                LIMIT 1
            """),
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
            },
        ).mappings().first()
        return dict(row) if row else None


def search_reports(
    project_id: int,
    query: str,
    limit: int = 20,
    marketplace_code: str = "wildberries",
) -> List[Dict[str, Any]]:
    """Search finance reports for autocomplete.
    Matches report_id, period_from, period_to, last_seen_at.
    """
    if not query or not query.strip():
        return list_reports(project_id=project_id, marketplace_code=marketplace_code)[:limit]
    q = f"%{query.strip()}%"
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    report_id,
                    period_from,
                    period_to,
                    currency,
                    total_amount,
                    rows_count,
                    first_seen_at,
                    last_seen_at
                FROM wb_finance_reports
                WHERE project_id = :project_id
                  AND marketplace_code = :marketplace_code
                  AND (
                    report_id::text ILIKE :q
                    OR period_from::text ILIKE :q
                    OR period_to::text ILIKE :q
                    OR last_seen_at::text ILIKE :q
                  )
                ORDER BY last_seen_at DESC
                LIMIT :limit
            """),
            {"project_id": project_id, "marketplace_code": marketplace_code, "q": q, "limit": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


__all__ = [
    "compute_payload_hash",
    "upsert_report_header",
    "insert_report_line_if_new",
    "list_reports",
    "get_latest_report",
    "search_reports",
]
