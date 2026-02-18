"""Ingestion routines for Wildberries Finance Reports (project-level)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional

from app.wb.finances_client import WBFinancesClient
from app.db_wb_finances import (
    upsert_report_header,
    insert_report_line_if_new,
    compute_payload_hash,
)
from app.utils.get_project_marketplace_token import get_wb_credentials_for_project


async def ingest_wb_finance_reports_by_period(
    project_id: int,
    date_from: date,
    date_to: date,
) -> Dict[str, Any]:
    """Fetch and store WB finance reports for a project and date range.
    
    Uses reportDetailByPeriod API endpoint and stores both report headers
    and individual report lines with idempotency.
    
    Args:
        project_id: Project ID
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        
    Returns:
        Dict with summary:
        - http_status: HTTP status code
        - total_reports: Total number of reports in response
        - inserted_reports: Number of new report headers inserted
        - updated_reports: Number of existing report headers updated
        - inserted_lines: Number of new lines inserted
        - skipped_lines: Number of lines skipped (already exist)
        - error: Error message if any
    """
    # Get WB token for project
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if not credentials or not credentials.get("token"):
            return {
                "http_status": 0,
                "total_reports": 0,
                "inserted_reports": 0,
                "updated_reports": 0,
                "inserted_lines": 0,
                "skipped_lines": 0,
                "error": "WB not connected or token missing",
            }
        token = credentials["token"]
    except ValueError as e:
        return {
            "http_status": 0,
            "total_reports": 0,
            "inserted_reports": 0,
            "updated_reports": 0,
            "inserted_lines": 0,
            "skipped_lines": 0,
            "error": str(e),
        }

    # Fetch from API with pagination (rrdid cursor)
    client = WBFinancesClient(token=token)
    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()
    limit = 100000
    max_batches = 1000
    rate_limit_sec = 60  # WB: 1 req/min

    reports_dict: Dict[int, List[Dict[str, Any]]] = {}
    rrdid_cursor = 0
    batch_idx = 0
    total_loaded = 0
    http_status = 200
    error: Optional[str] = None

    while True:
        batch_idx += 1
        if batch_idx > max_batches:
            raise RuntimeError(
                f"WB finances pagination: max_batches={max_batches} exceeded. "
                "Possible infinite loop or very large report."
            )

        response = await client.fetch_report_detail_by_period(
            date_from=date_from_str,
            date_to=date_to_str,
            rrdid=rrdid_cursor,
            limit=limit,
        )

        batch_status = response.get("http_status", 0)
        payload = response.get("payload")

        if batch_status not in (200, 204):
            error = f"HTTP {batch_status}"
            if payload and isinstance(payload, dict) and "error" in payload:
                error = f"HTTP {batch_status}: {payload.get('error')}"
            return {
                "http_status": batch_status,
                "total_reports": len(reports_dict),
                "inserted_reports": 0,
                "updated_reports": 0,
                "inserted_lines": 0,
                "skipped_lines": 0,
                "error": error,
            }

        if batch_status == 204 or not payload or not isinstance(payload, list):
            if batch_status == 204:
                print(f"ingest_wb_finance_reports_by_period: batch {batch_idx} 204 No data (done)")
            break

        lines = payload
        if not lines:
            break

        # Cursor from data: max(rrd_id) for next page
        max_rrd_id = None
        for line in lines:
            if isinstance(line, dict):
                for key in ("rrd_id", "rrdId"):
                    if key in line and line[key] is not None:
                        try:
                            vid = int(line[key])
                            if max_rrd_id is None or vid > max_rrd_id:
                                max_rrd_id = vid
                            break
                        except (ValueError, TypeError):
                            pass

        if max_rrd_id is not None and max_rrd_id == rrdid_cursor:
            raise RuntimeError(
                f"WB finances pagination stuck: new max(rrd_id)={max_rrd_id} == cursor={rrdid_cursor}. "
                "API may return same data repeatedly."
            )

        total_loaded += len(lines)
        print(
            f"ingest_wb_finance_reports_by_period: batch_idx={batch_idx} batch_size={len(lines)} "
            f"total_loaded={total_loaded} rrdid_cursor={rrdid_cursor} next_cursor={max_rrd_id}"
        )

        # Group lines by realizationreport_id (append to accumulated)
        for line in lines:
            if not isinstance(line, dict):
                continue

            report_id_value = None
            for key in ["realizationreport_id", "realizationReportId"]:
                if key in line and line[key] is not None:
                    try:
                        report_id_value = int(line[key])
                        break
                    except (ValueError, TypeError):
                        continue

            if report_id_value is None:
                print(
                    f"ingest_wb_finance_reports_by_period: skipping line without realizationreport_id: "
                    f"{list(line.keys())[:5]}"
                )
                continue

            if report_id_value not in reports_dict:
                reports_dict[report_id_value] = []
            reports_dict[report_id_value].append(line)

        rrdid_cursor = max_rrd_id if max_rrd_id is not None else rrdid_cursor

        if len(lines) < limit:
            break

        await asyncio.sleep(rate_limit_sec)

    # Process each report
    inserted_reports = 0
    updated_reports = 0
    inserted_lines = 0
    skipped_lines = 0
    
    for report_id, report_lines in reports_dict.items():
        # report_id here is realizationreport_id (ID of the report)
        # report_lines contains all lines (rows) that belong to this report
        
        # Extract report-level metadata from first line
        # (period_from, period_to, currency, etc.)
        first_line = report_lines[0]
        
        period_from_val = None
        period_to_val = None
        currency_val = None
        total_amount_val = None
        
        # Try common field names for dates
        for date_key in ["doc_date", "date_from", "period_from", "date", "report_date"]:
            if date_key in first_line and first_line[date_key]:
                try:
                    period_from_val = date.fromisoformat(str(first_line[date_key]).split("T")[0])
                    break
                except (ValueError, AttributeError):
                    continue
        
        for date_key in ["date_to", "period_to", "date_end", "end_date"]:
            if date_key in first_line and first_line[date_key]:
                try:
                    period_to_val = date.fromisoformat(str(first_line[date_key]).split("T")[0])
                    break
                except (ValueError, AttributeError):
                    continue
        
        # Currency
        for curr_key in ["currency", "currency_code", "valute"]:
            if curr_key in first_line and first_line[curr_key]:
                currency_val = str(first_line[curr_key])
                break
        
        # Total amount (if available at report level)
        # Usually this is sum of lines, but API might provide it
        for amount_key in ["total_amount", "total_sum", "sum_total", "amount_total"]:
            if amount_key in first_line and first_line[amount_key] is not None:
                try:
                    total_amount_val = float(first_line[amount_key])
                    break
                except (ValueError, TypeError):
                    continue
        
        # Create meta payload for report header (sample from first line)
        payload_meta = first_line
        
        # Upsert report header
        inserted, updated = upsert_report_header(
            project_id=project_id,
            report_id=report_id,
            marketplace_code="wildberries",
            period_from=period_from_val,
            period_to=period_to_val,
            currency=currency_val,
            total_amount=total_amount_val,
            rows_count=len(report_lines),
            payload_meta=payload_meta,
        )
        
        if inserted:
            inserted_reports += 1
        elif updated:
            updated_reports += 1
        
        # Insert lines with rrd_id as line_id
        for line in report_lines:
            # Extract rrd_id (line ID within the report)
            line_id_value = None
            for key in ["rrd_id", "rrdId"]:
                if key in line and line[key] is not None:
                    try:
                        line_id_value = int(line[key])
                        break
                    except (ValueError, TypeError):
                        continue
            
            if line_id_value is None:
                # Fallback: use hash if rrd_id not found (shouldn't happen in normal WB responses)
                print(f"ingest_wb_finance_reports_by_period: warning: line without rrd_id, using hash fallback")
                line_id_value = int(compute_payload_hash(line)[:15], 16)  # Use first 15 hex chars as int
            
            inserted_line = insert_report_line_if_new(
                project_id=project_id,
                report_id=report_id,
                line_id=line_id_value,
                payload=line,
            )
            
            if inserted_line:
                inserted_lines += 1
            else:
                skipped_lines += 1

    print(
        f"ingest_wb_finance_reports_by_period: project_id={project_id} "
        f"date_from={date_from_str} date_to={date_to_str} "
        f"reports={len(reports_dict)} "
        f"inserted_reports={inserted_reports} updated_reports={updated_reports} "
        f"inserted_lines={inserted_lines} skipped_lines={skipped_lines}"
    )

    return {
        "http_status": http_status,
        "total_reports": len(reports_dict),
        "inserted_reports": inserted_reports,
        "updated_reports": updated_reports,
        "inserted_lines": inserted_lines,
        "skipped_lines": skipped_lines,
        "error": error,
    }
