"""DB layer for wb_financial_events, reconciliations, allocations."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def upsert_event(
    project_id: int,
    report_id: Optional[int],
    line_id: Optional[int],
    line_uid_surrogate: Optional[str],
    event_date: Optional[date],
    event_date_quality: str,
    period_from: Optional[date],
    period_to: Optional[date],
    nm_id: Optional[int],
    vendor_code: Optional[str],
    internal_sku: Optional[str],
    event_type: str,
    scope: str,
    amount: float,
    currency: str,
    source_field: str,
    payload_hash: str,
) -> bool:
    """Upsert event. Returns True if inserted, False if updated."""
    now = datetime.utcnow()
    with engine.begin() as conn:
        if line_id is not None:
            result = conn.execute(
                text("""
                    INSERT INTO wb_financial_events (
                        project_id, marketplace_code, report_id, line_id, line_uid_surrogate,
                        event_date, event_date_quality, period_from, period_to,
                        nm_id, vendor_code, internal_sku, event_type, scope,
                        amount, currency, source_field, payload_hash,
                        created_at, updated_at
                    ) VALUES (
                        :project_id, 'wildberries', :report_id, :line_id, NULL,
                        :event_date, :event_date_quality, :period_from, :period_to,
                        :nm_id, :vendor_code, :internal_sku, :event_type, :scope,
                        :amount, :currency, :source_field, :payload_hash,
                        :now, :now
                    )
                    ON CONFLICT (project_id, report_id, line_id, event_type, source_field)
                    WHERE line_id IS NOT NULL
                    DO UPDATE SET
                        amount = EXCLUDED.amount,
                        payload_hash = EXCLUDED.payload_hash,
                        event_date = EXCLUDED.event_date,
                        event_date_quality = EXCLUDED.event_date_quality,
                        internal_sku = EXCLUDED.internal_sku,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_id": line_id,
                    "event_date": event_date,
                    "event_date_quality": event_date_quality,
                    "period_from": period_from,
                    "period_to": period_to,
                    "nm_id": nm_id,
                    "vendor_code": vendor_code,
                    "internal_sku": internal_sku,
                    "event_type": event_type,
                    "scope": scope,
                    "amount": amount,
                    "currency": currency,
                    "source_field": source_field,
                    "payload_hash": payload_hash,
                    "now": now,
                },
            )
        else:
            if not line_uid_surrogate:
                return False
            result = conn.execute(
                text("""
                    INSERT INTO wb_financial_events (
                        project_id, marketplace_code, report_id, line_id, line_uid_surrogate,
                        event_date, event_date_quality, period_from, period_to,
                        nm_id, vendor_code, internal_sku, event_type, scope,
                        amount, currency, source_field, payload_hash,
                        created_at, updated_at
                    ) VALUES (
                        :project_id, 'wildberries', :report_id, NULL, :line_uid_surrogate,
                        :event_date, :event_date_quality, :period_from, :period_to,
                        :nm_id, :vendor_code, :internal_sku, :event_type, :scope,
                        :amount, :currency, :source_field, :payload_hash,
                        :now, :now
                    )
                    ON CONFLICT (project_id, report_id, line_uid_surrogate, event_type, source_field)
                    WHERE line_id IS NULL AND line_uid_surrogate IS NOT NULL
                    DO UPDATE SET
                        amount = EXCLUDED.amount,
                        payload_hash = EXCLUDED.payload_hash,
                        event_date = EXCLUDED.event_date,
                        event_date_quality = EXCLUDED.event_date_quality,
                        internal_sku = EXCLUDED.internal_sku,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_uid_surrogate": line_uid_surrogate,
                    "event_date": event_date,
                    "event_date_quality": event_date_quality,
                    "period_from": period_from,
                    "period_to": period_to,
                    "nm_id": nm_id,
                    "vendor_code": vendor_code,
                    "internal_sku": internal_sku,
                    "event_type": event_type,
                    "scope": scope,
                    "amount": amount,
                    "currency": currency,
                    "source_field": source_field,
                    "payload_hash": payload_hash,
                    "now": now,
                },
            )
        return True


def delete_events_for_line(
    project_id: int,
    report_id: Optional[int],
    line_id: Optional[int],
    line_uid_surrogate: Optional[str],
) -> int:
    """Delete all events for given line. Returns deleted count."""
    with engine.begin() as conn:
        if line_id is not None:
            result = conn.execute(
                text("""
                    DELETE FROM wb_financial_events
                    WHERE project_id = :project_id
                      AND report_id = :report_id
                      AND line_id = :line_id
                """),
                {"project_id": project_id, "report_id": report_id, "line_id": line_id},
            )
        elif line_uid_surrogate:
            result = conn.execute(
                text("""
                    DELETE FROM wb_financial_events
                    WHERE project_id = :project_id
                      AND report_id = :report_id
                      AND line_id IS NULL
                      AND line_uid_surrogate = :line_uid_surrogate
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_uid_surrogate": line_uid_surrogate,
                },
            )
        else:
            return 0
        return result.rowcount or 0


def get_existing_payload_hash(
    project_id: int,
    report_id: Optional[int],
    line_id: Optional[int],
    line_uid_surrogate: Optional[str],
) -> Optional[str]:
    """Get payload_hash of existing events for this line. Returns None if no events."""
    with engine.connect() as conn:
        if line_id is not None:
            row = conn.execute(
                text("""
                    SELECT payload_hash FROM wb_financial_events
                    WHERE project_id = :project_id AND report_id = :report_id AND line_id = :line_id
                    LIMIT 1
                """),
                {"project_id": project_id, "report_id": report_id, "line_id": line_id},
            ).mappings().first()
        elif line_uid_surrogate:
            row = conn.execute(
                text("""
                    SELECT payload_hash FROM wb_financial_events
                    WHERE project_id = :project_id AND report_id = :report_id
                      AND line_id IS NULL AND line_uid_surrogate = :line_uid_surrogate
                    LIMIT 1
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_uid_surrogate": line_uid_surrogate,
                },
            ).mappings().first()
        else:
            return None
    return row["payload_hash"] if row else None


def get_events_sum_by_report(
    project_id: int, report_ids: List[int]
) -> Dict[int, float]:
    """Sum events.amount by report_id. Returns {report_id: sum}."""
    if not report_ids:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT report_id, COALESCE(SUM(amount), 0) AS total
                FROM wb_financial_events
                WHERE project_id = :project_id
                  AND report_id = ANY(:report_ids)
                GROUP BY report_id
            """),
            {"project_id": project_id, "report_ids": report_ids},
        ).mappings().all()
    return {int(r["report_id"]): float(r["total"]) for r in rows}


def insert_reconciliation(
    project_id: int,
    period_from: Optional[date],
    period_to: Optional[date],
    report_id: Optional[int],
    source: str,
    metric: str,
    value: Optional[float],
    details_json: Optional[Dict[str, Any]],
) -> None:
    """Insert reconciliation record."""
    import json

    with engine.begin() as conn:
        details_str = (
            json.dumps(details_json, ensure_ascii=False) if details_json is not None else None
        )
        conn.execute(
            text("""
                INSERT INTO wb_financial_reconciliations
                (project_id, period_from, period_to, report_id, source, metric, value, details_json)
                VALUES (:project_id, :period_from, :period_to, :report_id, :source, :metric, :value,
                    CASE WHEN :details_str IS NOT NULL THEN CAST(:details_str AS jsonb) ELSE NULL END)
            """),
            {
                "project_id": project_id,
                "period_from": period_from,
                "period_to": period_to,
                "report_id": report_id,
                "source": source,
                "metric": metric,
                "value": value,
                "details_str": details_str,
            },
        )
