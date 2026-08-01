from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Literal

from sqlalchemy import text

from app.db import engine
from app.schemas.data_availability import CoverageSegment
from app.schemas.report_filter_options import (
    ReportDatasetCoverage,
    ReportDateFilterOptions,
    ReportFilterOptionsResponse,
)


@dataclass(frozen=True)
class DatasetDefinition:
    code: str
    title: str
    sql: str


@dataclass(frozen=True)
class ReportDefinition:
    primary: str
    supplementary: tuple[str, ...] = ()
    default_days: int = 30
    require_continuous_default: bool = True


DATASETS: Dict[str, DatasetDefinition] = {
    "wb_card_stats_daily": DatasetDefinition(
        "wb_card_stats_daily",
        "Воронка и заказы",
        "SELECT DISTINCT stat_date AS d FROM wb_card_stats_daily WHERE project_id = :project_id",
    ),
    "wb_funnel_ctr_daily": DatasetDefinition(
        "wb_funnel_ctr_daily",
        "Показы и переходы",
        "SELECT DISTINCT stat_date AS d FROM wb_funnel_ctr_daily WHERE project_id = :project_id AND NOT is_deleted",
    ),
    "wb_showcase_price_snapshots": DatasetDefinition(
        "wb_showcase_price_snapshots",
        "Цена витрины и СПП",
        "SELECT DISTINCT snapshot_at::date AS d FROM wb_showcase_price_snapshots WHERE project_id = :project_id",
    ),
    "wb_feedback_created": DatasetDefinition(
        "wb_feedback_created",
        "Отзывы по дате создания",
        "SELECT DISTINCT created_date::date AS d FROM wb_feedback_snapshots WHERE project_id = :project_id AND created_date IS NOT NULL",
    ),
    "wb_finance_line_dates": DatasetDefinition(
        "wb_finance_line_dates",
        "Строки финансовых отчётов",
        """
        SELECT DISTINCT COALESCE(
            CASE WHEN payload->>'rr_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(payload->>'rr_dt', 10)::date END,
            CASE WHEN payload->>'sale_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(payload->>'sale_dt', 10)::date END,
            CASE WHEN payload->>'order_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(payload->>'order_dt', 10)::date END
        ) AS d
        FROM wb_finance_report_lines
        WHERE project_id = :project_id
        """,
    ),
}


REPORTS: Dict[str, ReportDefinition] = {
    "catalog": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily", "wb_showcase_price_snapshots", "wb_feedback_created"), 30),
    "catalog-product": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily", "wb_showcase_price_snapshots", "wb_feedback_created"), 30),
    "content-analytics": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily",), 30),
    "funnel-signals": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily",), 30),
    "product-groups": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily", "wb_showcase_price_snapshots"), 30),
    "sales-trends": ReportDefinition("wb_card_stats_daily", ("wb_funnel_ctr_daily",), 90),
    "reviews": ReportDefinition("wb_feedback_created", (), 30, False),
    "spp-dynamics": ReportDefinition("wb_showcase_price_snapshots", (), 30),
    "order-geography": ReportDefinition("wb_finance_line_dates", (), 30),
    "finances-sku-pnl": ReportDefinition("wb_finance_line_dates", (), 30),
}


class ReportPeriodUnavailableError(ValueError):
    def __init__(self, detail: Dict[str, Any]):
        super().__init__(str(detail.get("message") or "Report period is unavailable"))
        self.detail = detail


def _segments(values: List[date]) -> List[CoverageSegment]:
    if not values:
        return []
    ordered = sorted(set(values))
    start = previous = ordered[0]
    count = 1
    result: List[CoverageSegment] = []
    for value in ordered[1:]:
        if value == previous + timedelta(days=1):
            previous = value
            count += 1
            continue
        result.append(CoverageSegment(start=start, end=previous, count=count))
        start = previous = value
        count = 1
    result.append(CoverageSegment(start=start, end=previous, count=count))
    return result


def validate_report_period(project_id: int, report_code: str, period_from: date, period_to: date) -> None:
    report = REPORTS.get(report_code)
    if report is None:
        raise KeyError(report_code)
    if period_from > period_to:
        raise ReportPeriodUnavailableError(
            {
                "code": "report_period_unavailable",
                "report_code": report_code,
                "primary_dataset": report.primary,
                "requested_from": period_from.isoformat(),
                "requested_to": period_to.isoformat(),
                "available_from": None,
                "available_to": None,
                "reason": "invalid_range",
                "message": "Period start must be before or equal to period end",
            }
        )
    definition = DATASETS[report.primary]
    with engine.connect() as conn:
        values = [
            value
            for value in conn.execute(text(definition.sql), {"project_id": int(project_id)}).scalars().all()
            if isinstance(value, date)
        ]

    ordered = sorted(set(values))
    segments = _segments(ordered)
    available_from = ordered[0] if ordered else None
    available_to = ordered[-1] if ordered else None
    base_detail: Dict[str, Any] = {
        "code": "report_period_unavailable",
        "report_code": report_code,
        "primary_dataset": report.primary,
        "requested_from": period_from.isoformat(),
        "requested_to": period_to.isoformat(),
        "available_from": available_from.isoformat() if available_from else None,
        "available_to": available_to.isoformat() if available_to else None,
    }
    if not ordered:
        raise ReportPeriodUnavailableError(
            {**base_detail, "reason": "no_primary_data", "message": "No primary data is available for this report"}
        )
    if period_from < available_from or period_to > available_to:
        raise ReportPeriodUnavailableError(
            {**base_detail, "reason": "outside_available_range", "message": "Requested period is outside the available data range"}
        )
    if not any(segment.start <= period_to and segment.end >= period_from for segment in segments):
        raise ReportPeriodUnavailableError(
            {**base_detail, "reason": "no_data_in_period", "message": "Primary data is absent in the requested period"}
        )


def get_report_filter_options(project_id: int, report_code: str) -> ReportFilterOptionsResponse:
    report = REPORTS.get(report_code)
    if report is None:
        raise KeyError(report_code)

    codes = (report.primary, *report.supplementary)
    coverage: List[ReportDatasetCoverage] = []
    dates_by_code: Dict[str, List[date]] = {}
    with engine.connect() as conn:
        for code in codes:
            definition = DATASETS[code]
            values = [
                value
                for value in conn.execute(text(definition.sql), {"project_id": int(project_id)}).scalars().all()
                if isinstance(value, date)
            ]
            dates_by_code[code] = values
            segments = _segments(values)
            coverage.append(
                ReportDatasetCoverage(
                    code=code,
                    title=definition.title,
                    role="primary" if code == report.primary else "supplementary",
                    min_date=min(values) if values else None,
                    max_date=max(values) if values else None,
                    present_count=len(set(values)),
                    segments=segments,
                )
            )

    primary_dates = dates_by_code[report.primary]
    primary_segments = _segments(primary_dates)
    latest_segment = primary_segments[-1] if primary_segments else None
    default_to = max(primary_dates) if primary_dates else None
    if default_to is None:
        default_from = None
    elif report.require_continuous_default and latest_segment:
        default_from = max(latest_segment.start, default_to - timedelta(days=report.default_days - 1))
    else:
        default_from = max(min(primary_dates), default_to - timedelta(days=report.default_days - 1))
    return ReportFilterOptionsResponse(
        project_id=int(project_id),
        report_code=report_code,
        primary_dataset=report.primary,
        date_filter=ReportDateFilterOptions(
            enabled=bool(primary_dates),
            min_date=min(primary_dates) if primary_dates else None,
            max_date=max(primary_dates) if primary_dates else None,
            default_from=default_from,
            default_to=default_to,
            segments=primary_segments,
        ),
        datasets=coverage,
    )
