"""Diagnostics structures for SEO query CSV import."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SuspiciousRow:
    """A skipped or suspicious CSV row sample."""

    row_number: int
    reason: str
    raw_query: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopNormalizedQuery:
    """Top normalized query entry used in diagnostics output."""

    normalized_query: str
    raw_row_count: int
    frequency_total: Decimal | None


@dataclass(frozen=True)
class ImportDiagnostics:
    """Readable summary for one local CSV import batch."""

    batch_id: int
    project_id: int
    category_id: int
    source_file_path: str
    query_column_resolved: str
    frequency_column_resolved: str | None
    raw_rows_imported: int
    raw_rows_skipped: int
    normalized_rows_created: int
    duplicate_groups_collapsed: int
    duplicate_raw_rows_detected: int
    suspicious_rows: list[SuspiciousRow] = field(default_factory=list)
    top_normalized_queries: list[TopNormalizedQuery] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        payload = asdict(self)
        for item in payload["top_normalized_queries"]:
            if item["frequency_total"] is not None:
                item["frequency_total"] = str(item["frequency_total"])
        return payload
