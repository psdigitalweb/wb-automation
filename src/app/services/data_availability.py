"""Compute per-project data availability (presence) for last N days.

We intentionally avoid any ingest metadata and rely on facts in DB: "data exists or not".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Set

from sqlalchemy import bindparam, text

from app.db import engine
from app.schemas.data_availability import (
    CoverageSegment,
    DataAvailabilityResponse,
    DatasetAvailability,
    Grain,
)


def _safe_execute(conn, stmt, params: Optional[dict] = None):
    """Execute statement and rollback on error to avoid InFailedSqlTransaction."""
    try:
        return conn.execute(stmt, params or {})
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def _compress_periods(periods: Sequence[date], step_days: int) -> List[CoverageSegment]:
    if not periods:
        return []
    items = sorted(set(periods))
    seg_start = items[0]
    prev = items[0]
    count = 1
    segments: List[CoverageSegment] = []
    for d in items[1:]:
        if (d - prev).days == step_days:
            prev = d
            count += 1
            continue
        segments.append(CoverageSegment(start=seg_start, end=prev, count=count))
        seg_start = d
        prev = d
        count = 1
    segments.append(CoverageSegment(start=seg_start, end=prev, count=count))
    return segments


def _expected_periods(window_from: date, window_to: date, grain: Grain) -> List[date]:
    if grain == "day":
        days = (window_to - window_from).days
        return [window_from + timedelta(days=i) for i in range(days + 1)]
    if grain == "week":
        # Week key is Monday date (consistent with PostgreSQL date_trunc('week')).
        start = window_from - timedelta(days=window_from.weekday())
        end = window_to - timedelta(days=window_to.weekday())
        weeks = (end - start).days // 7
        return [start + timedelta(days=7 * i) for i in range(weeks + 1)]
    raise ValueError(f"Unsupported grain: {grain}")


def _build_dataset_availability(
    *,
    code: str,
    title: str,
    grain: Grain,
    window_from: date,
    window_to: date,
    present_periods: Sequence[date],
    note: Optional[str] = None,
) -> DatasetAvailability:
    expected = _expected_periods(window_from, window_to, grain)
    present_set: Set[date] = set(present_periods)
    present_sorted = sorted(present_set)
    missing_sorted = [d for d in expected if d not in present_set]

    step = 1 if grain == "day" else 7
    present_segments = _compress_periods(present_sorted, step_days=step)
    missing_segments = _compress_periods(missing_sorted, step_days=step)

    present_count = len(present_set)
    expected_count = len(expected)
    missing_count = len(missing_sorted)

    if note and note.startswith("ERROR:"):
        status = "ERROR"
    elif note and present_count == 0:
        status = "NOT_CONFIGURED"
    elif present_count == 0:
        status = "EMPTY"
    elif missing_count > 0:
        status = "WARN"
    else:
        status = "OK"

    return DatasetAvailability(
        code=code,
        title=title,
        grain=grain,
        status=status,  # type: ignore[arg-type]
        window_from=window_from,
        window_to=window_to,
        expected_count=expected_count,
        present_count=present_count,
        missing_count=missing_count,
        min_present=present_sorted[0] if present_sorted else None,
        max_present=present_sorted[-1] if present_sorted else None,
        present_segments=present_segments,
        missing_segments=missing_segments,
        note=note,
    )


def _get_wb_frontend_brand_ids_for_project(project_id: int) -> List[str]:
    sql = text(
        """
        SELECT pm.settings_json AS settings_json
        FROM project_marketplaces pm
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE pm.project_id = :project_id
          AND m.code = 'wildberries'
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = _safe_execute(conn, sql, {"project_id": project_id}).mappings().first()
        settings = row["settings_json"] if row else None

    if not isinstance(settings, dict):
        return []

    brand_ids: List[str] = []

    fp = settings.get("frontend_prices") if isinstance(settings, dict) else None
    brands = fp.get("brands") if isinstance(fp, dict) else None
    if isinstance(brands, list):
        for b in brands:
            if not isinstance(b, dict):
                continue
            if b.get("enabled") is False:
                continue
            bid = b.get("brand_id")
            if bid is None:
                continue
            brand_ids.append(str(bid))

    if not brand_ids:
        bid = settings.get("brand_id")
        if bid is not None:
            brand_ids.append(str(bid))

    # De-dup while preserving order
    seen: Set[str] = set()
    out: List[str] = []
    for bid in brand_ids:
        if bid in seen:
            continue
        seen.add(bid)
        out.append(bid)
    return out


def compute_project_data_availability(project_id: int, *, days: int = 90) -> DataAvailabilityResponse:
    if days < 1 or days > 365:
        raise ValueError("days must be in [1..365]")

    window_to = date.today()
    window_from = window_to - timedelta(days=days - 1)

    start_ts = datetime.combine(window_from, datetime.min.time())
    end_ts = datetime.combine(window_to + timedelta(days=1), datetime.min.time())

    wb_brand_ids = _get_wb_frontend_brand_ids_for_project(project_id)

    items: List[DatasetAvailability] = []

    with engine.connect() as conn:
        # 1) Остатки каталога (FBS): stock_snapshots
        try:
            sql = text(
                """
                SELECT DISTINCT (snapshot_at::date) AS d
                FROM stock_snapshots
                WHERE project_id = :project_id
                  AND snapshot_at >= :start_ts
                  AND snapshot_at < :end_ts
                """
            )
            dates = _safe_execute(conn, sql, {"project_id": project_id, "start_ts": start_ts, "end_ts": end_ts}).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="stock_snapshots",
                    title="Остатки каталога (FBS)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="stock_snapshots",
                    title="Остатки каталога (FBS)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 2) FBO: supplier_stock_snapshots (project scope via products join)
        try:
            sql = text(
                """
                SELECT DISTINCT (s.last_change_date::date) AS d
                FROM supplier_stock_snapshots s
                JOIN products p
                  ON p.project_id = :project_id
                 AND p.nm_id = s.nm_id
                WHERE s.last_change_date >= :start_ts
                  AND s.last_change_date < :end_ts
                """
            )
            dates = _safe_execute(conn, sql, {"project_id": project_id, "start_ts": start_ts, "end_ts": end_ts}).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="supplier_stock_snapshots",
                    title="Остатки WB (FBO)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="supplier_stock_snapshots",
                    title="Остатки WB (FBO)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 3) Цены WB (API): price_snapshots
        try:
            sql = text(
                """
                SELECT DISTINCT (created_at::date) AS d
                FROM price_snapshots
                WHERE project_id = :project_id
                  AND created_at >= :start_ts
                  AND created_at < :end_ts
                """
            )
            dates = _safe_execute(conn, sql, {"project_id": project_id, "start_ts": start_ts, "end_ts": end_ts}).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="price_snapshots",
                    title="Цены WB (API)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="price_snapshots",
                    title="Цены WB (API)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 4) Витрина WB: frontend_catalog_price_snapshots by configured brand_id(s)
        try:
            if not wb_brand_ids:
                items.append(
                    _build_dataset_availability(
                        code="frontend_catalog_price_snapshots",
                        title="Витрина WB (frontend_prices)",
                        grain="day",
                        window_from=window_from,
                        window_to=window_to,
                        present_periods=[],
                        note="WB brand_id не настроен",
                    )
                )
            else:
                sql = (
                    text(
                        """
                        SELECT DISTINCT (snapshot_at::date) AS d
                        FROM frontend_catalog_price_snapshots
                        WHERE query_type = 'brand'
                          AND query_value IN :brand_ids
                          AND snapshot_at >= :start_ts
                          AND snapshot_at < :end_ts
                        """
                    )
                    .bindparams(bindparam("brand_ids", expanding=True))
                )
                params = {"brand_ids": wb_brand_ids, "start_ts": start_ts, "end_ts": end_ts}
                dates = _safe_execute(conn, sql, params).scalars().all()
                items.append(
                    _build_dataset_availability(
                        code="frontend_catalog_price_snapshots",
                        title="Витрина WB (frontend_prices)",
                        grain="day",
                        window_from=window_from,
                        window_to=window_to,
                        present_periods=[d for d in dates if isinstance(d, date)],
                        note=f"brand_id: {', '.join(wb_brand_ids)}",
                    )
                )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="frontend_catalog_price_snapshots",
                    title="Витрина WB (frontend_prices)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 5) Финансовые отчеты WB: wb_finance_reports (weekly by period_to)
        try:
            sql = text(
                """
                SELECT DISTINCT date_trunc('week', (period_to::timestamp))::date AS week_start
                FROM wb_finance_reports
                WHERE project_id = :project_id
                  AND marketplace_code = 'wildberries'
                  AND period_to IS NOT NULL
                  AND period_to >= :start_date
                  AND period_to <= :end_date
                """
            )
            weeks = _safe_execute(
                conn,
                sql,
                {"project_id": project_id, "start_date": window_from, "end_date": window_to},
            ).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="wb_finance_reports",
                    title="Финансовые отчёты WB",
                    grain="week",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[w for w in weeks if isinstance(w, date)],
                    note="недели по period_to",
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="wb_finance_reports",
                    title="Финансовые отчёты WB",
                    grain="week",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 6) Воронка продаж: wb_card_stats_daily
        try:
            sql = text(
                """
                SELECT DISTINCT stat_date AS d
                FROM wb_card_stats_daily
                WHERE project_id = :project_id
                  AND stat_date >= :start_date
                  AND stat_date <= :end_date
                """
            )
            dates = _safe_execute(
                conn,
                sql,
                {"project_id": project_id, "start_date": window_from, "end_date": window_to},
            ).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="wb_card_stats_daily",
                    title="Воронка продаж WB (wb_card_stats_daily)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="wb_card_stats_daily",
                    title="Воронка продаж WB (wb_card_stats_daily)",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 7) Поисковые запросы WB: wb_search_query_daily
        try:
            sql = text(
                """
                SELECT DISTINCT stat_date AS d
                FROM wb_search_query_daily
                WHERE project_id = :project_id
                  AND stat_date >= :start_date
                  AND stat_date <= :end_date
                """
            )
            dates = _safe_execute(
                conn,
                sql,
                {"project_id": project_id, "start_date": window_from, "end_date": window_to},
            ).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="wb_search_query_daily",
                    title="Поисковые запросы WB",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="wb_search_query_daily",
                    title="Поисковые запросы WB",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

        # 8) Отзывы WB: wb_feedback_snapshots (by snapshot_at)
        try:
            sql = text(
                """
                SELECT DISTINCT (snapshot_at::date) AS d
                FROM wb_feedback_snapshots
                WHERE project_id = :project_id
                  AND snapshot_at >= :start_ts
                  AND snapshot_at < :end_ts
                """
            )
            dates = _safe_execute(conn, sql, {"project_id": project_id, "start_ts": start_ts, "end_ts": end_ts}).scalars().all()
            items.append(
                _build_dataset_availability(
                    code="wb_feedback_snapshots",
                    title="Отзывы WB",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[d for d in dates if isinstance(d, date)],
                    note="по snapshot_at",
                )
            )
        except Exception as e:
            items.append(
                _build_dataset_availability(
                    code="wb_feedback_snapshots",
                    title="Отзывы WB",
                    grain="day",
                    window_from=window_from,
                    window_to=window_to,
                    present_periods=[],
                    note=f"ERROR: {type(e).__name__}",
                )
            )

    return DataAvailabilityResponse(
        project_id=project_id,
        window_days=days,
        window_from=window_from,
        window_to=window_to,
        items=items,
    )
