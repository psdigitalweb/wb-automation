"""Local CSV import for SEO query batches."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import SeoQueryBatch, SeoQueryNormalized, SeoQueryRaw
from app.services.seo.query_pipeline.diagnostics import ImportDiagnostics, SuspiciousRow, TopNormalizedQuery
from app.services.seo.query_pipeline.normalization import (
    extract_frequency,
    extract_query_text,
    normalize_query_text,
    resolve_frequency_column,
    resolve_query_column,
)


class CsvImportError(ValueError):
    """Raised when the CSV cannot be imported safely."""


@dataclass(frozen=True)
class _ParsedCsv:
    """CSV rows plus resolved parser metadata."""

    rows: list[dict[str, Any]]
    query_column: str
    frequency_column: str | None


_WB_QUERY_EXPORT_HEADERS = ("Поисковый запрос", "Количество запросов")


def _suspicious_row_to_preview(row: SuspiciousRow) -> dict[str, Any]:
    """Convert suspicious row dataclass to JSON-serializable preview payload."""

    return {
        "row_number": int(row.row_number),
        "reason": row.reason,
        "raw_query": row.raw_query,
        "payload": dict(row.payload or {}),
    }


def _sniff_csv_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _read_rows_with_dialect(handle, *, dialect: csv.Dialect | type[csv.Dialect] | str) -> _ParsedCsv:
    reader = csv.DictReader(handle, dialect=dialect)
    if not reader.fieldnames:
        raise CsvImportError("CSV must include a header row")

    query_column = resolve_query_column(reader.fieldnames)
    frequency_column = resolve_frequency_column(reader.fieldnames)
    rows: list[dict[str, Any]] = []
    for row in reader:
        if row is None:
            continue
        rows.append(dict(row))
    return _ParsedCsv(
        rows=rows,
        query_column=query_column,
        frequency_column=frequency_column,
    )


def _looks_like_wb_frequency_export(fieldnames: list[str] | None) -> bool:
    if not fieldnames:
        return False
    normalized = {str(name or "").strip() for name in fieldnames}
    return all(header in normalized for header in _WB_QUERY_EXPORT_HEADERS)


def _read_csv(csv_path: str) -> _ParsedCsv:
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            preview_reader = csv.reader(sample.splitlines(), delimiter=",")
            preview_header = next(preview_reader, None)
            if _looks_like_wb_frequency_export(preview_header):
                handle.seek(0)
                return _read_rows_with_dialect(handle, dialect="excel")

            dialect = _sniff_csv_dialect(sample)
            handle.seek(0)
            return _read_rows_with_dialect(handle, dialect=dialect)
    except UnicodeDecodeError as exc:
        raise CsvImportError("CSV must be UTF-8 or UTF-8-SIG encoded") from exc
    except CsvImportError:
        raise
    except ValueError as exc:
        raise CsvImportError(str(exc)) from exc
    except csv.Error as exc:
        raise CsvImportError(f"Malformed CSV: {exc}") from exc
    except OSError as exc:
        raise CsvImportError(f"Failed to read CSV file: {exc}") from exc


def _append_suspicious(
    samples: list[SuspiciousRow],
    *,
    row_number: int,
    reason: str,
    raw_query: str | None = None,
    payload: dict[str, Any] | None = None,
    limit: int = 10,
) -> None:
    if len(samples) >= limit:
        return
    samples.append(
        SuspiciousRow(
            row_number=row_number,
            reason=reason,
            raw_query=raw_query,
            payload=dict(payload or {}),
        )
    )


def import_queries_from_csv(
    session: Session,
    *,
    csv_path: str,
    project_id: int,
    category_id: int,
    original_filename: str | None = None,
    source_type: str = "csv",
    suspicious_limit: int = 10,
    top_queries_limit: int = 10,
) -> ImportDiagnostics:
    """Import one local WB query CSV into raw and normalized SEO tables."""

    parsed_csv = _read_csv(csv_path)
    batch = SeoQueryBatch(
        project_id=project_id,
        category_id=category_id,
        source_type=source_type,
        source_path=os.path.abspath(csv_path),
        original_filename=original_filename or os.path.basename(csv_path),
        status="processing",
        meta={
            "query_column_resolved": parsed_csv.query_column,
            "frequency_column_resolved": parsed_csv.frequency_column,
            "normalization_version": "v1_csv_task_02",
        },
    )
    session.add(batch)
    session.flush()

    suspicious_rows: list[SuspiciousRow] = []
    aggregates: dict[str, dict[str, Any]] = {}
    exact_raw_duplicates = defaultdict(int)
    raw_rows_imported = 0
    raw_rows_skipped = 0
    duplicate_raw_rows_detected = 0

    for row_number, row in enumerate(parsed_csv.rows, start=2):
        row_payload = dict(row)
        if None in row_payload:
            raw_rows_skipped += 1
            _append_suspicious(
                suspicious_rows,
                row_number=row_number,
                reason="malformed_row",
                payload=row_payload,
                limit=suspicious_limit,
            )
            continue

        raw_query = extract_query_text(row_payload, parsed_csv.query_column)
        if raw_query is None:
            raw_rows_skipped += 1
            _append_suspicious(
                suspicious_rows,
                row_number=row_number,
                reason="missing_query_text",
                payload=row_payload,
                limit=suspicious_limit,
            )
            continue

        if raw_query.strip() == "":
            raw_rows_skipped += 1
            _append_suspicious(
                suspicious_rows,
                row_number=row_number,
                reason="empty_or_whitespace_query",
                raw_query=raw_query,
                payload=row_payload,
                limit=suspicious_limit,
            )
            continue

        normalized_query = normalize_query_text(raw_query)
        if not normalized_query:
            raw_rows_skipped += 1
            _append_suspicious(
                suspicious_rows,
                row_number=row_number,
                reason="normalization_produced_empty_query",
                raw_query=raw_query,
                payload=row_payload,
                limit=suspicious_limit,
            )
            continue

        extracted_frequency = extract_frequency(row_payload, parsed_csv.frequency_column)
        if parsed_csv.frequency_column and row_payload.get(parsed_csv.frequency_column) not in (None, "") and extracted_frequency is None:
            _append_suspicious(
                suspicious_rows,
                row_number=row_number,
                reason="invalid_frequency_value",
                raw_query=raw_query,
                payload=row_payload,
                limit=suspicious_limit,
            )
        raw_frequency = extracted_frequency if extracted_frequency is not None else Decimal("1")

        duplicate_key = (raw_query.strip(), str(raw_frequency))
        exact_raw_duplicates[duplicate_key] += 1
        if exact_raw_duplicates[duplicate_key] > 1:
            duplicate_raw_rows_detected += 1

        persisted_payload = dict(row_payload)
        persisted_payload["raw_query"] = raw_query.strip()
        persisted_payload["__resolved_query_column"] = parsed_csv.query_column
        persisted_payload["__resolved_frequency_column"] = parsed_csv.frequency_column
        persisted_payload["__normalized_query"] = normalized_query

        session.add(
            SeoQueryRaw(
                batch_id=batch.id,
                project_id=project_id,
                category_id=category_id,
                row_number=row_number,
                raw_query=raw_query,
                raw_frequency=raw_frequency,
                source_payload=persisted_payload,
            )
        )
        raw_rows_imported += 1

        aggregate = aggregates.setdefault(
            normalized_query,
            {
                "display_query": raw_query.strip(),
                "raw_row_count": 0,
                "frequency_total": Decimal("0"),
                "first_row_number": row_number,
                "sample_source_payload": dict(persisted_payload),
            },
        )
        aggregate["raw_row_count"] += 1
        aggregate["frequency_total"] += raw_frequency

    for normalized_query, aggregate in aggregates.items():
        sample_payload = dict(aggregate["sample_source_payload"])
        sample_payload["__trace_first_row_number"] = aggregate["first_row_number"]
        sample_payload["__raw_row_count"] = aggregate["raw_row_count"]
        session.add(
            SeoQueryNormalized(
                batch_id=batch.id,
                project_id=project_id,
                category_id=category_id,
                normalized_query=normalized_query,
                display_query=aggregate["display_query"],
                normalization_version="v1_csv_task_02",
                raw_row_count=aggregate["raw_row_count"],
                frequency_total=aggregate["frequency_total"],
                sample_source_payload=sample_payload,
            )
        )

    normalized_rows_created = len(aggregates)
    batch.status = "completed"
    batch.row_count = raw_rows_imported
    batch.normalized_row_count = normalized_rows_created
    batch.deduplicated_row_count = normalized_rows_created
    batch.meta = {
        **(batch.meta or {}),
        "raw_rows_skipped": raw_rows_skipped,
        "duplicate_raw_rows_detected": duplicate_raw_rows_detected,
        "suspicious_rows_preview": [_suspicious_row_to_preview(item) for item in suspicious_rows],
    }
    session.flush()

    top_normalized_queries: list[TopNormalizedQuery] = []
    if parsed_csv.frequency_column:
        ranked = sorted(
            aggregates.items(),
            key=lambda item: (item[1]["frequency_total"], item[1]["raw_row_count"], item[0]),
            reverse=True,
        )
        for normalized_query, aggregate in ranked[:top_queries_limit]:
            top_normalized_queries.append(
                TopNormalizedQuery(
                    normalized_query=normalized_query,
                    raw_row_count=int(aggregate["raw_row_count"]),
                    frequency_total=aggregate["frequency_total"],
                )
            )

    return ImportDiagnostics(
        batch_id=int(batch.id),
        project_id=project_id,
        category_id=category_id,
        source_file_path=os.path.abspath(csv_path),
        query_column_resolved=parsed_csv.query_column,
        frequency_column_resolved=parsed_csv.frequency_column,
        raw_rows_imported=raw_rows_imported,
        raw_rows_skipped=raw_rows_skipped,
        normalized_rows_created=normalized_rows_created,
        duplicate_groups_collapsed=max(raw_rows_imported - normalized_rows_created, 0),
        duplicate_raw_rows_detected=duplicate_raw_rows_detected,
        suspicious_rows=suspicious_rows,
        top_normalized_queries=top_normalized_queries,
    )
