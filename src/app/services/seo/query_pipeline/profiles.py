"""Deterministic query-cluster profile extraction for scoring preparation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy.orm import Session

from app.services.seo.query_pipeline.clustering import (
    PersistedQueryClusterView,
    _ClusteringHeuristicsContext,
    _build_clustering_context,
    _normalize_token_for_cluster,
    _strong_tokens,
    get_query_clusters,
)
from app.services.seo.query_pipeline.diagnostics import (
    ExtractedClusterProfile,
    QueryProfileExtractionDiagnostics,
    QueryProfileMarker,
    QueryProfileMarkerDecision,
    _serialize_value,
)
from app.services.seo.query_pipeline.hybrid import HybridAnnotatedQueryRow, get_persisted_hybrid_projection
from app.services.seo.query_pipeline.pruning import get_clean_query_set


_ATTRIBUTE_FAMILY_ORDER = ("format", "shape", "material", "color", "size", "quantity")
_PRODUCT_GENERIC_TOKENS = {
    "аксессуар",
    "дом",
    "домашний",
    "изделие",
    "кухня",
    "кухонный",
    "посуда",
    "предмет",
    "товар",
}
_COLOR_TOKENS = {
    "белая",
    "белое",
    "белые",
    "белый",
    "бирюзовая",
    "бирюзовые",
    "голубая",
    "голубые",
    "зеленая",
    "зеленые",
    "золотая",
    "золотые",
    "красная",
    "красное",
    "красные",
    "прозрачная",
    "прозрачные",
    "розовая",
    "розовые",
    "серая",
    "серые",
    "синяя",
    "синие",
    "черная",
    "черное",
    "черные",
}
_MATERIAL_PREFIXES = ("дерев", "керамич", "металл", "пластик", "силикон", "стекл", "фарфор", "хрусталь")
_FORMAT_PREFIXES = ("глубок", "десерт", "набор", "обеден", "однораз", "плоск", "порцион", "сервиров", "столов", "супов")
_SHAPE_PREFIXES = ("квадрат", "кругл", "оваль", "фигур")
_STOP_TOKENS = {
    "без",
    "в",
    "во",
    "для",
    "до",
    "из",
    "и",
    "или",
    "к",
    "ко",
    "на",
    "над",
    "от",
    "по",
    "под",
    "при",
    "с",
    "со",
    "у",
}
_USE_CASE_PREFIXES = {"для", "под"}
_USE_CASE_ON_ALLOWED = {"стол", "праздник", "пикник", "сервировка", "сервировки"}
_SIZE_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?(?:мм|см|мл|л)$", re.IGNORECASE)
_NUMBER_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?$", re.IGNORECASE)
_LATIN_TOKEN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_LOW_COVERAGE_RATIO = 0.35
_PRODUCT_SUPPORT_RATIO = 0.34
_USE_CASE_SUPPORT_RATIO = 0.25
_ATTRIBUTE_SUPPORT_RATIO = 0.2
_LANGUAGE_SUPPORT_RATIO = 0.5
_PRODUCT_GENERIC_PREFIXES = ("аксессуар", "дом", "издел", "кухн", "посуд", "предмет", "товар")
_ADJECTIVE_ENDINGS = (
    "ый",
    "ий",
    "ой",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ого",
    "его",
    "ому",
    "ему",
    "ым",
    "им",
    "ую",
    "юю",
    "ых",
    "их",
    "ыми",
    "ими",
)


@dataclass(frozen=True)
class QueryProfileExtractionResult:
    """Extracted cluster profiles plus diagnostics."""

    project_id: int
    category_id: int
    profiles: list[ExtractedClusterProfile]
    diagnostics: QueryProfileExtractionDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class _MarkerOccurrence:
    raw_value: str
    normalized_value: str
    family: str | None
    query_text: str
    source_kind: str
    position: int
    is_anchor: bool


@dataclass(frozen=True)
class _ProfileEvidenceRow:
    row: HybridAnnotatedQueryRow
    ordered_tokens: tuple[str, ...]
    normalized_tokens: tuple[str, ...]
    source_kind: str
    is_anchor: bool


@dataclass
class _MarkerAggregate:
    slot: str
    normalized_value: str
    family: str | None
    raw_value_counts: Counter[str] = field(default_factory=Counter)
    query_set: set[str] = field(default_factory=set)
    source_kinds: set[str] = field(default_factory=set)
    evidence_queries: list[str] = field(default_factory=list)
    anchor_query_hits: set[str] = field(default_factory=set)
    anchor_head_hits: int = 0
    earliest_position: int = 99

    def add(self, occurrence: _MarkerOccurrence, *, is_anchor_head: bool) -> None:
        self.raw_value_counts[occurrence.raw_value] += 1
        self.query_set.add(occurrence.query_text)
        self.source_kinds.add(occurrence.source_kind)
        if occurrence.query_text not in self.evidence_queries:
            self.evidence_queries.append(occurrence.query_text)
        if occurrence.is_anchor:
            self.anchor_query_hits.add(occurrence.query_text)
        if is_anchor_head:
            self.anchor_head_hits += 1
        self.earliest_position = min(self.earliest_position, occurrence.position)

    @property
    def support_query_count(self) -> int:
        return len(self.query_set)

    def support_ratio(self, total_evidence_queries: int) -> float:
        if total_evidence_queries <= 0:
            return 0.0
        return self.support_query_count / total_evidence_queries

    @property
    def value(self) -> str:
        if not self.raw_value_counts:
            return self.normalized_value
        return sorted(self.raw_value_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _ordered_tokens(text_value: str) -> tuple[str, ...]:
    return tuple(token for token in str(text_value or "").split(" ") if token)


def _round_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _marker_round(value: float) -> float:
    return round(max(0.0, value), 4)


def _is_numeric_like(token: str) -> bool:
    return bool(_NUMBER_TOKEN_RE.match(token))


def _is_size_token(token: str) -> bool:
    return bool(_SIZE_TOKEN_RE.match(token))


def _is_latin_like(token: str) -> bool:
    return bool(_LATIN_TOKEN_RE.search(token))


def _matches_prefix(token: str, prefixes: tuple[str, ...]) -> bool:
    return any(token.startswith(prefix) for prefix in prefixes)


def _is_potential_product_token(normalized_token: str, raw_token: str) -> bool:
    if normalized_token in _PRODUCT_GENERIC_TOKENS or normalized_token in _STOP_TOKENS:
        return False
    if _matches_prefix(normalized_token, _PRODUCT_GENERIC_PREFIXES):
        return False
    if _matches_prefix(normalized_token, _MATERIAL_PREFIXES + _FORMAT_PREFIXES + _SHAPE_PREFIXES):
        return False
    if normalized_token in _COLOR_TOKENS:
        return False
    if _is_numeric_like(raw_token) or _is_size_token(raw_token) or _is_latin_like(raw_token):
        return False
    return True


def _is_noun_like_product_token(normalized_token: str, raw_token: str) -> bool:
    if not _is_potential_product_token(normalized_token, raw_token):
        return False
    return not normalized_token.endswith(_ADJECTIVE_ENDINGS)


def _is_broad_cluster(cluster: PersistedQueryClusterView, *, context: _ClusteringHeuristicsContext) -> bool:
    if cluster.query_count <= 3:
        return False
    label_basis = cluster.cluster_label_candidate or cluster.top_query_text
    strong_tokens = _strong_tokens(
        (
            _normalize_token_for_cluster(token, token_family_map=context.token_family_map)
            for token in _ordered_tokens(label_basis)
        ),
        weak_tokens=context.weak_tokens,
    )
    return len(strong_tokens) <= 1


def _source_priority(row: HybridAnnotatedQueryRow) -> tuple[int, float, str]:
    provenance_rank = {
        "individual": 0,
        "fallback": 1,
        "cluster": 2,
        "rejected": 3,
    }.get(row.provenance, 4)
    return provenance_rank, -float(row.ranking_value_used or 0), row.normalized_query_text


def _select_evidence_rows(
    *,
    cluster: PersistedQueryClusterView,
    hybrid_rows_by_query: dict[str, HybridAnnotatedQueryRow],
    context: _ClusteringHeuristicsContext,
) -> tuple[list[_ProfileEvidenceRow], HybridAnnotatedQueryRow | None, list[str]]:
    quality_flags: list[str] = []
    cluster_rows = [
        hybrid_rows_by_query[member.normalized_query_text]
        for member in cluster.members
        if member.normalized_query_text in hybrid_rows_by_query
    ]
    cluster_rows.sort(key=_source_priority)

    anchor_row = next((row for row in cluster_rows if row.provenance in {"individual", "fallback"}), None)
    if anchor_row is None:
        quality_flags.append("missing_anchor")
    if _is_broad_cluster(cluster, context=context):
        quality_flags.append("broad_cluster")

    selected_rows: list[HybridAnnotatedQueryRow] = []
    if anchor_row is not None:
        selected_rows.append(anchor_row)
    selected_rows.extend(
        row
        for row in cluster_rows
        if row.provenance == "cluster"
        and row.normalized_query_text != getattr(anchor_row, "normalized_query_text", None)
    )
    selected_rows = selected_rows[:8]

    if not selected_rows and cluster_rows:
        selected_rows = [row for row in cluster_rows if row.provenance != "rejected"][:4]

    evidence_rows = [
        _ProfileEvidenceRow(
            row=row,
            ordered_tokens=_ordered_tokens(row.normalized_query_text),
            normalized_tokens=tuple(
                _normalize_token_for_cluster(token, token_family_map=context.token_family_map)
                for token in _ordered_tokens(row.normalized_query_text)
            ),
            source_kind=row.provenance,
            is_anchor=row.provenance in {"individual", "fallback"},
        )
        for row in selected_rows
    ]

    coverage_ratio = (len(evidence_rows) / cluster.query_count) if cluster.query_count > 0 else 0.0
    if len(evidence_rows) <= 1:
        quality_flags.append("thin_evidence")
    if cluster.query_count >= 4 and coverage_ratio < _LOW_COVERAGE_RATIO:
        quality_flags.append("low_coverage")

    return evidence_rows, anchor_row, quality_flags


def _extract_use_case_occurrences(
    evidence: _ProfileEvidenceRow,
    *,
    consumed_indexes: set[int],
) -> list[_MarkerOccurrence]:
    occurrences: list[_MarkerOccurrence] = []
    tokens = evidence.ordered_tokens
    normalized_tokens = evidence.normalized_tokens

    for index, token in enumerate(tokens):
        normalized_token = normalized_tokens[index]
        if normalized_token in _USE_CASE_PREFIXES:
            next_tokens: list[str] = []
            next_normalized: list[str] = []
            pointer = index + 1
            while pointer < len(tokens):
                candidate = tokens[pointer]
                candidate_normalized = normalized_tokens[pointer]
                if candidate_normalized in _STOP_TOKENS or _is_numeric_like(candidate) or _is_size_token(candidate):
                    break
                if next_tokens and _is_noun_like_product_token(candidate_normalized, candidate):
                    break
                next_tokens.append(candidate)
                next_normalized.append(candidate_normalized)
                pointer += 1
                if len(next_tokens) >= 2:
                    break
            if next_tokens:
                consumed_indexes.update(range(index, index + 1 + len(next_tokens)))
                occurrences.append(
                    _MarkerOccurrence(
                        raw_value=" ".join((token, *next_tokens)),
                        normalized_value=" ".join((normalized_token, *next_normalized)),
                        family=None,
                        query_text=evidence.row.normalized_query_text,
                        source_kind=evidence.source_kind,
                        position=index,
                        is_anchor=evidence.is_anchor,
                    )
                )
        elif normalized_token == "на" and index + 1 < len(tokens):
            next_normalized = normalized_tokens[index + 1]
            next_raw = tokens[index + 1]
            if next_normalized in _USE_CASE_ON_ALLOWED and not _is_numeric_like(next_raw):
                consumed_indexes.update({index, index + 1})
                occurrences.append(
                    _MarkerOccurrence(
                        raw_value=f"{token} {next_raw}",
                        normalized_value=f"{normalized_token} {next_normalized}",
                        family=None,
                        query_text=evidence.row.normalized_query_text,
                        source_kind=evidence.source_kind,
                        position=index,
                        is_anchor=evidence.is_anchor,
                    )
                )

    return occurrences


def _extract_attribute_occurrences(
    evidence: _ProfileEvidenceRow,
    *,
    consumed_indexes: set[int],
) -> list[_MarkerOccurrence]:
    occurrences: list[_MarkerOccurrence] = []
    tokens = evidence.ordered_tokens
    normalized_tokens = evidence.normalized_tokens
    index = 0

    while index < len(tokens):
        token = tokens[index]
        normalized_token = normalized_tokens[index]
        if index in consumed_indexes:
            index += 1
            continue

        if normalized_token == "в" and index + 2 < len(tokens) and normalized_tokens[index + 1] == "виде":
            end_index = min(index + 4, len(tokens))
            consumed_indexes.update(range(index, end_index))
            occurrences.append(
                _MarkerOccurrence(
                    raw_value=" ".join(tokens[index:end_index]),
                    normalized_value=" ".join(normalized_tokens[index:end_index]),
                    family="shape",
                    query_text=evidence.row.normalized_query_text,
                    source_kind=evidence.source_kind,
                    position=index,
                    is_anchor=evidence.is_anchor,
                )
            )
            index = end_index
            continue

        if _is_size_token(token):
            consumed_indexes.add(index)
            occurrences.append(
                _MarkerOccurrence(
                    raw_value=token,
                    normalized_value=token.lower(),
                    family="size",
                    query_text=evidence.row.normalized_query_text,
                    source_kind=evidence.source_kind,
                    position=index,
                    is_anchor=evidence.is_anchor,
                )
            )
            index += 1
            continue

        if _is_numeric_like(token) and index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_normalized = normalized_tokens[index + 1]
            if next_normalized in {"мм", "см", "мл", "л"}:
                consumed_indexes.update({index, index + 1})
                occurrences.append(
                    _MarkerOccurrence(
                        raw_value=f"{token} {next_token}",
                        normalized_value=f"{token.lower()} {next_normalized}",
                        family="size",
                        query_text=evidence.row.normalized_query_text,
                        source_kind=evidence.source_kind,
                        position=index,
                        is_anchor=evidence.is_anchor,
                    )
                )
                index += 2
                continue
            if next_normalized in {"шт", "штук", "персоны", "персон", "предметов"}:
                consumed_indexes.update({index, index + 1})
                occurrences.append(
                    _MarkerOccurrence(
                        raw_value=f"{token} {next_token}",
                        normalized_value=f"{token.lower()} {next_normalized}",
                        family="quantity",
                        query_text=evidence.row.normalized_query_text,
                        source_kind=evidence.source_kind,
                        position=index,
                        is_anchor=evidence.is_anchor,
                    )
                )
                index += 2
                continue

        if normalized_token == "на" and index + 2 < len(tokens) and _is_numeric_like(tokens[index + 1]):
            if normalized_tokens[index + 2] in {"персоны", "персон"}:
                consumed_indexes.update({index, index + 1, index + 2})
                occurrences.append(
                    _MarkerOccurrence(
                        raw_value=" ".join(tokens[index : index + 3]),
                        normalized_value=f"на {tokens[index + 1].lower()} {normalized_tokens[index + 2]}",
                        family="quantity",
                        query_text=evidence.row.normalized_query_text,
                        source_kind=evidence.source_kind,
                        position=index,
                        is_anchor=evidence.is_anchor,
                    )
                )
                index += 3
                continue

        if normalized_token in _COLOR_TOKENS:
            family = "color"
        elif _matches_prefix(normalized_token, _MATERIAL_PREFIXES):
            family = "material"
        elif _matches_prefix(normalized_token, _FORMAT_PREFIXES):
            family = "format"
        elif _matches_prefix(normalized_token, _SHAPE_PREFIXES):
            family = "shape"
        else:
            family = None

        if family is not None:
            consumed_indexes.add(index)
            occurrences.append(
                _MarkerOccurrence(
                    raw_value=token,
                    normalized_value=normalized_token,
                    family=family,
                    query_text=evidence.row.normalized_query_text,
                    source_kind=evidence.source_kind,
                    position=index,
                    is_anchor=evidence.is_anchor,
                )
            )

        index += 1

    return occurrences


def _extract_product_occurrences(
    evidence: _ProfileEvidenceRow,
    *,
    consumed_indexes: set[int],
) -> list[_MarkerOccurrence]:
    occurrences: list[_MarkerOccurrence] = []
    last_index = len(evidence.ordered_tokens) - 1
    for index, token in enumerate(evidence.ordered_tokens):
        normalized_token = evidence.normalized_tokens[index]
        candidate_is_product = _is_potential_product_token(normalized_token, token)
        if index in consumed_indexes and not (candidate_is_product and index == last_index):
            continue
        if not candidate_is_product:
            continue
        occurrences.append(
            _MarkerOccurrence(
                raw_value=token,
                normalized_value=normalized_token,
                family=None,
                query_text=evidence.row.normalized_query_text,
                source_kind=evidence.source_kind,
                position=index,
                is_anchor=evidence.is_anchor,
            )
        )
    return occurrences


def _extract_language_occurrences(
    evidence: _ProfileEvidenceRow,
    *,
    consumed_indexes: set[int],
) -> list[_MarkerOccurrence]:
    residual_tokens = [
        (index, token, evidence.normalized_tokens[index])
        for index, token in enumerate(evidence.ordered_tokens)
        if index not in consumed_indexes
        and evidence.normalized_tokens[index] not in _PRODUCT_GENERIC_TOKENS
        and evidence.normalized_tokens[index] not in _STOP_TOKENS
        and not _is_numeric_like(token)
        and not _is_size_token(token)
        and not _is_latin_like(token)
    ]
    if len(residual_tokens) < 2:
        return []
    phrase = residual_tokens[:3]
    return [
        _MarkerOccurrence(
            raw_value=" ".join(token for _index, token, _normalized in phrase),
            normalized_value=" ".join(normalized for _index, _token, normalized in phrase),
            family=None,
            query_text=evidence.row.normalized_query_text,
            source_kind=evidence.source_kind,
            position=phrase[0][0],
            is_anchor=evidence.is_anchor,
        )
    ]


def _aggregate_occurrences(slot: str, occurrences: list[_MarkerOccurrence], *, anchor_head_candidate: str | None) -> list[_MarkerAggregate]:
    aggregates: dict[tuple[str | None, str], _MarkerAggregate] = {}
    for occurrence in occurrences:
        key = (occurrence.family, occurrence.normalized_value)
        aggregate = aggregates.setdefault(
            key,
            _MarkerAggregate(
                slot=slot,
                normalized_value=occurrence.normalized_value,
                family=occurrence.family,
            ),
        )
        aggregate.add(
            occurrence,
            is_anchor_head=bool(anchor_head_candidate and occurrence.normalized_value == anchor_head_candidate and occurrence.is_anchor),
        )

    return sorted(
        aggregates.values(),
        key=lambda item: (
            -item.support_query_count,
            -item.anchor_head_hits,
            item.earliest_position,
            item.normalized_value,
        ),
    )


def _decision_from_aggregate(
    aggregate: _MarkerAggregate,
    *,
    total_evidence_queries: int,
    selected: bool,
    reason: str,
) -> QueryProfileMarkerDecision:
    return QueryProfileMarkerDecision(
        slot=aggregate.slot,
        value=aggregate.value,
        normalized_value=aggregate.normalized_value,
        family=aggregate.family,
        support_query_count=aggregate.support_query_count,
        support_ratio=_marker_round(aggregate.support_ratio(total_evidence_queries)),
        evidence_queries=aggregate.evidence_queries[:3],
        source_kinds=sorted(aggregate.source_kinds),
        selected=selected,
        reason=reason,
    )


def _marker_from_decision(decision: QueryProfileMarkerDecision) -> QueryProfileMarker:
    return QueryProfileMarker(
        value=decision.value,
        normalized_value=decision.normalized_value,
        family=decision.family,
        support_query_count=decision.support_query_count,
        support_share=decision.support_ratio,
        weighted_support=float(decision.support_query_count),
        evidence_queries=decision.evidence_queries,
    )


def _select_product_markers(
    aggregates: list[_MarkerAggregate],
    *,
    total_evidence_queries: int,
    anchor_head_candidate: str | None,
    anchor_candidates: set[str],
) -> tuple[list[QueryProfileMarker], list[QueryProfileMarkerDecision], list[str], bool]:
    quality_flags: list[str] = []
    decisions: list[QueryProfileMarkerDecision] = []
    if not aggregates:
        return [], decisions, quality_flags, False

    if anchor_head_candidate:
        primary = next((item for item in aggregates if item.normalized_value == anchor_head_candidate), None)
        if primary is None:
            primary = next((item for item in aggregates if item.normalized_value in anchor_candidates), None)
    else:
        primary = aggregates[0]

    if primary is None:
        for item in aggregates:
            decisions.append(
                _decision_from_aggregate(
                    item,
                    total_evidence_queries=total_evidence_queries,
                    selected=False,
                    reason="rejected_not_anchor_aligned",
                )
            )
        return [], decisions, quality_flags, False

    primary_ratio = primary.support_ratio(total_evidence_queries)
    primary_anchor_aligned = primary.normalized_value in anchor_candidates if anchor_candidates else bool(primary.anchor_query_hits)
    stable_support = (
        primary.support_query_count >= 2 and primary_ratio >= _PRODUCT_SUPPORT_RATIO
    ) or (total_evidence_queries <= 2 and primary_ratio >= 0.5)
    if not anchor_candidates and primary.support_query_count >= 2 and primary_ratio >= 0.6:
        primary_anchor_aligned = True

    competitor = next(
        (
            item
            for item in aggregates
            if item.normalized_value != primary.normalized_value
            and item.support_query_count >= max(1, primary.support_query_count - 1)
            and item.support_ratio(total_evidence_queries) >= max(_PRODUCT_SUPPORT_RATIO, primary_ratio - 0.15)
        ),
        None,
    )
    if competitor is not None and stable_support:
        quality_flags.append("conflicting_product_type_marker")
        stable_support = False

    primary_selected = stable_support and primary_anchor_aligned
    if primary_selected:
        selected_reason = "selected_anchor_head_stable_family" if primary.normalized_value == anchor_head_candidate else "selected_anchor_aligned_stable_family"
    elif competitor is not None:
        selected_reason = "rejected_competing_product_family"
    elif not primary_anchor_aligned:
        selected_reason = "rejected_not_anchor_aligned"
    else:
        selected_reason = "rejected_low_support"

    selected_markers: list[QueryProfileMarker] = []
    for item in aggregates:
        if item.normalized_value == primary.normalized_value:
            decision = _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=primary_selected,
                reason=selected_reason,
            )
            decisions.append(decision)
            if decision.selected:
                selected_markers.append(_marker_from_decision(decision))
            continue

        if competitor is not None and item.normalized_value == competitor.normalized_value:
            reason = "rejected_competing_product_family"
        elif primary_selected:
            reason = f"rejected_weaker_than_selected:{primary.normalized_value}"
        elif item.normalized_value not in anchor_candidates and anchor_candidates:
            reason = "rejected_not_anchor_aligned"
        else:
            reason = "rejected_low_support"
        decisions.append(
            _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=False,
                reason=reason,
            )
        )

    if selected_markers:
        return selected_markers[:1], decisions, quality_flags, primary_selected

    fallback_primary = next(
        (
            item
            for item in aggregates
            if item.support_query_count >= 2 or item.support_ratio(total_evidence_queries) >= 0.2
        ),
        None,
    )
    if fallback_primary is None:
        return [], decisions, quality_flags, False

    fallback_decisions: list[QueryProfileMarkerDecision] = []
    fallback_marker: QueryProfileMarker | None = None
    for item in aggregates:
        if item.normalized_value == fallback_primary.normalized_value:
            decision = _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=True,
                reason="selected_evidence_fallback",
            )
            fallback_marker = _marker_from_decision(decision)
        else:
            decision = _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=False,
                reason=f"rejected_weaker_than_selected:{fallback_primary.normalized_value}",
            )
        fallback_decisions.append(decision)

    return [fallback_marker] if fallback_marker is not None else [], fallback_decisions, quality_flags, bool(
        fallback_primary.anchor_query_hits
    )


def _apply_product_noun_guard(
    product_type_markers: list[QueryProfileMarker],
    product_decisions: list[QueryProfileMarkerDecision],
    *,
    anchor_noun_candidates: set[str],
) -> tuple[list[QueryProfileMarker], list[QueryProfileMarkerDecision]]:
    if not product_type_markers:
        return product_type_markers, product_decisions

    selected_marker = product_type_markers[0]
    noun_like = _is_noun_like_product_token(selected_marker.normalized_value, selected_marker.value)
    anchor_noun_like = selected_marker.normalized_value in anchor_noun_candidates
    if noun_like and (selected_marker.support_query_count >= 2 or anchor_noun_like):
        return product_type_markers, product_decisions

    updated_decisions = [
        replace(decision, selected=False, reason="rejected_non_noun_product_candidate")
        if decision.slot == "product_type"
        and decision.selected
        and decision.normalized_value == selected_marker.normalized_value
        else decision
        for decision in product_decisions
    ]
    return [], updated_decisions


def _select_slot_markers(
    slot: str,
    aggregates: list[_MarkerAggregate],
    *,
    total_evidence_queries: int,
    min_support_ratio: float,
    max_selected: int,
) -> tuple[list[QueryProfileMarker], list[QueryProfileMarkerDecision]]:
    selected_markers: list[QueryProfileMarker] = []
    decisions: list[QueryProfileMarkerDecision] = []
    selected_count = 0

    for item in aggregates:
        ratio = item.support_ratio(total_evidence_queries)
        anchor_supported = bool(item.anchor_query_hits)
        stable_support = ratio >= min_support_ratio and (item.support_query_count >= 2 or anchor_supported)
        if stable_support and selected_count < max_selected:
            decision = _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=True,
                reason=f"selected_stable_{slot}",
            )
            selected_markers.append(_marker_from_decision(decision))
            selected_count += 1
        else:
            decision = _decision_from_aggregate(
                item,
                total_evidence_queries=total_evidence_queries,
                selected=False,
                reason="rejected_low_support" if not stable_support else "rejected_selection_limit",
            )
        decisions.append(decision)

    return selected_markers, decisions


def _select_attribute_markers(
    aggregates: list[_MarkerAggregate],
    *,
    total_evidence_queries: int,
) -> tuple[list[QueryProfileMarker], list[QueryProfileMarkerDecision], list[str]]:
    selected_markers: list[QueryProfileMarker] = []
    decisions: list[QueryProfileMarkerDecision] = []
    conflicting_families: list[str] = []
    grouped: dict[str, list[_MarkerAggregate]] = defaultdict(list)

    for item in aggregates:
        grouped[item.family or "attribute"].append(item)

    for family, items in grouped.items():
        items = sorted(
            items,
            key=lambda item: (-item.support_query_count, item.earliest_position, item.normalized_value),
        )
        top = items[0]
        top_ratio = top.support_ratio(total_evidence_queries)
        top_is_stable = top_ratio >= _ATTRIBUTE_SUPPORT_RATIO and top.support_query_count >= 1
        contender = next(
            (
                item
                for item in items[1:]
                if item.support_ratio(total_evidence_queries) >= max(_ATTRIBUTE_SUPPORT_RATIO, top_ratio - 0.15)
            ),
            None,
        )

        if contender is not None and top_is_stable:
            if family != "attribute":
                conflicting_families.append(family)
            for item in items:
                decisions.append(
                    _decision_from_aggregate(
                        item,
                        total_evidence_queries=total_evidence_queries,
                        selected=False,
                        reason="rejected_conflicting_attribute_family",
                    )
                )
            continue

        for index, item in enumerate(items):
            ratio = item.support_ratio(total_evidence_queries)
            stable_support = ratio >= _ATTRIBUTE_SUPPORT_RATIO and (
                item.support_query_count >= 2
                or bool(item.anchor_query_hits)
                or (item.family in {"size", "quantity"} and ratio >= _ATTRIBUTE_SUPPORT_RATIO)
            )
            if index == 0 and stable_support:
                decision = _decision_from_aggregate(
                    item,
                    total_evidence_queries=total_evidence_queries,
                    selected=True,
                    reason="selected_stable_attribute",
                )
                selected_markers.append(_marker_from_decision(decision))
            else:
                decision = _decision_from_aggregate(
                    item,
                    total_evidence_queries=total_evidence_queries,
                    selected=False,
                    reason="rejected_low_support" if not stable_support else f"rejected_weaker_than_selected:{top.normalized_value}",
                )
            decisions.append(decision)

    selected_markers.sort(
        key=lambda marker: (
            _ATTRIBUTE_FAMILY_ORDER.index(marker.family) if marker.family in _ATTRIBUTE_FAMILY_ORDER else len(_ATTRIBUTE_FAMILY_ORDER),
            -marker.support_query_count,
            marker.normalized_value,
        )
    )
    return selected_markers, decisions, sorted(set(conflicting_families))


def _build_profile_label(
    *,
    cluster: PersistedQueryClusterView,
    product_type_markers: list[QueryProfileMarker],
    use_case_markers: list[QueryProfileMarker],
    attribute_markers: list[QueryProfileMarker],
) -> str:
    if not product_type_markers:
        return ""
    label_parts: list[str] = []
    if product_type_markers:
        label_parts.append(product_type_markers[0].value)
    if use_case_markers:
        label_parts.append(use_case_markers[0].value)
    if attribute_markers:
        label_parts.append(attribute_markers[0].value)
    if label_parts:
        return " ".join(label_parts)
    return cluster.cluster_label_candidate or cluster.top_query_text or cluster.cluster_key


def _profile_confidence(
    *,
    cluster: PersistedQueryClusterView,
    evidence_rows: list[_ProfileEvidenceRow],
    anchor_row: HybridAnnotatedQueryRow | None,
    product_type_markers: list[QueryProfileMarker],
    conflicting_attribute_families: list[str],
    quality_flags: list[str],
    product_anchor_aligned: bool,
) -> tuple[float, dict[str, Any]]:
    support_queries = product_type_markers[0].support_query_count if product_type_markers else 0
    support_ratio = product_type_markers[0].support_share if product_type_markers else 0.0
    source_diversity = len({row.source_kind for row in evidence_rows})
    coverage_ratio = (len(evidence_rows) / cluster.query_count) if cluster.query_count > 0 else 0.0
    conflict_presence = bool(conflicting_attribute_families or "conflicting_product_type_marker" in quality_flags)
    low_coverage = coverage_ratio < _LOW_COVERAGE_RATIO or "low_coverage" in quality_flags
    weak_evidence = len(evidence_rows) <= 1 or "thin_evidence" in quality_flags or "broad_cluster" in quality_flags or not product_type_markers

    confidence = support_ratio
    if source_diversity > 1:
        confidence += 0.1
    if product_anchor_aligned:
        confidence += 0.1
    if anchor_row is None:
        confidence -= 0.15
    if conflict_presence:
        confidence -= 0.15
    if low_coverage:
        confidence -= 0.1
    if weak_evidence:
        confidence -= 0.15

    if not product_type_markers:
        confidence = min(confidence, 0.35)
    if conflict_presence:
        confidence = min(confidence, 0.45)
    if weak_evidence:
        confidence = min(confidence, 0.4)

    return _round_score(confidence), {
        "support_queries": support_queries,
        "support_ratio": _marker_round(support_ratio),
        "source_diversity": source_diversity,
        "anchor_alignment": product_anchor_aligned,
        "conflict_presence": conflict_presence,
        "low_coverage": low_coverage,
        "weak_evidence": weak_evidence,
        "has_anchor": anchor_row is not None,
    }


def _profile_strength(
    *,
    confidence: float,
    product_type_markers: list[QueryProfileMarker],
    use_case_markers: list[QueryProfileMarker],
    attribute_markers: list[QueryProfileMarker],
    conflicting_attribute_families: list[str],
    quality_flags: list[str],
    confidence_factors: dict[str, Any],
) -> str:
    if not product_type_markers and not use_case_markers and not attribute_markers:
        return "empty"
    if (
        not product_type_markers
        or confidence < 0.45
        or confidence_factors.get("conflict_presence")
        or confidence_factors.get("weak_evidence")
    ):
        return "weak"
    if (
        confidence >= 0.75
        and product_type_markers[0].support_share >= 0.65
        and confidence_factors.get("source_diversity", 0) > 1
        and confidence_factors.get("anchor_alignment")
        and not conflicting_attribute_families
        and "broad_cluster" not in quality_flags
    ):
        return "strong"
    return "medium"


def _extract_profile_for_cluster(
    *,
    cluster: PersistedQueryClusterView,
    hybrid_rows_by_query: dict[str, HybridAnnotatedQueryRow],
    context: _ClusteringHeuristicsContext,
) -> ExtractedClusterProfile:
    evidence_rows, anchor_row, quality_flags = _select_evidence_rows(
        cluster=cluster,
        hybrid_rows_by_query=hybrid_rows_by_query,
        context=context,
    )

    product_occurrences: list[_MarkerOccurrence] = []
    use_case_occurrences: list[_MarkerOccurrence] = []
    attribute_occurrences: list[_MarkerOccurrence] = []
    language_occurrences: list[_MarkerOccurrence] = []
    anchor_product_candidates: list[str] = []
    anchor_noun_candidates: set[str] = set()

    for evidence in evidence_rows:
        consumed_indexes: set[int] = set()
        use_case_occurrences.extend(_extract_use_case_occurrences(evidence, consumed_indexes=consumed_indexes))
        attribute_occurrences.extend(_extract_attribute_occurrences(evidence, consumed_indexes=consumed_indexes))
        row_product_occurrences = _extract_product_occurrences(evidence, consumed_indexes=consumed_indexes)
        product_occurrences.extend(row_product_occurrences)
        if evidence.is_anchor:
            anchor_product_candidates = [occ.normalized_value for occ in row_product_occurrences]
            anchor_noun_candidates = {
                normalized_token
                for token, normalized_token in zip(evidence.ordered_tokens, evidence.normalized_tokens, strict=False)
                if _is_noun_like_product_token(normalized_token, token)
            }
        language_occurrences.extend(_extract_language_occurrences(evidence, consumed_indexes=consumed_indexes))

    total_evidence_queries = max(len(evidence_rows), 1)
    anchor_head_candidate = anchor_product_candidates[0] if anchor_product_candidates else None
    anchor_product_set = set(anchor_product_candidates)

    product_aggregates = _aggregate_occurrences(
        "product_type",
        product_occurrences,
        anchor_head_candidate=anchor_head_candidate,
    )
    use_case_aggregates = _aggregate_occurrences("use_case", use_case_occurrences, anchor_head_candidate=None)
    attribute_aggregates = _aggregate_occurrences("attribute", attribute_occurrences, anchor_head_candidate=None)
    language_aggregates = _aggregate_occurrences("language", language_occurrences, anchor_head_candidate=None)

    product_type_markers, product_decisions, product_flags, product_anchor_aligned = _select_product_markers(
        product_aggregates,
        total_evidence_queries=total_evidence_queries,
        anchor_head_candidate=anchor_head_candidate,
        anchor_candidates=anchor_product_set,
    )
    product_type_markers, product_decisions = _apply_product_noun_guard(
        product_type_markers,
        product_decisions,
        anchor_noun_candidates=anchor_noun_candidates,
    )
    if not product_type_markers:
        product_anchor_aligned = False
    quality_flags.extend(product_flags)

    use_case_markers, use_case_decisions = _select_slot_markers(
        "use_case",
        use_case_aggregates,
        total_evidence_queries=total_evidence_queries,
        min_support_ratio=_USE_CASE_SUPPORT_RATIO,
        max_selected=3,
    )
    attribute_markers, attribute_decisions, conflicting_attribute_families = _select_attribute_markers(
        attribute_aggregates,
        total_evidence_queries=total_evidence_queries,
    )
    language_markers, language_decisions = _select_slot_markers(
        "language",
        language_aggregates,
        total_evidence_queries=total_evidence_queries,
        min_support_ratio=_LANGUAGE_SUPPORT_RATIO,
        max_selected=2,
    )

    if not product_type_markers:
        quality_flags.append("no_product_type_marker")
    if conflicting_attribute_families:
        quality_flags.append("conflicting_attribute_markers")

    confidence, confidence_factors = _profile_confidence(
        cluster=cluster,
        evidence_rows=evidence_rows,
        anchor_row=anchor_row,
        product_type_markers=product_type_markers,
        conflicting_attribute_families=conflicting_attribute_families,
        quality_flags=quality_flags,
        product_anchor_aligned=product_anchor_aligned,
    )
    strength = _profile_strength(
        confidence=confidence,
        product_type_markers=product_type_markers,
        use_case_markers=use_case_markers,
        attribute_markers=attribute_markers,
        conflicting_attribute_families=conflicting_attribute_families,
        quality_flags=quality_flags,
        confidence_factors=confidence_factors,
    )

    marker_decisions = sorted(
        [*product_decisions, *use_case_decisions, *attribute_decisions, *language_decisions],
        key=lambda decision: (
            0 if decision.selected else 1,
            decision.slot,
            -decision.support_query_count,
            decision.normalized_value,
        ),
    )
    source_diversity = len({row.source_kind for row in evidence_rows})

    return ExtractedClusterProfile(
        cluster_key=cluster.cluster_key,
        profile_label_candidate=_build_profile_label(
            cluster=cluster,
            product_type_markers=product_type_markers,
            use_case_markers=use_case_markers,
            attribute_markers=attribute_markers,
        ),
        profile_strength=strength,
        profile_confidence=confidence,
        source_cluster_key=cluster.cluster_key,
        source_anchor_query=anchor_row.normalized_query_text if anchor_row is not None else None,
        source_query_examples=[row.row.normalized_query_text for row in evidence_rows[:5]],
        query_count=cluster.query_count,
        evidence_query_count=len(evidence_rows),
        weighted_signal=_marker_round(len(evidence_rows) + (0.25 * max(source_diversity - 1, 0))),
        product_type_markers=product_type_markers,
        use_case_markers=use_case_markers,
        attribute_markers=attribute_markers,
        language_markers=language_markers,
        marker_decisions=marker_decisions,
        conflicting_attribute_families=conflicting_attribute_families,
        quality_flags=sorted(set(quality_flags)),
        confidence_factors=confidence_factors,
    )


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    profiles: list[ExtractedClusterProfile],
    top_limit: int,
    samples_limit: int,
) -> QueryProfileExtractionDiagnostics:
    strength_counts = Counter(profile.profile_strength for profile in profiles)
    counts_by_marker_type = {
        "product_type": sum(len(profile.product_type_markers) for profile in profiles),
        "use_case": sum(len(profile.use_case_markers) for profile in profiles),
        "attribute": sum(len(profile.attribute_markers) for profile in profiles),
        "language": sum(len(profile.language_markers) for profile in profiles),
    }
    counts_by_attribute_family = Counter(
        marker.family
        for profile in profiles
        for marker in profile.attribute_markers
        if marker.family
    )
    sorted_by_signal = sorted(
        profiles,
        key=lambda profile: (-profile.profile_confidence, -profile.weighted_signal, -profile.query_count, profile.cluster_key),
    )
    conflicting_profiles = [
        profile
        for profile in sorted_by_signal
        if profile.conflicting_attribute_families or "conflicting_product_type_marker" in profile.quality_flags
    ]
    low_confidence_profiles = [
        profile
        for profile in sorted_by_signal
        if profile.profile_confidence < 0.45 or profile.profile_strength in {"weak", "empty"}
    ]

    return QueryProfileExtractionDiagnostics(
        project_id=project_id,
        category_id=category_id,
        total_profiles_built=len(profiles),
        strong_profiles_count=int(strength_counts.get("strong", 0)),
        medium_profiles_count=int(strength_counts.get("medium", 0)),
        weak_profiles_count=int(strength_counts.get("weak", 0)),
        empty_profiles_count=int(strength_counts.get("empty", 0)),
        profiles_with_conflicts_count=len(conflicting_profiles),
        profiles_with_low_confidence_count=len(low_confidence_profiles),
        counts_by_marker_type=counts_by_marker_type,
        counts_by_attribute_family=dict(sorted(counts_by_attribute_family.items(), key=lambda item: (-item[1], item[0]))),
        sample_profiles=sorted_by_signal[:samples_limit],
        top_profiles_by_signal=sorted_by_signal[:top_limit],
        profiles_with_conflicting_markers=conflicting_profiles[:samples_limit],
        profiles_with_low_confidence=low_confidence_profiles[:samples_limit],
    )


def run_query_profile_extraction(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    top_limit: int = 20,
    samples_limit: int = 20,
    refresh_hybrid: bool = False,
    persist: bool = False,
) -> QueryProfileExtractionResult:
    """Run deterministic cluster-profile extraction over persisted query pipeline state."""

    del persist  # v1 profile extraction is projection-only by design.

    hybrid_rows = get_persisted_hybrid_projection(
        session,
        project_id=project_id,
        category_id=category_id,
        refresh_if_missing=refresh_hybrid,
        samples_limit=max(1, int(samples_limit)),
    )
    clean_rows = get_clean_query_set(session, project_id=project_id, category_id=category_id)
    clusters = get_query_clusters(session, project_id=project_id, category_id=category_id)
    context = _build_clustering_context(clean_rows) if clean_rows else _build_clustering_context([])
    hybrid_rows_by_query = {row.normalized_query_text: row for row in hybrid_rows}

    profiles = [
        _extract_profile_for_cluster(
            cluster=cluster,
            hybrid_rows_by_query=hybrid_rows_by_query,
            context=context,
        )
        for cluster in clusters
    ]
    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        profiles=profiles,
        top_limit=max(1, int(top_limit)),
        samples_limit=max(1, int(samples_limit)),
    )
    return QueryProfileExtractionResult(
        project_id=project_id,
        category_id=category_id,
        profiles=profiles,
        diagnostics=diagnostics,
    )
