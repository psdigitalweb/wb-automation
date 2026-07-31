from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.db_wb_funnel_imports import import_funnel_report
from app.services.wb_funnel_report_parser import ParsedWBFunnelReport, WBFunnelReportRow


def _report() -> ParsedWBFunnelReport:
    return ParsedWBFunnelReport(
        source_type="xlsx",
        content_sha256="a" * 64,
        rows=(
            WBFunnelReportRow(
                row_number=3,
                nm_id=123,
                stat_date=date(2026, 7, 21),
                vendor_code="SKU",
                product_name="Title",
                is_deleted=False,
                impressions=100,
                card_clicks=14,
                reported_ctr=Decimal("14"),
                quality_status="ok",
                quality_flags=(),
                source_payload={"Показы": 100},
            ),
        ),
    )


def test_duplicate_content_short_circuits_without_writes():
    conn = MagicMock()
    duplicate = {
        "id": 7,
        "original_filename": "old.xlsx",
        "source_type": "xlsx",
        "period_from": date(2026, 7, 21),
        "period_to": date(2026, 7, 21),
        "rows_total": 1,
        "quality_summary": {},
        "created_at": None,
        "completed_at": None,
    }
    conn.execute.return_value.mappings.return_value.first.return_value = duplicate

    @contextmanager
    def begin():
        yield conn

    with patch("app.db_wb_funnel_imports.engine.begin", begin), patch(
        "app.db_wb_funnel_imports.resolve_marketplace_product_ids",
        return_value={"123": 987},
    ):
        result = import_funnel_report(
            project_id=1,
            original_filename="same.zip",
            created_by_user_id=1,
            report=_report(),
        )

    assert result["duplicate"] is True
    assert conn.execute.call_count == 1


def test_import_upsert_replaces_only_ctr_enrichment_on_overlap():
    conn = MagicMock()
    duplicate_result = MagicMock()
    duplicate_result.mappings.return_value.first.return_value = None
    import_result = MagicMock()
    import_result.scalar_one.return_value = 11
    conn.execute.side_effect = [duplicate_result, import_result, MagicMock(), MagicMock()]

    @contextmanager
    def begin():
        yield conn

    with patch("app.db_wb_funnel_imports.engine.begin", begin), patch(
        "app.db_wb_funnel_imports.resolve_marketplace_product_ids",
        return_value={"123": 987},
    ):
        result = import_funnel_report(
            project_id=1,
            original_filename="new.xlsx",
            created_by_user_id=1,
            report=_report(),
        )

    canonical_sql = str(conn.execute.call_args_list[3].args[0])
    assert "INSERT INTO wb_funnel_ctr_daily" in canonical_sql
    assert "ON CONFLICT (project_id, nm_id, stat_date) DO UPDATE" in canonical_sql
    assert "marketplace_product_id" in canonical_sql
    assert conn.execute.call_args_list[3].args[1][0]["marketplace_product_id"] == 987
    assert "wb_card_stats_daily" not in canonical_sql
    assert result["id"] == 11
