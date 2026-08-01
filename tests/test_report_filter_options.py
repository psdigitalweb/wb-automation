from __future__ import annotations

from datetime import date

import pytest

from app.services import report_filter_options as service


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Connection:
    def execute(self, statement, params):
        sql = str(statement)
        if "wb_card_stats_daily" in sql:
            return _ScalarResult(
                [date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 25), date(2026, 7, 26)]
            )
        if "wb_funnel_ctr_daily" in sql:
            return _ScalarResult([date(2026, 7, 25)])
        if "wb_showcase_price_snapshots" in sql:
            return _ScalarResult([date(2026, 7, 26)])
        if "wb_feedback_snapshots" in sql:
            return _ScalarResult([])
        raise AssertionError(sql)


class _Connect:
    def __enter__(self):
        return _Connection()

    def __exit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def connect(self):
        return _Connect()


def test_catalog_period_uses_latest_continuous_primary_segment(monkeypatch) -> None:
    monkeypatch.setattr(service, "engine", _Engine())

    result = service.get_report_filter_options(3, "catalog")

    assert result.primary_dataset == "wb_card_stats_daily"
    assert result.date_filter.min_date == date(2026, 7, 20)
    assert result.date_filter.max_date == date(2026, 7, 26)
    assert result.date_filter.default_from == date(2026, 7, 25)
    assert result.date_filter.default_to == date(2026, 7, 26)
    assert [(segment.start, segment.end) for segment in result.date_filter.segments] == [
        (date(2026, 7, 20), date(2026, 7, 21)),
        (date(2026, 7, 25), date(2026, 7, 26)),
    ]
    assert [dataset.role for dataset in result.datasets] == [
        "primary",
        "supplementary",
        "supplementary",
        "supplementary",
    ]


def test_report_without_primary_data_disables_date_filter(monkeypatch) -> None:
    class EmptyConnection(_Connection):
        def execute(self, statement, params):
            return _ScalarResult([])

    class EmptyEngine(_Engine):
        def connect(self):
            class EmptyConnect(_Connect):
                def __enter__(self):
                    return EmptyConnection()

            return EmptyConnect()

    monkeypatch.setattr(service, "engine", EmptyEngine())

    result = service.get_report_filter_options(3, "reviews")

    assert result.date_filter.enabled is False
    assert result.date_filter.default_from is None
    assert result.date_filter.default_to is None


def test_event_report_default_uses_calendar_window_across_days_without_events(monkeypatch) -> None:
    class ReviewsConnection(_Connection):
        def execute(self, statement, params):
            sql = str(statement)
            if "wb_feedback_snapshots" in sql:
                return _ScalarResult([date(2026, 6, 1), date(2026, 7, 10), date(2026, 7, 30)])
            raise AssertionError(sql)

    class ReviewsEngine(_Engine):
        def connect(self):
            class ReviewsConnect(_Connect):
                def __enter__(self):
                    return ReviewsConnection()

            return ReviewsConnect()

    monkeypatch.setattr(service, "engine", ReviewsEngine())

    result = service.get_report_filter_options(3, "reviews")

    assert result.date_filter.default_from == date(2026, 7, 1)
    assert result.date_filter.default_to == date(2026, 7, 30)


def test_validate_report_period_accepts_period_with_primary_data(monkeypatch) -> None:
    monkeypatch.setattr(service, "engine", _Engine())

    service.validate_report_period(3, "catalog", date(2026, 7, 20), date(2026, 7, 21))


def test_validate_report_period_rejects_outside_available_range(monkeypatch) -> None:
    monkeypatch.setattr(service, "engine", _Engine())

    with pytest.raises(service.ReportPeriodUnavailableError) as caught:
        service.validate_report_period(3, "catalog", date(2026, 7, 3), date(2026, 7, 26))

    assert caught.value.detail == {
        "code": "report_period_unavailable",
        "report_code": "catalog",
        "primary_dataset": "wb_card_stats_daily",
        "requested_from": "2026-07-03",
        "requested_to": "2026-07-26",
        "available_from": "2026-07-20",
        "available_to": "2026-07-26",
        "reason": "outside_available_range",
        "message": "Requested period is outside the available data range",
    }


def test_validate_report_period_rejects_gap_without_primary_data(monkeypatch) -> None:
    monkeypatch.setattr(service, "engine", _Engine())

    with pytest.raises(service.ReportPeriodUnavailableError) as caught:
        service.validate_report_period(3, "catalog", date(2026, 7, 22), date(2026, 7, 24))

    assert caught.value.detail["reason"] == "no_data_in_period"
