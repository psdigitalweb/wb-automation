"""Deterministic unified query dataset assembly for one project/category scope."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import SeoQueryBatch, SeoQueryNormalized
from app.services.seo.query_pipeline.diagnostics import (
    CanonicalQueryPreview,
    SourceInventoryItem,
    UnifiedQueryDatasetDiagnostics,
)
from app.services.seo.query_pipeline.normalization import normalize_query_text


QuerySourceInventoryItem = SourceInventoryItem

_SOURCE_COMBINATION_KEYS = (
    "csv_only",
    "wb_terms_only",
    "wb_daily_only",
    "csv_wb_terms",
    "csv_wb_daily",
    "wb_terms_wb_daily",
    "csv_wb_terms_wb_daily",
)
_BUCKET_KEYS = ("head", "mid", "tail")
_GARBAGE_SINGLE_TOKEN_MARKERS = {
    "wb",
    "wildberries",
    "вайлдберриз",
    "вб",
    "ozon",
    "маркетплейс",
}
_INFORMATIONAL_MARKERS = {
    "как",
    "что",
    "почему",
    "зачем",
    "отзывы",
    "обзор",
    "сравнение",
    "лучше",
}
_NAVIGATION_MARKERS = {
    "wb",
    "wildberries",
    "вайлдберриз",
    "вб",
    "ozon",
}


@dataclass(frozen=True)
class CanonicalQuerySourceRef:
    """Traceability payload for one source contributing to a canonical query."""

    source_type: str
    record_ids: list[int] = field(default_factory=list)
    record_count: int = 0
    batch_ids: list[int] = field(default_factory=list)
    nm_ids: list[int] = field(default_factory=list)
    date_range: dict[str, str | None] | None = None
    raw_value_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalQueryRow:
    """One canonical query row for project/category scope."""

    project_id: int
    category_id: int
    normalized_query_text: str
    display_query: str
    source_presence: dict[str, bool]
    source_count: int
    source_record_refs: list[CanonicalQuerySourceRef]
    frequency_total: Decimal
    orders_total: Decimal
    ranking_value_used: Decimal
    bucket_basis: str
    head_tail_bucket: str
    first_seen_at: str | None
    last_seen_at: str | None
    is_empty_candidate: bool
    is_duplicate_candidate: bool
    is_garbage_candidate: bool
    is_informational_candidate: bool
    is_navigation_candidate: bool
    preparation_flag_reasons: list[str]
    avg_position_best: Decimal | None = None
    canonical_entity_basis: str = "normalized_query_text"
    display_variants: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UnifiedQueryDatasetResult:
    """Assembled canonical queries plus ready-to-print diagnostics."""

    project_id: int
    category_id: int
    canonical_queries: list[CanonicalQueryRow]
    diagnostics: UnifiedQueryDatasetDiagnostics
    latest_csv_batch_id: int | None = None


@dataclass
class _CanonicalAccumulator:
    project_id: int
    category_id: int
    normalized_query_text: str
    csv_rows: list[dict[str, Any]] = field(default_factory=list)
    terms_rows: list[dict[str, Any]] = field(default_factory=list)
    daily_rows: list[dict[str, Any]] = field(default_factory=list)
    wb_display_counter: Counter[str] = field(default_factory=Counter)
    display_variants: set[str] = field(default_factory=set)
    temporal_values: list[date | datetime] = field(default_factory=list)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_to_string(value: Decimal | None) -> str:
    if value is None:
        return "0"
    normalized = value.normalize()
    return format(normalized, "f") if normalized == normalized.to_integral() else format(normalized, "f").rstrip("0").rstrip(".")


def _coerce_temporal(value: Any) -> date | datetime | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        try:
            if "T" in value or " " in value:
                return datetime.fromisoformat(value.replace(" ", "T"))
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _normalize_text_for_matching(value: Any) -> str:
    if value is None:
        return ""
    return normalize_query_text(str(value))


def _trimmed_text(value: Any) -> str:
    return str(value or "").strip()


def _is_digits_only(text_value: str) -> bool:
    return bool(text_value) and text_value.isdigit()


def _is_only_punctuation(text_value: str) -> bool:
    return bool(text_value) and not any(ch.isalnum() for ch in text_value)


def _to_sortable_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _to_iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _min_temporal(values: Iterable[date | datetime]) -> str | None:
    normalized = [item for item in (_to_sortable_datetime(value) for value in values) if item is not None]
    if not normalized:
        return None
    return min(normalized).isoformat()


def _max_temporal(values: Iterable[date | datetime]) -> str | None:
    normalized = [item for item in (_to_sortable_datetime(value) for value in values) if item is not None]
    if not normalized:
        return None
    return max(normalized).isoformat()


def _completed_csv_batches(session: Session, *, project_id: int, category_id: int) -> list[SeoQueryBatch]:
    return session.scalars(
        select(SeoQueryBatch)
        .where(
            SeoQueryBatch.project_id == project_id,
            SeoQueryBatch.category_id == category_id,
            SeoQueryBatch.status == "completed",
        )
        .order_by(SeoQueryBatch.created_at.asc(), SeoQueryBatch.id.asc())
    ).all()


def _latest_completed_csv_batch(session: Session, *, project_id: int, category_id: int) -> SeoQueryBatch | None:
    return session.scalars(
        select(SeoQueryBatch)
        .where(
            SeoQueryBatch.project_id == project_id,
            SeoQueryBatch.category_id == category_id,
            SeoQueryBatch.status == "completed",
        )
        .order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc())
        .limit(1)
    ).first()


def _load_csv_rows(session: Session, *, batch_ids: list[int]) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    rows = session.scalars(
        select(SeoQueryNormalized)
        .where(SeoQueryNormalized.batch_id.in_(batch_ids))
        .order_by(SeoQueryNormalized.normalized_query.asc(), SeoQueryNormalized.batch_id.asc(), SeoQueryNormalized.id.asc())
    ).all()
    return [
        {
            "id": int(row.id),
            "batch_id": int(row.batch_id),
            "project_id": int(row.project_id),
            "category_id": int(row.category_id),
            "normalized_query": row.normalized_query or "",
            "display_query": row.display_query or "",
            "raw_row_count": int(row.raw_row_count or 0),
            "frequency_total": _decimal(row.frequency_total),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def _load_wb_terms_rows(session: Session, *, project_id: int, category_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                t.id,
                t.project_id,
                p.subject_id AS category_id,
                t.nm_id,
                t.search_text,
                t.frequency,
                t.is_ad,
                t.created_at,
                t.updated_at
            FROM wb_search_query_terms t
            JOIN products p
              ON p.project_id = t.project_id
             AND p.nm_id = t.nm_id
            WHERE t.project_id = :project_id
              AND p.subject_id = :category_id
            ORDER BY t.search_text ASC, t.id ASC
            """
        ),
        {"project_id": project_id, "category_id": category_id},
    ).mappings().all()
    normalized_rows = []
    for row in rows:
        payload = dict(row)
        payload["created_at"] = _coerce_temporal(payload.get("created_at"))
        payload["updated_at"] = _coerce_temporal(payload.get("updated_at"))
        normalized_rows.append(payload)
    return normalized_rows


def _load_wb_daily_rows(session: Session, *, project_id: int, category_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                d.id,
                d.project_id,
                p.subject_id AS category_id,
                d.nm_id,
                d.search_text,
                d.stat_date,
                d.orders,
                d.avg_position,
                d.created_at,
                d.updated_at
            FROM wb_search_query_daily d
            JOIN products p
              ON p.project_id = d.project_id
             AND p.nm_id = d.nm_id
            WHERE d.project_id = :project_id
              AND p.subject_id = :category_id
            ORDER BY d.search_text ASC, d.stat_date ASC, d.id ASC
            """
        ),
        {"project_id": project_id, "category_id": category_id},
    ).mappings().all()
    normalized_rows = []
    for row in rows:
        payload = dict(row)
        payload["stat_date"] = _coerce_temporal(payload.get("stat_date"))
        payload["created_at"] = _coerce_temporal(payload.get("created_at"))
        payload["updated_at"] = _coerce_temporal(payload.get("updated_at"))
        normalized_rows.append(payload)
    return normalized_rows


def _latest_timestamp_from_rows(rows: Iterable[dict[str, Any]], *field_names: str) -> str | None:
    values: list[date | datetime] = []
    for row in rows:
        for field_name in field_names:
            value = row.get(field_name)
            if isinstance(value, (date, datetime)):
                values.append(value)
    return _max_temporal(values)


def _source_inventory(
    *,
    csv_rows: list[dict[str, Any]],
    latest_csv_batch: SeoQueryBatch | None,
    wb_terms_rows: list[dict[str, Any]],
    wb_daily_rows: list[dict[str, Any]],
) -> list[QuerySourceInventoryItem]:
    csv_latest = _latest_timestamp_from_rows(csv_rows, "updated_at", "created_at")
    if latest_csv_batch and latest_csv_batch.updated_at:
        csv_latest = max(filter(None, [csv_latest, _to_iso(latest_csv_batch.updated_at)]), default=None)
    return [
        QuerySourceInventoryItem(
            source_type="csv_normalized",
            source_table="seo_queries_normalized",
            project_linkage="direct project_id",
            category_linkage="direct category_id",
            query_fields=["normalized_query", "display_query"],
            demand_fields=["frequency_total"],
            source_identifiers=["id", "batch_id"],
            freshness_fields=["created_at", "updated_at", "batch.created_at", "batch.updated_at"],
            record_count=len(csv_rows),
            latest_timestamp=csv_latest,
        ),
        QuerySourceInventoryItem(
            source_type="wb_terms",
            source_table="wb_search_query_terms",
            project_linkage="direct project_id",
            category_linkage="products.project_id + products.nm_id + products.subject_id",
            query_fields=["search_text"],
            demand_fields=["frequency"],
            source_identifiers=["id", "nm_id", "search_text"],
            freshness_fields=["created_at", "updated_at"],
            record_count=len(wb_terms_rows),
            latest_timestamp=_latest_timestamp_from_rows(wb_terms_rows, "updated_at", "created_at"),
        ),
        QuerySourceInventoryItem(
            source_type="wb_daily",
            source_table="wb_search_query_daily",
            project_linkage="direct project_id",
            category_linkage="products.project_id + products.nm_id + products.subject_id",
            query_fields=["search_text"],
            demand_fields=["orders", "avg_position"],
            source_identifiers=["id", "nm_id", "search_text", "stat_date"],
            freshness_fields=["stat_date", "created_at", "updated_at"],
            record_count=len(wb_daily_rows),
            latest_timestamp=_latest_timestamp_from_rows(wb_daily_rows, "updated_at", "created_at", "stat_date"),
        ),
    ]


def _presence_key(source_presence: dict[str, bool]) -> str:
    has_csv = bool(source_presence.get("has_csv_normalized"))
    has_terms = bool(source_presence.get("has_wb_terms"))
    has_daily = bool(source_presence.get("has_wb_daily"))
    if has_csv and has_terms and has_daily:
        return "csv_wb_terms_wb_daily"
    if has_csv and has_terms:
        return "csv_wb_terms"
    if has_csv and has_daily:
        return "csv_wb_daily"
    if has_terms and has_daily:
        return "wb_terms_wb_daily"
    if has_csv:
        return "csv_only"
    if has_terms:
        return "wb_terms_only"
    return "wb_daily_only"


def _bucket_for_position(*, index: int, total: int, ranking_value_used: Decimal) -> tuple[str, str]:
    if ranking_value_used <= 0:
        return "tail", "none"
    if total < 10:
        if index < 2:
            return "head", ""
        if index < 5:
            return "mid", ""
        return "tail", ""
    position_ratio = Decimal(index + 1) / Decimal(total)
    if position_ratio <= Decimal("0.2"):
        return "head", ""
    if position_ratio <= Decimal("0.5"):
        return "mid", ""
    return "tail", ""


def _choose_display_query(accumulator: _CanonicalAccumulator) -> str:
    csv_candidates = sorted({_trimmed_text(row.get("display_query")) for row in accumulator.csv_rows if _trimmed_text(row.get("display_query"))})
    if csv_candidates:
        return csv_candidates[0]
    if accumulator.wb_display_counter:
        top_count = max(accumulator.wb_display_counter.values())
        candidates = sorted(query for query, count in accumulator.wb_display_counter.items() if count == top_count)
        if candidates:
            return candidates[0]
    return accumulator.normalized_query_text


def _build_source_ref(source_type: str, rows: list[dict[str, Any]]) -> CanonicalQuerySourceRef:
    if source_type == "csv_normalized":
        return CanonicalQuerySourceRef(
            source_type=source_type,
            record_ids=sorted(int(row["id"]) for row in rows),
            record_count=len(rows),
            batch_ids=sorted({int(row["batch_id"]) for row in rows}),
            raw_value_summary={
                "frequency_total": _decimal_to_string(sum((_decimal(row.get("frequency_total")) for row in rows), Decimal("0"))),
                "raw_row_count_total": int(sum(int(row.get("raw_row_count") or 0) for row in rows)),
            },
        )
    if source_type == "wb_terms":
        return CanonicalQuerySourceRef(
            source_type=source_type,
            record_ids=sorted(int(row["id"]) for row in rows),
            record_count=len(rows),
            nm_ids=sorted({int(row["nm_id"]) for row in rows if row.get("nm_id") is not None}),
            raw_value_summary={
                "frequency_total": _decimal_to_string(sum((_decimal(row.get("frequency")) for row in rows), Decimal("0"))),
                "is_ad_true_count": int(sum(1 for row in rows if bool(row.get("is_ad")))),
            },
        )
    dates = [value for value in (_coerce_temporal(row.get("stat_date")) for row in rows) if isinstance(value, (date, datetime))]
    avg_positions = [_decimal(row.get("avg_position")) for row in rows if row.get("avg_position") is not None]
    return CanonicalQuerySourceRef(
        source_type=source_type,
        record_ids=sorted(int(row["id"]) for row in rows),
        record_count=len(rows),
        nm_ids=sorted({int(row["nm_id"]) for row in rows if row.get("nm_id") is not None}),
        date_range={
            "from": _to_iso(min(dates)) if dates else None,
            "to": _to_iso(max(dates)) if dates else None,
        },
        raw_value_summary={
            "orders_total": _decimal_to_string(sum((_decimal(row.get("orders")) for row in rows), Decimal("0"))),
            "avg_position_best": _decimal_to_string(min(avg_positions)) if avg_positions else None,
        },
    )


def _preparation_flags(*, normalized_query_text: str, source_count: int, source_refs: list[CanonicalQuerySourceRef]) -> tuple[dict[str, bool], list[str]]:
    reasons: list[str] = []
    tokens = [token for token in normalized_query_text.split(" ") if token]
    is_empty_candidate = normalized_query_text == ""
    if is_empty_candidate:
        reasons.append("empty_normalized_query")

    is_duplicate_candidate = source_count > 1 or any(ref.record_count > 1 for ref in source_refs)
    if is_duplicate_candidate:
        reasons.append("duplicate_or_multi_source_coverage")

    is_garbage_candidate = (
        len(normalized_query_text) < 2
        or _is_digits_only(normalized_query_text)
        or _is_only_punctuation(normalized_query_text)
        or (len(tokens) == 1 and tokens[0] in _GARBAGE_SINGLE_TOKEN_MARKERS)
    )
    if is_garbage_candidate:
        reasons.append("garbage_like_query")

    is_informational_candidate = any(token in _INFORMATIONAL_MARKERS for token in tokens)
    if is_informational_candidate:
        reasons.append("contains_informational_marker")

    is_navigation_candidate = any(token in _NAVIGATION_MARKERS for token in tokens)
    if is_navigation_candidate:
        reasons.append("contains_navigation_marker")

    return (
        {
            "is_empty_candidate": is_empty_candidate,
            "is_duplicate_candidate": is_duplicate_candidate,
            "is_garbage_candidate": is_garbage_candidate,
            "is_informational_candidate": is_informational_candidate,
            "is_navigation_candidate": is_navigation_candidate,
        },
        reasons,
    )


def _preview_from_row(row: CanonicalQueryRow) -> CanonicalQueryPreview:
    return CanonicalQueryPreview(
        project_id=row.project_id,
        category_id=row.category_id,
        normalized_query_text=row.normalized_query_text,
        display_query=row.display_query,
        source_presence_key=_presence_key(row.source_presence),
        source_presence=dict(row.source_presence),
        source_count=row.source_count,
        source_record_count=sum(ref.record_count for ref in row.source_record_refs),
        frequency_total=_decimal_to_string(row.frequency_total),
        orders_total=_decimal_to_string(row.orders_total),
        ranking_value_used=_decimal_to_string(row.ranking_value_used),
        bucket_basis=row.bucket_basis,
        head_tail_bucket=row.head_tail_bucket,
        preparation_flag_reasons=list(row.preparation_flag_reasons),
        display_variants=list(row.display_variants),
    )


def _has_any_flag(row: CanonicalQueryRow) -> bool:
    return any(
        (
            row.is_empty_candidate,
            row.is_duplicate_candidate,
            row.is_garbage_candidate,
            row.is_informational_candidate,
            row.is_navigation_candidate,
        )
    )


def _has_conflict(row: CanonicalQueryRow) -> bool:
    has_mixed_demand_coverage = (row.frequency_total > 0 and row.orders_total == 0) or (row.orders_total > 0 and row.frequency_total == 0)
    return row.source_count > 1 and (len(row.display_variants) > 1 or has_mixed_demand_coverage)


def assemble_unified_query_dataset(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    top_limit: int = 20,
    samples_limit: int = 20,
) -> UnifiedQueryDatasetResult:
    """Assemble a deterministic canonical query dataset for one project/category."""

    csv_batches = _completed_csv_batches(session, project_id=project_id, category_id=category_id)
    latest_csv_batch = _latest_completed_csv_batch(session, project_id=project_id, category_id=category_id)
    csv_batch_ids = [int(batch.id) for batch in csv_batches]
    batch_by_id = {int(batch.id): batch for batch in csv_batches}
    csv_rows = _load_csv_rows(session, batch_ids=csv_batch_ids)
    wb_terms_rows = _load_wb_terms_rows(session, project_id=project_id, category_id=category_id)
    wb_daily_rows = _load_wb_daily_rows(session, project_id=project_id, category_id=category_id)

    grouped: dict[tuple[int, int, str], _CanonicalAccumulator] = {}

    def ensure_group(normalized_query_text: str) -> _CanonicalAccumulator:
        key = (project_id, category_id, normalized_query_text)
        accumulator = grouped.get(key)
        if accumulator is None:
            accumulator = _CanonicalAccumulator(
                project_id=project_id,
                category_id=category_id,
                normalized_query_text=normalized_query_text,
            )
            grouped[key] = accumulator
        return accumulator

    for row in csv_rows:
        normalized_query = str(row.get("normalized_query") or "")
        accumulator = ensure_group(normalized_query)
        accumulator.csv_rows.append(row)
        display_query = _trimmed_text(row.get("display_query"))
        if display_query:
            accumulator.display_variants.add(display_query)
        for temporal in (row.get("created_at"), row.get("updated_at")):
            if isinstance(temporal, (date, datetime)):
                accumulator.temporal_values.append(temporal)
        batch = batch_by_id.get(int(row.get("batch_id") or 0))
        if batch is not None:
            for temporal in (batch.created_at, batch.updated_at):
                if isinstance(temporal, (date, datetime)):
                    accumulator.temporal_values.append(temporal)

    for row in wb_terms_rows:
        normalized_query = _normalize_text_for_matching(row.get("search_text"))
        accumulator = ensure_group(normalized_query)
        accumulator.terms_rows.append(row)
        display_query = _trimmed_text(row.get("search_text"))
        if display_query:
            accumulator.display_variants.add(display_query)
            accumulator.wb_display_counter[display_query] += 1
        for temporal in (row.get("created_at"), row.get("updated_at")):
            if isinstance(temporal, (date, datetime)):
                accumulator.temporal_values.append(temporal)

    for row in wb_daily_rows:
        normalized_query = _normalize_text_for_matching(row.get("search_text"))
        accumulator = ensure_group(normalized_query)
        accumulator.daily_rows.append(row)
        display_query = _trimmed_text(row.get("search_text"))
        if display_query:
            accumulator.display_variants.add(display_query)
            accumulator.wb_display_counter[display_query] += 1
        for temporal in (row.get("stat_date"), row.get("created_at"), row.get("updated_at")):
            if isinstance(temporal, (date, datetime)):
                accumulator.temporal_values.append(temporal)

    canonical_rows: list[CanonicalQueryRow] = []
    for _, accumulator in sorted(grouped.items(), key=lambda item: item[0][2]):
        source_presence = {
            "has_csv_normalized": bool(accumulator.csv_rows),
            "has_wb_terms": bool(accumulator.terms_rows),
            "has_wb_daily": bool(accumulator.daily_rows),
        }
        source_refs: list[CanonicalQuerySourceRef] = []
        if accumulator.csv_rows:
            source_refs.append(_build_source_ref("csv_normalized", accumulator.csv_rows))
        if accumulator.terms_rows:
            source_refs.append(_build_source_ref("wb_terms", accumulator.terms_rows))
        if accumulator.daily_rows:
            source_refs.append(_build_source_ref("wb_daily", accumulator.daily_rows))

        source_count = sum(1 for present in source_presence.values() if present)
        frequency_total = sum((_decimal(row.get("frequency_total")) for row in accumulator.csv_rows), Decimal("0"))
        frequency_total += sum((_decimal(row.get("frequency")) for row in accumulator.terms_rows), Decimal("0"))
        orders_total = sum((_decimal(row.get("orders")) for row in accumulator.daily_rows), Decimal("0"))
        avg_positions = [_decimal(row.get("avg_position")) for row in accumulator.daily_rows if row.get("avg_position") is not None]
        bucket_basis = "frequency_total" if frequency_total > 0 else ("orders_total" if orders_total > 0 else "none")
        ranking_value_used = frequency_total if frequency_total > 0 else (orders_total if orders_total > 0 else Decimal("0"))
        flags, reasons = _preparation_flags(
            normalized_query_text=accumulator.normalized_query_text,
            source_count=source_count,
            source_refs=source_refs,
        )

        canonical_rows.append(
            CanonicalQueryRow(
                project_id=project_id,
                category_id=category_id,
                normalized_query_text=accumulator.normalized_query_text,
                display_query=_choose_display_query(accumulator),
                source_presence=source_presence,
                source_count=source_count,
                source_record_refs=source_refs,
                frequency_total=frequency_total,
                orders_total=orders_total,
                ranking_value_used=ranking_value_used,
                bucket_basis=bucket_basis,
                head_tail_bucket="tail",
                first_seen_at=_min_temporal(accumulator.temporal_values),
                last_seen_at=_max_temporal(accumulator.temporal_values),
                avg_position_best=min(avg_positions) if avg_positions else None,
                preparation_flag_reasons=reasons,
                display_variants=sorted(accumulator.display_variants),
                **flags,
            )
        )

    ranked_rows = sorted(
        canonical_rows,
        key=lambda row: (-row.ranking_value_used, row.normalized_query_text),
    )
    bucketed_rows: list[CanonicalQueryRow] = []
    for index, row in enumerate(ranked_rows):
        bucket, bucket_override = _bucket_for_position(index=index, total=len(ranked_rows), ranking_value_used=row.ranking_value_used)
        bucket_basis = bucket_override or row.bucket_basis
        bucketed_rows.append(
            CanonicalQueryRow(
                **{
                    **row.__dict__,
                    "head_tail_bucket": bucket,
                    "bucket_basis": bucket_basis,
                }
            )
        )

    queries_by_source_presence = {key: 0 for key in _SOURCE_COMBINATION_KEYS}
    queries_by_head_tail_bucket = {key: 0 for key in _BUCKET_KEYS}
    for row in bucketed_rows:
        queries_by_source_presence[_presence_key(row.source_presence)] += 1
        queries_by_head_tail_bucket[row.head_tail_bucket] += 1

    top_queries = [_preview_from_row(row) for row in bucketed_rows[:top_limit]]
    partial_coverage_samples = [_preview_from_row(row) for row in bucketed_rows if row.source_count == 1][:samples_limit]
    flagged_samples = [_preview_from_row(row) for row in bucketed_rows if _has_any_flag(row)][:samples_limit]
    conflict_samples = [_preview_from_row(row) for row in bucketed_rows if _has_conflict(row)][:samples_limit]

    diagnostics = UnifiedQueryDatasetDiagnostics(
        project_id=project_id,
        category_id=category_id,
        source_inventory=_source_inventory(
            csv_rows=csv_rows,
            latest_csv_batch=latest_csv_batch,
            wb_terms_rows=wb_terms_rows,
            wb_daily_rows=wb_daily_rows,
        ),
        total_canonical_queries=len(bucketed_rows),
        total_source_linked_queries=sum(sum(ref.record_count for ref in row.source_record_refs) for row in bucketed_rows),
        queries_by_source_presence=queries_by_source_presence,
        queries_by_head_tail_bucket=queries_by_head_tail_bucket,
        top_queries=top_queries,
        partial_coverage_samples=partial_coverage_samples,
        flagged_samples=flagged_samples,
        conflict_samples=conflict_samples,
        latest_csv_batch_id=int(latest_csv_batch.id) if latest_csv_batch else None,
        assembly_basis="normalized_query_text",
    )

    return UnifiedQueryDatasetResult(
        project_id=project_id,
        category_id=category_id,
        canonical_queries=bucketed_rows,
        diagnostics=diagnostics,
        latest_csv_batch_id=int(latest_csv_batch.id) if latest_csv_batch else None,
    )
