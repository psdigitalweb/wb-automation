"""Generic evidence reader for category-profile derive.

This module only reads existing corpus and axes rows. It does not build,
persist, activate, or score a ``SeoCategoryProfile``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.models import SeoCategoryMeaningAxes, SeoQueryNormalized


_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ.]+", re.IGNORECASE)
_ECONOMIC_FIELD_PATTERNS = (
    "orders",
    "order",
    "conversion",
    "конверсия",
    "заказ",
    "заказали",
)


class CategoryProfileEvidenceError(Exception):
    """Base error for derive evidence input problems."""


class MissingCorpusError(CategoryProfileEvidenceError):
    """Raised when a category has no normalized query corpus."""


class MissingAxesError(CategoryProfileEvidenceError):
    """Raised when a category has no ready meaning axes."""


class AmbiguousAxesError(CategoryProfileEvidenceError):
    """Raised when latest ready axes cannot be selected deterministically."""


@dataclass(frozen=True)
class QueryCandidateEvidence:
    """One normalized query row usable as derive corpus evidence."""

    normalized_query: str
    display_query: str
    frequency_total: str
    raw_row_count: int


@dataclass(frozen=True)
class AxesEvidence:
    """Latest ready category meaning axes used as derive input."""

    axes_id: int
    schema_version: str
    source: str
    evidence_hash: str
    input_hash: str
    axes_payload: Mapping[str, Any]


@dataclass(frozen=True)
class CorpusDiagnostics:
    """Completeness and safety diagnostics for derive evidence."""

    query_count: int
    distinct_query_count: int
    top_queries_count: int
    total_frequency: str
    nonzero_frequency_count: int
    source_payload_keys_sample: tuple[str, ...]
    economic_field_names_present: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CategoryProfileDeriveEvidence:
    """All existing inputs needed by later generic profile builders."""

    project_id: int
    category_id: int
    evidence_hash: str
    corpus: CorpusDiagnostics
    query_candidates: tuple[QueryCandidateEvidence, ...]
    query_token_counts: Mapping[str, int]
    axes: AxesEvidence
    diagnostics: Mapping[str, Any]

    def to_builder_input(self) -> dict[str, Any]:
        """Return JSON-compatible evidence for later derive builder steps."""

        return {
            "project_id": self.project_id,
            "category_id": self.category_id,
            "evidence_hash": self.evidence_hash,
            "corpus": {
                "query_count": self.corpus.query_count,
                "distinct_query_count": self.corpus.distinct_query_count,
                "top_queries_count": self.corpus.top_queries_count,
                "total_frequency": self.corpus.total_frequency,
                "nonzero_frequency_count": self.corpus.nonzero_frequency_count,
                "source_payload_keys_sample": list(self.corpus.source_payload_keys_sample),
                "economic_field_names_present": list(self.corpus.economic_field_names_present),
                "notes": list(self.corpus.notes),
            },
            "query_candidates": [
                {
                    "normalized_query": item.normalized_query,
                    "display_query": item.display_query,
                    "frequency_total": item.frequency_total,
                    "raw_row_count": item.raw_row_count,
                }
                for item in self.query_candidates
            ],
            "query_token_counts": dict(self.query_token_counts),
            "axes": {
                "axes_id": self.axes.axes_id,
                "schema_version": self.axes.schema_version,
                "source": self.axes.source,
                "evidence_hash": self.axes.evidence_hash,
                "input_hash": self.axes.input_hash,
                "axes_payload": dict(self.axes.axes_payload),
            },
            "diagnostics": dict(self.diagnostics),
        }


def read_category_profile_derive_evidence(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    top_query_limit: int = 200,
    token_limit: int = 200,
) -> CategoryProfileDeriveEvidence:
    """Read generic derive evidence from existing corpus and axes tables."""

    category_id = int(category_id)
    project_id = int(project_id)
    if top_query_limit <= 0:
        raise ValueError("top_query_limit must be positive")
    if token_limit <= 0:
        raise ValueError("token_limit must be positive")

    axes = _read_latest_ready_axes(session, project_id=project_id, category_id=category_id)
    corpus = _read_corpus_diagnostics(session, project_id=project_id, category_id=category_id)
    if corpus.query_count <= 0:
        raise MissingCorpusError(
            f"No SeoQueryNormalized corpus found for project_id={project_id}, category_id={category_id}."
        )

    query_candidates = _read_top_query_candidates(
        session,
        project_id=project_id,
        category_id=category_id,
        limit=top_query_limit,
    )
    corpus = replace(corpus, top_queries_count=len(query_candidates))
    token_counts = _top_query_tokens(query_candidates, limit=token_limit)
    diagnostics = {
        "status": "ready",
        "missing_inputs": [],
        "warnings": list(corpus.notes),
        "axes": {
            "id": axes.axes_id,
            "source": axes.source,
            "schema_version": axes.schema_version,
            "product_type_axes_count": len(_list_from_mapping(axes.axes_payload, "product_type_axes")),
            "use_case_axes_count": len(_list_from_mapping(axes.axes_payload, "use_case_axes")),
            "audience_axes_count": len(_list_from_mapping(axes.axes_payload, "audience_axes")),
            "attribute_axes_count": len(_list_from_mapping(axes.axes_payload, "attribute_axes")),
        },
        "economics_usage": "raw economics fields are recorded as diagnostics only, not builder scoring evidence",
    }
    evidence_hash = _build_evidence_hash(
        project_id=project_id,
        category_id=category_id,
        corpus=corpus,
        query_candidates=query_candidates,
        token_counts=token_counts,
        axes=axes,
    )
    return CategoryProfileDeriveEvidence(
        project_id=project_id,
        category_id=category_id,
        evidence_hash=f"sha256:{evidence_hash}",
        corpus=corpus,
        query_candidates=query_candidates,
        query_token_counts=token_counts,
        axes=axes,
        diagnostics=diagnostics,
    )


def _read_latest_ready_axes(session: Session, *, project_id: int, category_id: int) -> AxesEvidence:
    rows = list(
        session.scalars(
            select(SeoCategoryMeaningAxes)
            .where(
                SeoCategoryMeaningAxes.project_id == int(project_id),
                SeoCategoryMeaningAxes.category_id == int(category_id),
                SeoCategoryMeaningAxes.status == "ready",
            )
            .order_by(desc(SeoCategoryMeaningAxes.updated_at), desc(SeoCategoryMeaningAxes.id))
            .limit(2)
        )
    )
    if not rows:
        raise MissingAxesError(
            f"No ready SeoCategoryMeaningAxes found for project_id={project_id}, category_id={category_id}."
        )
    row = rows[0]
    payload = dict(getattr(row, "axes_payload", {}) or {})
    if not payload:
        raise MissingAxesError(
            f"Latest ready SeoCategoryMeaningAxes has empty axes_payload for project_id={project_id}, "
            f"category_id={category_id}, axes_id={getattr(row, 'id', None)}."
        )
    return AxesEvidence(
        axes_id=int(row.id),
        schema_version=str(row.schema_version or ""),
        source=str(row.source or ""),
        evidence_hash=str(row.evidence_hash or ""),
        input_hash=str(row.input_hash or ""),
        axes_payload=payload,
    )


def _read_corpus_diagnostics(session: Session, *, project_id: int, category_id: int) -> CorpusDiagnostics:
    row = session.execute(
        select(
            func.count(SeoQueryNormalized.id),
            func.count(func.distinct(SeoQueryNormalized.normalized_query)),
            func.coalesce(func.sum(SeoQueryNormalized.frequency_total), 0),
            func.sum(_nonzero_frequency_case()),
        ).where(
            SeoQueryNormalized.project_id == int(project_id),
            SeoQueryNormalized.category_id == int(category_id),
        )
    ).one()
    query_count = int(row[0] or 0)
    distinct_query_count = int(row[1] or 0)
    total_frequency = _decimal_to_string(row[2])
    nonzero_frequency_count = int(row[3] or 0)
    source_payload_keys, economic_fields = _source_payload_key_diagnostics(
        session,
        project_id=project_id,
        category_id=category_id,
    )
    notes: list[str] = []
    if query_count == 0:
        notes.append("missing_corpus")
    if nonzero_frequency_count == 0 and query_count > 0:
        notes.append("all_query_frequencies_are_zero")
    return CorpusDiagnostics(
        query_count=query_count,
        distinct_query_count=distinct_query_count,
        top_queries_count=0,
        total_frequency=total_frequency,
        nonzero_frequency_count=nonzero_frequency_count,
        source_payload_keys_sample=tuple(source_payload_keys),
        economic_field_names_present=tuple(economic_fields),
        notes=tuple(notes),
    )


def _nonzero_frequency_case() -> Any:
    return case((SeoQueryNormalized.frequency_total > 0, 1), else_=0)


def _source_payload_key_diagnostics(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    sample_limit: int = 50,
) -> tuple[list[str], list[str]]:
    rows = session.scalars(
        select(SeoQueryNormalized.sample_source_payload)
        .where(
            SeoQueryNormalized.project_id == int(project_id),
            SeoQueryNormalized.category_id == int(category_id),
        )
        .order_by(desc(SeoQueryNormalized.frequency_total), SeoQueryNormalized.normalized_query.asc())
        .limit(sample_limit)
    ).all()
    keys: set[str] = set()
    economic_keys: set[str] = set()
    for payload in rows:
        if not isinstance(payload, Mapping):
            continue
        for key in payload.keys():
            key_text = str(key)
            if _is_economic_field_name(key_text):
                economic_keys.add(key_text)
            else:
                keys.add(key_text)
    return sorted(keys), sorted(economic_keys)


def _read_top_query_candidates(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int,
) -> tuple[QueryCandidateEvidence, ...]:
    rows = session.execute(
        select(
            SeoQueryNormalized.normalized_query,
            SeoQueryNormalized.display_query,
            SeoQueryNormalized.frequency_total,
            SeoQueryNormalized.raw_row_count,
        )
        .where(
            SeoQueryNormalized.project_id == int(project_id),
            SeoQueryNormalized.category_id == int(category_id),
        )
        .order_by(desc(SeoQueryNormalized.frequency_total), SeoQueryNormalized.normalized_query.asc())
        .limit(int(limit))
    ).all()
    return tuple(
        QueryCandidateEvidence(
            normalized_query=str(row[0] or ""),
            display_query=str(row[1] or ""),
            frequency_total=_decimal_to_string(row[2]),
            raw_row_count=int(row[3] or 0),
        )
        for row in rows
    )


def _top_query_tokens(candidates: Sequence[QueryCandidateEvidence], *, limit: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        weight = max(1, int(Decimal(candidate.frequency_total or "0")))
        for token in _tokens(candidate.normalized_query):
            counts[token] = counts.get(token, 0) + weight
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: int(limit)])


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower().replace("ё", "е") for match in _WORD_RE.finditer(value or ""))


def _is_economic_field_name(value: str) -> bool:
    normalized = value.lower().replace("ё", "е")
    return any(pattern in normalized for pattern in _ECONOMIC_FIELD_PATTERNS)


def _list_from_mapping(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _decimal_to_string(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value or "0")


def _build_evidence_hash(
    *,
    project_id: int,
    category_id: int,
    corpus: CorpusDiagnostics,
    query_candidates: Sequence[QueryCandidateEvidence],
    token_counts: Mapping[str, int],
    axes: AxesEvidence,
) -> str:
    fingerprint_payload = {
        "method": "category_profile_derive_evidence_v1",
        "project_id": int(project_id),
        "category_id": int(category_id),
        "corpus": {
            "query_count": corpus.query_count,
            "distinct_query_count": corpus.distinct_query_count,
            "total_frequency": corpus.total_frequency,
            "nonzero_frequency_count": corpus.nonzero_frequency_count,
            "source_payload_keys_sample": list(corpus.source_payload_keys_sample),
        },
        "query_candidates": [
            {
                "normalized_query": item.normalized_query,
                "display_query": item.display_query,
                "frequency_total": item.frequency_total,
                "raw_row_count": item.raw_row_count,
            }
            for item in query_candidates
        ],
        "query_token_counts": dict(token_counts),
        "axes": {
            "axes_id": axes.axes_id,
            "schema_version": axes.schema_version,
            "source": axes.source,
            "evidence_hash": axes.evidence_hash,
            "input_hash": axes.input_hash,
            "axes_payload": dict(axes.axes_payload),
        },
    }
    encoded = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
