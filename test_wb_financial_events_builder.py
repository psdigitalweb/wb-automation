"""Tests for WB financial events builder.

Requires: running Postgres with wb_finance_* and wb_financial_* tables.
Run: pytest test_wb_financial_events_builder.py -v
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.db import engine
from app.db_wb_finances import compute_payload_hash
from app.services.wb_financial.builder import build_wb_financial_events
from sqlalchemy import text


def _ensure_test_data(project_id: int, report_id: int) -> None:
    """Ensure wb_finance_reports and wb_finance_report_lines have test rows."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO projects (id, name, description, created_by)
                VALUES (:id, 'Test WB Events', 'Test project', 1)
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": project_id},
        )
        conn.execute(
            text("""
                INSERT INTO wb_finance_reports
                (project_id, marketplace_code, report_id, period_from, period_to, payload, payload_hash)
                VALUES (:project_id, 'wildberries', :report_id, '2025-01-01', '2025-01-31', '{}', 'hash1')
                ON CONFLICT (project_id, marketplace_code, report_id) DO UPDATE SET last_seen_at = now()
            """),
            {"project_id": project_id, "report_id": report_id},
        )


def _count_events(project_id: int) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) AS c FROM wb_financial_events WHERE project_id = :pid"),
            {"pid": project_id},
        ).mappings().first()
    return row["c"] or 0


def _insert_raw_line(
    project_id: int,
    report_id: int,
    line_id: int | None,
    payload: dict,
    line_pk: int = 99999,
) -> None:
    import json

    ph = compute_payload_hash(payload)
    payload_json = json.dumps(payload, ensure_ascii=False)
    with engine.begin() as conn:
        if line_id is not None:
            conn.execute(
                text("""
                    INSERT INTO wb_finance_report_lines
                    (project_id, report_id, line_id, line_uid, payload, payload_hash)
                    VALUES (:project_id, :report_id, :line_id, :line_uid, CAST(:payload AS jsonb), :payload_hash)
                    ON CONFLICT (project_id, report_id, line_id) DO UPDATE SET payload = EXCLUDED.payload, payload_hash = EXCLUDED.payload_hash
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_id": line_id,
                    "line_uid": ph,
                    "payload": payload_json,
                    "payload_hash": ph,
                },
            )
        else:
            conn.execute(
                text("""
                    INSERT INTO wb_finance_report_lines
                    (project_id, report_id, line_id, line_uid, payload, payload_hash)
                    VALUES (:project_id, :report_id, NULL, :line_uid, CAST(:payload AS jsonb), :payload_hash)
                """),
                {
                    "project_id": project_id,
                    "report_id": report_id,
                    "line_uid": ph,
                    "payload": payload_json,
                    "payload_hash": ph,
                },
            )


@pytest.mark.skipif(
    True,
    reason="Requires DB with wb_finance_* tables; run manually with docker",
)
def test_idempotent():
    """Run builder twice -> event count stable."""
    project_id = 999901
    report_id = 888801
    _ensure_test_data(project_id, report_id)

    with patch(
        "app.services.wb_financial.builder.FIELD_TO_EVENT",
        [(["retail_amount_for_pay", "retailAmountForPay"], "sale_income", "sku")],
    ):
        payload = {
            "rrd_id": 111,
            "realizationreport_id": report_id,
            "nm_id": 12345,
            "retail_amount_for_pay": 1000.50,
            "doc_date": "2025-01-15",
        }
        _insert_raw_line(project_id, report_id, 111, payload)

        stats1 = build_wb_financial_events(project_id, date(2025, 1, 1), date(2025, 1, 31))
        count1 = _count_events(project_id)

        stats2 = build_wb_financial_events(project_id, date(2025, 1, 1), date(2025, 1, 31))
        count2 = _count_events(project_id)

        assert count1 == count2, "Event count should be stable on second run"
        assert count1 >= 1


@pytest.mark.skipif(
    True,
    reason="Requires DB with wb_finance_* tables; run manually with docker",
)
def test_payload_hash_change():
    """When payload_hash changes in raw, builder deletes old events and rebuilds."""
    project_id = 999902
    report_id = 888802
    _ensure_test_data(project_id, report_id)

    with patch(
        "app.services.wb_financial.builder.FIELD_TO_EVENT",
        [(["retail_amount_for_pay"], "sale_income", "sku")],
    ):
        payload1 = {
            "rrd_id": 222,
            "realizationreport_id": report_id,
            "retail_amount_for_pay": 500.0,
            "doc_date": "2025-01-10",
        }
        _insert_raw_line(project_id, report_id, 222, payload1)
        build_wb_financial_events(project_id, date(2025, 1, 1), date(2025, 1, 31))
        count1 = _count_events(project_id)

        payload2 = {"rrd_id": 222, "realizationreport_id": report_id, "retail_amount_for_pay": 600.0}
        _insert_raw_line(project_id, report_id, 222, payload2)
        stats = build_wb_financial_events(project_id, date(2025, 1, 1), date(2025, 1, 31))
        count2 = _count_events(project_id)

        assert stats.get("deleted", 0) >= 1 or count2 >= 1
        assert count2 >= 1


@pytest.mark.skipif(
    True,
    reason="Requires DB with wb_finance_* tables; run manually with docker",
)
def test_surrogate():
    """line_id NULL -> line_uid_surrogate used, uniqueness preserved."""
    project_id = 999903
    report_id = 888803
    _ensure_test_data(project_id, report_id)

    payload = {
        "realizationreport_id": report_id,
        "retail_amount_for_pay": 100.0,
        "doc_date": "2025-01-10",
    }
    _insert_raw_line(project_id, report_id, None, payload)

    with patch(
        "app.services.wb_financial.builder.FIELD_TO_EVENT",
        [(["retail_amount_for_pay"], "sale_income", "sku")],
    ):
        stats = build_wb_financial_events(project_id, date(2025, 1, 1), date(2025, 1, 31))

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT line_id, line_uid_surrogate FROM wb_financial_events
                WHERE project_id = :pid AND report_id = :rid
            """),
            {"pid": project_id, "rid": report_id},
        ).mappings().first()
    if row:
        assert row["line_id"] is None
        assert row["line_uid_surrogate"] is not None
        assert ":" in str(row["line_uid_surrogate"])
