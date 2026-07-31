"""Deterministic scoring-preparation layer between query profiles and SKU evidence."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.seo.query_pipeline import normalize_query_text, run_query_profile_extraction
from app.services.seo.query_pipeline.diagnostics import ExtractedClusterProfile, QueryProfileMarker, _serialize_value


PreparationStatus = Literal["matched", "not_matched", "unknown"]
MarkerStatus = Literal["matched", "missed", "conflicting", "unknown"]
ReadinessStatus = Literal["ready", "partial", "poor"]

_PRODUCT_SCOPE_FIELDS = ("title_text", "title_tokens", "attributes_text", "attributes_tokens", "description_text", "description_tokens")
_AUXILIARY_FIELD_ORDER = ("sizes", "colors", "dimensions")


class QueryScoringPreparationError(Exception):
    """Base scoring preparation error."""


class QueryScoringPreparationNotFoundError(QueryScoringPreparationError):
    """Raised when the target SKU is unavailable in the selected scope."""


class QueryScoringPreparationScopeError(QueryScoringPreparationError):
    """Raised when the target SKU falls outside the selected category scope."""


@dataclass(frozen=True)
class ScoringPreparationMarkerEvaluation:
    """One marker-level matching decision."""

    value: str
    normalized_value: str
    family: str | None
    status: MarkerStatus
    fields_checked: list[str] = field(default_factory=list)
    matched_fields: list[str] = field(default_factory=list)
    conflicting_with: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class ProductTypeMatchResult:
    """Explainable product-type comparison output."""

    status: PreparationStatus
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    marker_evaluations: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)


@dataclass(frozen=True)
class UseCaseMatchResult:
    """Explainable use-case comparison output."""

    matched_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    missed_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    unknown_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class AttributeMatchResult:
    """Explainable attribute comparison output."""

    matched_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    missed_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    conflicting_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    unknown_markers: list[ScoringPreparationMarkerEvaluation] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class SkuEvidenceSummary:
    """Summary of which SKU evidence fields were available and used."""

    title_present: bool
    attributes_present: bool
    description_present: bool
    normalized_evidence_fields_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class PreparationFlags:
    """Profile/SKU quality flags exposed to debug views."""

    weak_profile: bool = False
    empty_profile: bool = False
    missing_product_type: bool = False
    conflicting_profile_markers: bool = False
    insufficient_sku_data: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class ClusterScoringPreparation:
    """Explainable preparation object for one cluster profile against one SKU."""

    cluster_key: str
    profile_label_candidate: str
    profile_strength: str
    profile_confidence: float
    product_type_match: ProductTypeMatchResult
    use_case_match: UseCaseMatchResult
    attribute_match: AttributeMatchResult
    sku_evidence_summary: SkuEvidenceSummary
    preparation_flags: PreparationFlags
    readiness_for_scoring: ReadinessStatus

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryScoringPreparationDiagnostics:
    """Readable diagnostics for one scoring-preparation run."""

    project_id: int
    category_id: int
    nm_id: int
    total_cluster_comparisons: int = 0
    ready_count: int = 0
    partial_count: int = 0
    poor_count: int = 0
    product_type_matched_rate: float = 0.0
    use_case_matched_rate: float = 0.0
    attribute_matched_rate: float = 0.0
    insufficient_sku_data_count: int = 0
    weak_profile_count: int = 0
    missing_product_type_count: int = 0
    sample_preparations: list[ClusterScoringPreparation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryScoringPreparationResult:
    """All preparation objects plus diagnostics for one SKU scope."""

    project_id: int
    category_id: int
    nm_id: int
    sku_evidence_summary: SkuEvidenceSummary
    preparations: list[ClusterScoringPreparation]
    diagnostics: QueryScoringPreparationDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class _SkuEvidenceField:
    name: str
    raw_text: str
    normalized_text: str = ""
    tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class _SkuEvidenceBundle:
    nm_id: int
    subject_id: int | None
    title_text: str
    attributes_text: str
    description_text: str
    searchable_fields: list[_SkuEvidenceField]
    summary: SkuEvidenceSummary


@dataclass(frozen=True)
class _MatchedField:
    field_name: str
    snippet: str


def _round_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _truncate(value: str, *, limit: int = 140) -> str:
    text_value = str(value or "").strip()
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[: max(0, limit - 3)].rstrip()}..."


def _coerce_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped[:1] in {"[", "{"}:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _flatten_jsonish(value: Any) -> list[str]:
    resolved = _coerce_jsonish(value)
    if resolved is None:
        return []
    if isinstance(resolved, str):
        normalized = resolved.strip()
        return [normalized] if normalized else []
    if isinstance(resolved, (int, float, bool)):
        return [str(resolved)]
    if isinstance(resolved, list):
        parts: list[str] = []
        for item in resolved:
            if isinstance(item, dict) and "name" in item and "value" in item:
                name = str(item.get("name") or "").strip()
                value_parts = _flatten_jsonish(item.get("value"))
                joined = " ".join(part for part in ([name] + value_parts) if part)
                if joined:
                    parts.append(joined)
                continue
            parts.extend(_flatten_jsonish(item))
        return parts
    if isinstance(resolved, dict):
        parts = []
        for key, item in resolved.items():
            key_text = str(key or "").strip()
            value_parts = _flatten_jsonish(item)
            if value_parts:
                combined = " ".join(part for part in ([key_text] + value_parts) if part)
                if combined:
                    parts.append(combined)
            elif key_text:
                parts.append(key_text)
        return parts
    return [str(resolved)]


def _build_text_field(field_name: str, raw_text: str | None) -> list[_SkuEvidenceField]:
    normalized_text = normalize_query_text(raw_text or "")
    if not normalized_text:
        return []
    tokens = frozenset(token for token in normalized_text.split(" ") if token)
    return [
        _SkuEvidenceField(
            name=f"{field_name}_text",
            raw_text=str(raw_text or ""),
            normalized_text=normalized_text,
        ),
        _SkuEvidenceField(
            name=f"{field_name}_tokens",
            raw_text=str(raw_text or ""),
            tokens=tokens,
        ),
    ]


def _fetch_sku_row(session: Session, *, project_id: int, nm_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT
                project_id,
                nm_id,
                subject_id,
                title,
                description,
                characteristics,
                sizes,
                colors,
                dimensions
            FROM v_wb_product_source
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"project_id": project_id, "nm_id": nm_id},
    ).mappings().first()
    if row is None:
        raise QueryScoringPreparationNotFoundError(
            f"SKU nm_id={nm_id} is not available in project_id={project_id}"
        )
    return dict(row)


def _build_sku_evidence(row: dict[str, Any]) -> _SkuEvidenceBundle:
    title_text = str(row.get("title") or "").strip()
    description_text = str(row.get("description") or "").strip()

    attribute_parts: list[str] = []
    attribute_parts.extend(_flatten_jsonish(row.get("characteristics")))
    for field_name in _AUXILIARY_FIELD_ORDER:
        attribute_parts.extend(_flatten_jsonish(row.get(field_name)))
    attributes_text = " ".join(part for part in attribute_parts if part).strip()

    searchable_fields = [
        *_build_text_field("title", title_text),
        *_build_text_field("attributes", attributes_text),
        *_build_text_field("description", description_text),
    ]
    normalized_fields_used = [field.name for field in searchable_fields]
    summary = SkuEvidenceSummary(
        title_present=bool(title_text),
        attributes_present=bool(attributes_text),
        description_present=bool(description_text),
        normalized_evidence_fields_used=normalized_fields_used,
    )
    return _SkuEvidenceBundle(
        nm_id=int(row["nm_id"]),
        subject_id=int(row["subject_id"]) if row.get("subject_id") is not None else None,
        title_text=title_text,
        attributes_text=attributes_text,
        description_text=description_text,
        searchable_fields=searchable_fields,
        summary=summary,
    )


def _match_marker_against_fields(
    marker: QueryProfileMarker,
    searchable_fields: list[_SkuEvidenceField],
) -> tuple[list[_MatchedField], list[str]]:
    normalized_value = normalize_query_text(marker.normalized_value or marker.value or "")
    if not normalized_value:
        return [], [field.name for field in searchable_fields]

    matched_fields: list[_MatchedField] = []
    checked_fields = [field.name for field in searchable_fields]
    marker_tokens = tuple(token for token in normalized_value.split(" ") if token)
    for field in searchable_fields:
        if field.name.endswith("_text"):
            if normalized_value and normalized_value in field.normalized_text:
                matched_fields.append(_MatchedField(field_name=field.name, snippet=_truncate(field.raw_text)))
        elif field.name.endswith("_tokens"):
            if marker_tokens and all(token in field.tokens for token in marker_tokens):
                matched_fields.append(_MatchedField(field_name=field.name, snippet=_truncate(field.raw_text)))

    deduped_by_field: dict[str, _MatchedField] = {}
    for item in matched_fields:
        deduped_by_field.setdefault(item.field_name, item)
    return list(deduped_by_field.values()), checked_fields


def _evaluate_marker(
    marker: QueryProfileMarker,
    *,
    searchable_fields: list[_SkuEvidenceField],
    found_competing_values: set[str] | None = None,
) -> ScoringPreparationMarkerEvaluation:
    matched_fields, checked_fields = _match_marker_against_fields(marker, searchable_fields)
    competing_values = sorted(value for value in (found_competing_values or set()) if value != marker.normalized_value)
    evidence = [f"{item.field_name}: {item.snippet}" for item in matched_fields]

    if not checked_fields:
        return ScoringPreparationMarkerEvaluation(
            value=marker.value,
            normalized_value=marker.normalized_value,
            family=marker.family,
            status="unknown",
            fields_checked=[],
            matched_fields=[],
            evidence=[],
            reason="sku_evidence_unavailable",
        )
    if competing_values:
        return ScoringPreparationMarkerEvaluation(
            value=marker.value,
            normalized_value=marker.normalized_value,
            family=marker.family,
            status="conflicting",
            fields_checked=checked_fields,
            matched_fields=[item.field_name for item in matched_fields],
            conflicting_with=competing_values,
            evidence=evidence,
            reason=f"found_competing_{marker.family or 'attribute'}_markers",
        )
    if matched_fields:
        return ScoringPreparationMarkerEvaluation(
            value=marker.value,
            normalized_value=marker.normalized_value,
            family=marker.family,
            status="matched",
            fields_checked=checked_fields,
            matched_fields=[item.field_name for item in matched_fields],
            evidence=evidence,
            reason="marker_found_in_sku_evidence",
        )
    return ScoringPreparationMarkerEvaluation(
        value=marker.value,
        normalized_value=marker.normalized_value,
        family=marker.family,
        status="missed",
        fields_checked=checked_fields,
        matched_fields=[],
        evidence=[],
        reason="marker_not_found_in_sku_evidence",
    )


def _build_attribute_lexicon(profiles: list[ExtractedClusterProfile]) -> dict[str, dict[str, QueryProfileMarker]]:
    lexicon: dict[str, dict[str, QueryProfileMarker]] = defaultdict(dict)
    for profile in profiles:
        for marker in profile.attribute_markers:
            if not marker.family or not marker.normalized_value:
                continue
            lexicon[marker.family].setdefault(marker.normalized_value, marker)
    return {family: dict(sorted(markers.items(), key=lambda item: item[0])) for family, markers in lexicon.items()}


def _build_sku_family_matches(
    *,
    family_lexicon: dict[str, dict[str, QueryProfileMarker]],
    searchable_fields: list[_SkuEvidenceField],
) -> dict[str, set[str]]:
    found_by_family: dict[str, set[str]] = {}
    for family, markers in family_lexicon.items():
        found_values: set[str] = set()
        for normalized_value, marker in markers.items():
            matched_fields, _checked_fields = _match_marker_against_fields(marker, searchable_fields)
            if matched_fields:
                found_values.add(normalized_value)
        found_by_family[family] = found_values
    return found_by_family


def _build_product_type_match(
    profile: ExtractedClusterProfile,
    *,
    searchable_fields: list[_SkuEvidenceField],
) -> ProductTypeMatchResult:
    if not profile.product_type_markers:
        return ProductTypeMatchResult(
            status="unknown",
            evidence=[],
            reason="profile_has_no_product_type_markers",
            marker_evaluations=[],
        )

    evaluations = [
        _evaluate_marker(marker, searchable_fields=searchable_fields)
        for marker in profile.product_type_markers
    ]
    matched_evaluations = [item for item in evaluations if item.status == "matched"]
    if matched_evaluations:
        evidence: list[str] = []
        for item in matched_evaluations:
            evidence.extend(item.evidence)
        return ProductTypeMatchResult(
            status="matched",
            evidence=evidence,
            reason="found_product_type_marker_in_sku_evidence",
            marker_evaluations=evaluations,
        )
    if not searchable_fields:
        return ProductTypeMatchResult(
            status="unknown",
            evidence=[],
            reason="sku_evidence_unavailable_for_product_type",
            marker_evaluations=evaluations,
        )
    return ProductTypeMatchResult(
        status="not_matched",
        evidence=[],
        reason="product_type_markers_not_found_in_sku_evidence",
        marker_evaluations=evaluations,
    )


def _build_use_case_match(
    profile: ExtractedClusterProfile,
    *,
    searchable_fields: list[_SkuEvidenceField],
) -> UseCaseMatchResult:
    if not profile.use_case_markers:
        return UseCaseMatchResult(reason="profile_has_no_use_case_markers")

    evaluations = [
        _evaluate_marker(marker, searchable_fields=searchable_fields)
        for marker in profile.use_case_markers
    ]
    matched = [item for item in evaluations if item.status == "matched"]
    unknown = [item for item in evaluations if item.status == "unknown"]
    missed = [item for item in evaluations if item.status == "missed"]
    if unknown and not searchable_fields:
        reason = "sku_evidence_unavailable_for_use_case_markers"
    else:
        reason = f"use_case_markers matched={len(matched)} missed={len(missed)} unknown={len(unknown)}"
    return UseCaseMatchResult(
        matched_markers=matched,
        missed_markers=missed,
        unknown_markers=unknown,
        reason=reason,
    )


def _build_attribute_match(
    profile: ExtractedClusterProfile,
    *,
    searchable_fields: list[_SkuEvidenceField],
    found_attribute_values_by_family: dict[str, set[str]],
) -> AttributeMatchResult:
    if not profile.attribute_markers:
        return AttributeMatchResult(reason="profile_has_no_attribute_markers")

    evaluations: list[ScoringPreparationMarkerEvaluation] = []
    for marker in profile.attribute_markers:
        competing_values = found_attribute_values_by_family.get(marker.family or "", set()) if marker.family else set()
        evaluations.append(
            _evaluate_marker(
                marker,
                searchable_fields=searchable_fields,
                found_competing_values=competing_values,
            )
        )
    matched = [item for item in evaluations if item.status == "matched"]
    conflicting = [item for item in evaluations if item.status == "conflicting"]
    unknown = [item for item in evaluations if item.status == "unknown"]
    missed = [item for item in evaluations if item.status == "missed"]
    if unknown and not searchable_fields:
        reason = "sku_evidence_unavailable_for_attribute_markers"
    else:
        reason = (
            f"attribute_markers matched={len(matched)} conflicting={len(conflicting)} "
            f"missed={len(missed)} unknown={len(unknown)}"
        )
    return AttributeMatchResult(
        matched_markers=matched,
        missed_markers=missed,
        conflicting_markers=conflicting,
        unknown_markers=unknown,
        reason=reason,
    )


def _build_preparation_flags(profile: ExtractedClusterProfile, *, evidence_summary: SkuEvidenceSummary) -> PreparationFlags:
    weak_profile = profile.profile_strength == "weak"
    empty_profile = profile.profile_strength == "empty" or not (
        profile.product_type_markers or profile.use_case_markers or profile.attribute_markers
    )
    missing_product_type = not profile.product_type_markers
    conflicting_profile_markers = bool(profile.conflicting_attribute_families) or "conflicting_product_type_marker" in profile.quality_flags
    insufficient_sku_data = not (
        evidence_summary.title_present or evidence_summary.attributes_present or evidence_summary.description_present
    )
    return PreparationFlags(
        weak_profile=weak_profile,
        empty_profile=empty_profile,
        missing_product_type=missing_product_type,
        conflicting_profile_markers=conflicting_profile_markers,
        insufficient_sku_data=insufficient_sku_data,
    )


def _resolve_readiness(
    *,
    flags: PreparationFlags,
    product_type_match: ProductTypeMatchResult,
) -> ReadinessStatus:
    if flags.empty_profile or flags.insufficient_sku_data:
        return "poor"
    if flags.weak_profile or flags.missing_product_type or flags.conflicting_profile_markers:
        return "partial"
    if product_type_match.status == "unknown":
        return "partial"
    return "ready"


def _build_preparation(
    profile: ExtractedClusterProfile,
    *,
    evidence_bundle: _SkuEvidenceBundle,
    found_attribute_values_by_family: dict[str, set[str]],
) -> ClusterScoringPreparation:
    searchable_fields = evidence_bundle.searchable_fields
    product_type_match = _build_product_type_match(profile, searchable_fields=searchable_fields)
    use_case_match = _build_use_case_match(profile, searchable_fields=searchable_fields)
    attribute_match = _build_attribute_match(
        profile,
        searchable_fields=searchable_fields,
        found_attribute_values_by_family=found_attribute_values_by_family,
    )
    flags = _build_preparation_flags(profile, evidence_summary=evidence_bundle.summary)
    readiness = _resolve_readiness(flags=flags, product_type_match=product_type_match)
    return ClusterScoringPreparation(
        cluster_key=profile.cluster_key,
        profile_label_candidate=profile.profile_label_candidate,
        profile_strength=profile.profile_strength,
        profile_confidence=profile.profile_confidence,
        product_type_match=product_type_match,
        use_case_match=use_case_match,
        attribute_match=attribute_match,
        sku_evidence_summary=evidence_bundle.summary,
        preparation_flags=flags,
        readiness_for_scoring=readiness,
    )


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    preparations: list[ClusterScoringPreparation],
    samples_limit: int,
) -> QueryScoringPreparationDiagnostics:
    readiness_counts = Counter(item.readiness_for_scoring for item in preparations)
    product_type_matched = sum(1 for item in preparations if item.product_type_match.status == "matched")
    use_case_matched = sum(len(item.use_case_match.matched_markers) for item in preparations)
    use_case_total = sum(
        len(item.use_case_match.matched_markers) + len(item.use_case_match.missed_markers) + len(item.use_case_match.unknown_markers)
        for item in preparations
    )
    attribute_matched = sum(len(item.attribute_match.matched_markers) for item in preparations)
    attribute_total = sum(
        len(item.attribute_match.matched_markers)
        + len(item.attribute_match.missed_markers)
        + len(item.attribute_match.conflicting_markers)
        + len(item.attribute_match.unknown_markers)
        for item in preparations
    )
    sorted_preparations = sorted(
        preparations,
        key=lambda item: (
            {"ready": 0, "partial": 1, "poor": 2}.get(item.readiness_for_scoring, 9),
            -float(item.profile_confidence),
            item.cluster_key,
        ),
    )
    return QueryScoringPreparationDiagnostics(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        total_cluster_comparisons=len(preparations),
        ready_count=int(readiness_counts.get("ready", 0)),
        partial_count=int(readiness_counts.get("partial", 0)),
        poor_count=int(readiness_counts.get("poor", 0)),
        product_type_matched_rate=_round_ratio(product_type_matched, len(preparations)),
        use_case_matched_rate=_round_ratio(use_case_matched, use_case_total),
        attribute_matched_rate=_round_ratio(attribute_matched, attribute_total),
        insufficient_sku_data_count=sum(1 for item in preparations if item.preparation_flags.insufficient_sku_data),
        weak_profile_count=sum(1 for item in preparations if item.preparation_flags.weak_profile),
        missing_product_type_count=sum(1 for item in preparations if item.preparation_flags.missing_product_type),
        sample_preparations=sorted_preparations[:samples_limit],
    )


def run_query_scoring_preparation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    top_limit: int = 20,
    samples_limit: int = 20,
    refresh_hybrid: bool = True,
) -> QueryScoringPreparationResult:
    """Prepare explainable deterministic match inputs for one SKU against all cluster profiles."""

    profile_result = run_query_profile_extraction(
        session,
        project_id=project_id,
        category_id=category_id,
        top_limit=max(1, int(top_limit)),
        samples_limit=max(1, int(samples_limit)),
        refresh_hybrid=refresh_hybrid,
        persist=False,
    )
    sku_row = _fetch_sku_row(session, project_id=project_id, nm_id=nm_id)
    evidence_bundle = _build_sku_evidence(sku_row)
    if evidence_bundle.subject_id is not None and int(evidence_bundle.subject_id) != int(category_id):
        raise QueryScoringPreparationScopeError(
            f"SKU nm_id={nm_id} has subject_id={evidence_bundle.subject_id}, expected category_id={category_id}"
        )

    attribute_lexicon = _build_attribute_lexicon(profile_result.profiles)
    found_attribute_values_by_family = _build_sku_family_matches(
        family_lexicon=attribute_lexicon,
        searchable_fields=evidence_bundle.searchable_fields,
    )
    preparations = [
        _build_preparation(
            profile,
            evidence_bundle=evidence_bundle,
            found_attribute_values_by_family=found_attribute_values_by_family,
        )
        for profile in profile_result.profiles
    ]
    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        preparations=preparations,
        samples_limit=max(1, int(samples_limit)),
    )
    return QueryScoringPreparationResult(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        sku_evidence_summary=evidence_bundle.summary,
        preparations=preparations,
        diagnostics=diagnostics,
    )
