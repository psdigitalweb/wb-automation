#!/usr/bin/env python3
"""Verify WB finance report pagination: compare raw count vs DB after ingestion.

Usage:
    # 1) Fetch raw first (creates /tmp/wb_report_499328737_raw.jsonl.gz)
    python scripts/audit_wb_report_499328737_raw.py

    # 2) Run verification (runs ingestion, then compares)
    python scripts/verify_wb_finance_report_pagination.py --report-id 499328737 --project-id 1

Or with explicit expected (skip raw file):
    python scripts/verify_wb_finance_report_pagination.py --report-id 499328737 --project-id 1 --expected 14531

In Docker:
    docker compose -f infra/docker/docker-compose.yml exec api python /app/scripts/verify_wb_finance_report_pagination.py --report-id 499328737 --project-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DEFAULT_RAW_PATH = "/tmp/wb_report_499328737_raw.jsonl.gz"


def get_period_from_db(report_id: int) -> tuple[str, str] | None:
    """Get date_from, date_to for report from wb_finance_reports."""
    from sqlalchemy import text
    from app.db import engine

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT period_from, period_to FROM wb_finance_reports "
                "WHERE report_id = :rid LIMIT 1"
            ),
            {"rid": report_id},
        ).fetchone()
        if row and row[0] and row[1]:
            return (str(row[0]), str(row[1]))
    return None


def count_raw_lines(path: str) -> int:
    """Count lines in raw gzipped JSONL. Audit file contains one report only."""
    count = 0
    import json

    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def get_db_count(report_id: int) -> int:
    """Get row count from wb_finance_report_lines."""
    from sqlalchemy import text
    from app.db import engine

    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT COUNT(*) FROM wb_finance_report_lines WHERE report_id = :rid"
            ),
            {"rid": report_id},
        ).scalar()


def main():
    parser = argparse.ArgumentParser(
        description="Verify WB finance report pagination: raw vs DB after ingestion"
    )
    parser.add_argument("--report-id", type=int, required=True, help="WB report_id (realizationreport_id)")
    parser.add_argument("--project-id", type=int, default=1, help="Project ID")
    parser.add_argument(
        "--raw-file",
        type=str,
        default=DEFAULT_RAW_PATH,
        help="Path to raw JSONL.gz (from audit script)",
    )
    parser.add_argument(
        "--expected",
        type=int,
        default=None,
        help="Expected row count (skips raw file read)",
    )
    parser.add_argument("--skip-ingest", action="store_true", help="Only compare, do not run ingestion")
    parser.add_argument("--period-from", type=str, help="Override period start YYYY-MM-DD")
    parser.add_argument("--period-to", type=str, help="Override period end YYYY-MM-DD")
    args = parser.parse_args()

    report_id = args.report_id
    project_id = args.project_id

    # Resolve expected count
    if args.expected is not None:
        total_rows_raw = args.expected
        print(f"Using --expected: {total_rows_raw}")
    else:
        path = args.raw_file
        if not Path(path).exists():
            print(f"ERROR: Raw file not found: {path}")
            print("Run audit first: python scripts/audit_wb_report_499328737_raw.py")
            print("Or provide --expected N")
            sys.exit(1)
        total_rows_raw = count_raw_lines(path)
        print(f"Raw file {path}: total_rows_raw (report_id={report_id}) = {total_rows_raw}")

    if not args.skip_ingest:
        period = get_period_from_db(report_id)
        if period:
            date_from_str, date_to_str = period
        elif args.period_from and args.period_to:
            date_from_str, date_to_str = args.period_from, args.period_to
        else:
            print(
                f"ERROR: Report {report_id} not in wb_finance_reports. "
                "Provide --period-from and --period-to, or run ingestion for the period first."
            )
            sys.exit(1)
        date_from = date.fromisoformat(date_from_str)
        date_to = date.fromisoformat(date_to_str)
        print(f"Running ingestion: project_id={project_id} {date_from}..{date_to}")

        from app.ingest_wb_finances import ingest_wb_finance_reports_by_period

        result = asyncio.run(
            ingest_wb_finance_reports_by_period(
                project_id=project_id,
                date_from=date_from,
                date_to=date_to,
            )
        )
        if result.get("error"):
            print(f"Ingestion error: {result['error']}")
            sys.exit(1)
        print(f"Ingestion: inserted={result.get('inserted_lines')} skipped={result.get('skipped_lines')}")
    else:
        print("Skipping ingestion (--skip-ingest)")

    total_rows_db = get_db_count(report_id)
    print(f"DB count (report_id={report_id}): {total_rows_db}")

    delta = total_rows_raw - total_rows_db
    print()
    print("=" * 50)
    if delta == 0:
        print("PASS: raw == db")
    else:
        print(f"FAIL: raw={total_rows_raw} db={total_rows_db} delta={delta}")
    print("=" * 50)
    sys.exit(0 if delta == 0 else 1)


if __name__ == "__main__":
    main()
