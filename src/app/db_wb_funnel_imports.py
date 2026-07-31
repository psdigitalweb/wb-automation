"""Persistence for WB funnel report imports and CTR enrichment."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.wb_funnel_report_parser import ParsedWBFunnelReport


def import_funnel_report(
    *,
    project_id: int,
    original_filename: str,
    created_by_user_id: int | None,
    report: ParsedWBFunnelReport,
) -> dict[str, Any]:
    """Persist immutable source rows and replace only canonical CTR enrichment fields."""
    with engine.begin() as conn:
        duplicate = conn.execute(
            text(
                """
                SELECT id, original_filename, source_type, period_from, period_to,
                       rows_total, quality_summary, created_at, completed_at
                FROM wb_funnel_report_imports
                WHERE project_id = :project_id AND content_sha256 = :content_sha256
                  AND status = 'completed'
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"project_id": project_id, "content_sha256": report.content_sha256},
        ).mappings().first()
        if duplicate:
            return {**dict(duplicate), "duplicate": True}

        dates = [row.stat_date for row in report.rows]
        flag_counts = Counter(flag for row in report.rows for flag in row.quality_flags)
        quality_summary = {
            "flag_counts": dict(sorted(flag_counts.items())),
            "warning_rows": sum(row.quality_status != "ok" for row in report.rows),
        }
        import_id = conn.execute(
            text(
                """
                INSERT INTO wb_funnel_report_imports (
                    project_id, original_filename, source_type, content_sha256, status,
                    period_from, period_to, rows_total, quality_summary,
                    created_by_user_id, completed_at
                ) VALUES (
                    :project_id, :original_filename, :source_type, :content_sha256, 'completed',
                    :period_from, :period_to, :rows_total, CAST(:quality_summary AS jsonb),
                    :created_by_user_id, NOW()
                ) RETURNING id
                """
            ),
            {
                "project_id": project_id,
                "original_filename": original_filename,
                "source_type": report.source_type,
                "content_sha256": report.content_sha256,
                "period_from": min(dates),
                "period_to": max(dates),
                "rows_total": len(report.rows),
                "quality_summary": json.dumps(quality_summary, ensure_ascii=False),
                "created_by_user_id": created_by_user_id,
            },
        ).scalar_one()

        raw_sql = text(
            """
            INSERT INTO wb_funnel_report_rows (
                import_id, project_id, row_number, nm_id, stat_date, vendor_code,
                product_name, is_deleted, impressions, card_clicks, reported_ctr,
                quality_status, quality_flags, source_payload
            ) VALUES (
                :import_id, :project_id, :row_number, :nm_id, :stat_date, :vendor_code,
                :product_name, :is_deleted, :impressions, :card_clicks, :reported_ctr,
                :quality_status, :quality_flags, CAST(:source_payload AS jsonb)
            )
            """
        )
        canonical_sql = text(
            """
            INSERT INTO wb_funnel_ctr_daily (
                project_id, nm_id, stat_date, impressions, card_clicks, reported_ctr,
                is_deleted, quality_status, quality_flags, last_import_id
            ) VALUES (
                :project_id, :nm_id, :stat_date, :impressions, :card_clicks, :reported_ctr,
                :is_deleted, :quality_status, :quality_flags, :import_id
            )
            ON CONFLICT (project_id, nm_id, stat_date) DO UPDATE SET
                impressions = EXCLUDED.impressions,
                card_clicks = EXCLUDED.card_clicks,
                reported_ctr = EXCLUDED.reported_ctr,
                is_deleted = EXCLUDED.is_deleted,
                quality_status = EXCLUDED.quality_status,
                quality_flags = EXCLUDED.quality_flags,
                last_import_id = EXCLUDED.last_import_id,
                updated_at = NOW()
            """
        )
        params_rows = []
        for row in report.rows:
            params_rows.append({
                "import_id": import_id,
                "project_id": project_id,
                "row_number": row.row_number,
                "nm_id": row.nm_id,
                "stat_date": row.stat_date,
                "vendor_code": row.vendor_code,
                "product_name": row.product_name,
                "is_deleted": row.is_deleted,
                "impressions": row.impressions,
                "card_clicks": row.card_clicks,
                "reported_ctr": row.reported_ctr,
                "quality_status": row.quality_status,
                "quality_flags": list(row.quality_flags),
                "source_payload": json.dumps(row.source_payload, ensure_ascii=False),
            })
        for start in range(0, len(params_rows), 500):
            batch = params_rows[start : start + 500]
            conn.execute(raw_sql, batch)
            conn.execute(canonical_sql, batch)

        return {
            "id": int(import_id),
            "original_filename": original_filename,
            "source_type": report.source_type,
            "period_from": min(dates),
            "period_to": max(dates),
            "rows_total": len(report.rows),
            "quality_summary": quality_summary,
            "duplicate": False,
        }


def list_funnel_report_imports(project_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, original_filename, source_type, status, period_from, period_to,
                       rows_total, quality_summary, created_at, completed_at
                FROM wb_funnel_report_imports
                WHERE project_id = :project_id
                ORDER BY id DESC LIMIT :limit
                """
            ),
            {"project_id": project_id, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]
