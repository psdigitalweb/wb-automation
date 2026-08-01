from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from app.services.report_filter_options import ReportPeriodUnavailableError, validate_report_period


def enforce_report_period(project_id: int, report_code: str, period_from: date, period_to: date) -> None:
    try:
        validate_report_period(project_id, report_code, period_from, period_to)
    except ReportPeriodUnavailableError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
