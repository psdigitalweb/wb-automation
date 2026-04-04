"""Deterministic text normalization for SEO query imports."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


QUERY_FIELD_CANDIDATES: Sequence[str] = (
    "query",
    "text",
    "keyword",
    "search_query",
    "request",
    "запрос",
    "поисковый запрос",
    "фраза",
)
FREQUENCY_FIELD_CANDIDATES: Sequence[str] = (
    "frequency",
    "freq",
    "count",
    "hits",
    "volume",
    "частота",
    "частотность",
)

_PUNCTUATION_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+", flags=re.UNICODE)


def canonicalize_header(header: str) -> str:
    """Normalize CSV header names for stable column resolution."""

    return _WHITESPACE_RE.sub(" ", str(header or "").strip().casefold())


def normalize_query_text(raw_query: str) -> str:
    """Normalize raw query text with minimal deterministic cleanup only."""

    normalized = str(raw_query or "").strip().casefold().replace("ё", "е")
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def resolve_query_column(fieldnames: Sequence[str] | None) -> str:
    """Resolve the query text column or fail clearly."""

    normalized_headers = {canonicalize_header(name): name for name in (fieldnames or []) if name}
    for candidate in QUERY_FIELD_CANDIDATES:
        resolved = normalized_headers.get(canonicalize_header(candidate))
        if resolved:
            return resolved
    raise ValueError(
        "CSV is missing a required query column. Expected one of: "
        + ", ".join(QUERY_FIELD_CANDIDATES)
    )


def resolve_frequency_column(fieldnames: Sequence[str] | None) -> str | None:
    """Resolve the optional frequency column if present."""

    normalized_headers = {canonicalize_header(name): name for name in (fieldnames or []) if name}
    for candidate in FREQUENCY_FIELD_CANDIDATES:
        resolved = normalized_headers.get(canonicalize_header(candidate))
        if resolved:
            return resolved
    return None


def extract_query_text(row: Mapping[str, object], query_column: str) -> str | None:
    """Extract raw query text from the resolved query column."""

    value = row.get(query_column)
    if value is None:
        return None
    return str(value)


def extract_frequency(row: Mapping[str, object], frequency_column: str | None) -> Decimal | None:
    """Extract frequency-like numeric value from the resolved frequency column."""

    if not frequency_column:
        return None
    value = row.get(frequency_column)
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip().replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
