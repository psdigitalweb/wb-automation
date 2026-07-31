"""Deterministic query pruning and basic annotation over the unified dataset."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SeoQueryAnnotation, SeoQueryAnnotationVersion
from app.services.seo.query_pipeline.diagnostics import (
    PrunedQueryPreview,
    QueryPruningDiagnostics,
    _serialize_value,
)
from app.services.seo.query_pipeline.unified_dataset import (
    CanonicalQueryRow,
    UnifiedQueryDatasetResult,
    _decimal_to_string,
    _presence_key,
    assemble_unified_query_dataset,
)


_QUERY_TYPE_KEYS = ("head", "mid", "tail")
_PRUNING_REASON_KEYS = (
    "empty_malformed",
    "navigation_marketplace",
    "garbage_noise",
    "informational_query",
    "single_token_lexical_noise",
    "weak_coverage_no_demand",
    "pipeline_candidate",
)
_INTENT_KEYS = ("product", "category", "informational", "garbage", "unknown")


@dataclass(frozen=True)
class _OverlayState:
    """Resolved current overlay rows plus persisted annotations absent from fresh dataset."""

    overlay_rows: list[AnnotatedCanonicalQueryRow]
    stale_rows: list[AnnotatedCanonicalQueryRow]


@dataclass(frozen=True)
class AnnotatedCanonicalQueryRow(CanonicalQueryRow):
    """Canonical query row enriched with persisted pruning + annotation state."""

    normalized_query_id: int | None = None
    pruning_status: str = "review"
    pruning_reason_code: str = "migrated_pending"
    is_kept_for_pipeline: bool = False
    query_type: str = "tail"
    intent_type: str = "unknown"
    annotation_reason_code: str = "migrated_pending"
    annotation_id: int | None = None
    annotation_version_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryPruningResult:
    """Annotated query rows plus diagnostics and source dataset metadata."""

    project_id: int
    category_id: int
    annotated_queries: list[AnnotatedCanonicalQueryRow]
    diagnostics: QueryPruningDiagnostics
    unified_dataset: UnifiedQueryDatasetResult
    annotations_upserted: int = 0
    versions_created: int = 0


def _normalized_query_id_for_row(row: CanonicalQueryRow) -> int | None:
    for source_ref in row.source_record_refs:
        if source_ref.source_type == "csv_normalized" and source_ref.record_ids:
            return int(source_ref.record_ids[0])
    return None


def _token_count(normalized_query_text: str) -> int:
    return len([token for token in normalized_query_text.split(" ") if token])


def _single_token(normalized_query_text: str) -> str | None:
    tokens = [token for token in normalized_query_text.split(" ") if token]
    return tokens[0] if len(tokens) == 1 else None


def _common_prefix_length(left: str, right: str) -> int:
    prefix = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        prefix += 1
    return prefix


def _levenshtein_distance_with_limit(left: str, right: str, *, limit: int) -> int | None:
    if abs(len(left) - len(right)) > limit:
        return None
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + cost,
                )
            )
            row_min = min(row_min, current[-1])
        if row_min > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def detect_single_token_lexical_noise(rows: Iterable[CanonicalQueryRow | AnnotatedCanonicalQueryRow]) -> dict[str, str]:
    single_rows: list[tuple[str, Decimal]] = []
    for row in rows:
        token = _single_token(str(row.normalized_query_text).strip().lower())
        if token is None or not token.isalpha():
            continue
        single_rows.append((token, Decimal(str(row.ranking_value_used))))
    if not single_rows:
        return {}

    ordered_single_rows = sorted(single_rows, key=lambda item: (-item[1], item[0]))
    dominant_anchors = [(token, ranking) for token, ranking in ordered_single_rows if len(token) >= 6][:5]
    if not dominant_anchors:
        return {}

    anchor_tokens = {token for token, _ in dominant_anchors}
    suspicious: dict[str, str] = {}
    for token, ranking in ordered_single_rows:
        if token in anchor_tokens:
            continue

        for anchor_token, anchor_ranking in dominant_anchors:
            if anchor_token == token:
                continue
            if _common_prefix_length(token, anchor_token) >= 5:
                distance = _levenshtein_distance_with_limit(token, anchor_token, limit=2)
                if distance is not None and ranking <= max(Decimal("100"), anchor_ranking * Decimal("0.02")):
                    suspicious[token] = "single_token_typo_like"
                    break
            if (
                token not in suspicious
                and len(token) >= len(anchor_token) + 4
                and anchor_token in token
                and ranking <= Decimal("500")
            ):
                suspicious[token] = "single_token_glued_family_noise"
                break
    return suspicious


def _apply_pruning_rules_legacy(row: CanonicalQueryRow) -> tuple[str, str, bool]:
    if row.is_empty_candidate:
        return "drop", "empty_malformed", False
    if row.is_navigation_candidate:
        return "drop", "navigation_marketplace", False
    if row.is_garbage_candidate:
        return "drop", "garbage_noise", False
    if row.is_informational_candidate:
        return "review", "informational_query", False
    if row.ranking_value_used <= 0 and row.source_count == 1:
        return "review", "weak_coverage_no_demand", False
    return "keep", "pipeline_candidate", True


def _apply_pruning_rules(
    row: CanonicalQueryRow,
    *,
    single_token_noise_reasons: dict[str, str] | None = None,
) -> tuple[str, str, bool]:
    legacy_status, legacy_reason_code, legacy_keep = _apply_pruning_rules_legacy(row)
    if legacy_reason_code != "pipeline_candidate":
        return legacy_status, legacy_reason_code, legacy_keep
    single_token_noise_reasons = single_token_noise_reasons or {}
    token = _single_token(row.normalized_query_text)
    if token is not None and token in single_token_noise_reasons:
        return "review", "single_token_lexical_noise", False
    return legacy_status, legacy_reason_code, legacy_keep


def _apply_annotation_rules(row: CanonicalQueryRow, *, pruning_reason_code: str) -> tuple[str, str]:
    token_count = _token_count(row.normalized_query_text)
    if pruning_reason_code == "empty_malformed":
        return "garbage", "garbage_empty_malformed"
    if pruning_reason_code == "navigation_marketplace":
        return "garbage", "garbage_navigation_marketplace"
    if pruning_reason_code == "garbage_noise":
        return "garbage", "garbage_noise_marker"
    if row.is_informational_candidate:
        return "informational", "informational_marker"
    if pruning_reason_code == "single_token_lexical_noise":
        return "unknown", "unknown_single_token_lexical_noise"
    if token_count >= 2 and row.ranking_value_used > 0:
        return "product", "product_multi_token_with_signal"
    if token_count == 1:
        return "category", "category_single_token"
    return "unknown", "unknown_fallback"


def _annotate_canonical_row(
    row: CanonicalQueryRow,
    *,
    single_token_noise_reasons: dict[str, str] | None = None,
    rule_version: str = "tightened",
) -> AnnotatedCanonicalQueryRow:
    if rule_version == "legacy":
        pruning_status, pruning_reason_code, is_kept_for_pipeline = _apply_pruning_rules_legacy(row)
    else:
        pruning_status, pruning_reason_code, is_kept_for_pipeline = _apply_pruning_rules(
            row,
            single_token_noise_reasons=single_token_noise_reasons,
        )
    intent_type, annotation_reason_code = _apply_annotation_rules(row, pruning_reason_code=pruning_reason_code)
    return AnnotatedCanonicalQueryRow(
        **{
            **row.__dict__,
            "normalized_query_id": _normalized_query_id_for_row(row),
            "pruning_status": pruning_status,
            "pruning_reason_code": pruning_reason_code,
            "is_kept_for_pipeline": is_kept_for_pipeline,
            "query_type": row.head_tail_bucket,
            "intent_type": intent_type,
            "annotation_reason_code": annotation_reason_code,
        }
    )


def annotate_canonical_rows(
    rows: Iterable[CanonicalQueryRow],
    *,
    rule_version: str = "tightened",
) -> list[AnnotatedCanonicalQueryRow]:
    materialized_rows = list(rows)
    single_token_noise_reasons = (
        detect_single_token_lexical_noise(materialized_rows)
        if rule_version == "tightened"
        else {}
    )
    return [
        _annotate_canonical_row(
            row,
            single_token_noise_reasons=single_token_noise_reasons,
            rule_version=rule_version,
        )
        for row in materialized_rows
    ]


def _annotation_payload(row: AnnotatedCanonicalQueryRow) -> dict[str, Any]:
    return _serialize_value(
        {
            "project_id": row.project_id,
            "category_id": row.category_id,
            "normalized_query_id": row.normalized_query_id,
            "normalized_query_text": row.normalized_query_text,
            "display_query": row.display_query,
            "pruning_status": row.pruning_status,
            "pruning_reason_code": row.pruning_reason_code,
            "is_kept_for_pipeline": row.is_kept_for_pipeline,
            "query_type": row.query_type,
            "intent_type": row.intent_type,
            "annotation_reason_code": row.annotation_reason_code,
            "head_tail_bucket": row.head_tail_bucket,
            "bucket_basis": row.bucket_basis,
            "ranking_value_used": row.ranking_value_used,
            "frequency_total": row.frequency_total,
            "orders_total": row.orders_total,
            "avg_position_best": row.avg_position_best,
            "source_presence": row.source_presence,
            "source_count": row.source_count,
            "source_record_refs": row.source_record_refs,
            "preparation_flags": {
                "is_empty_candidate": row.is_empty_candidate,
                "is_duplicate_candidate": row.is_duplicate_candidate,
                "is_garbage_candidate": row.is_garbage_candidate,
                "is_informational_candidate": row.is_informational_candidate,
                "is_navigation_candidate": row.is_navigation_candidate,
            },
            "preparation_flag_reasons": row.preparation_flag_reasons,
            "display_variants": row.display_variants,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "canonical_entity_basis": row.canonical_entity_basis,
        }
    )


def _sorted_source_ref_summary(row: AnnotatedCanonicalQueryRow) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for source_ref in sorted(row.source_record_refs, key=lambda item: item.source_type):
        raw_summary = source_ref.raw_value_summary or {}
        summaries.append(
            {
                "source_type": source_ref.source_type,
                "record_ids": sorted(int(item) for item in source_ref.record_ids),
                "record_count": int(source_ref.record_count),
                "batch_ids": sorted(int(item) for item in source_ref.batch_ids),
                "nm_ids": sorted(int(item) for item in source_ref.nm_ids),
                "date_range": dict(source_ref.date_range or {}) or None,
                "raw_value_summary": {str(key): raw_summary[key] for key in sorted(raw_summary)},
            }
        )
    return summaries


def _semantic_snapshot(row: AnnotatedCanonicalQueryRow) -> dict[str, Any]:
    return _serialize_value(
        {
            "normalized_query_id": row.normalized_query_id,
            "normalized_query_text": row.normalized_query_text,
            "pruning_status": row.pruning_status,
            "pruning_reason_code": row.pruning_reason_code,
            "is_kept_for_pipeline": row.is_kept_for_pipeline,
            "query_type": row.query_type,
            "intent_type": row.intent_type,
            "annotation_reason_code": row.annotation_reason_code,
            "head_tail_bucket": row.head_tail_bucket,
            "bucket_basis": row.bucket_basis,
            "ranking_value_used": row.ranking_value_used,
            "source_presence": {key: row.source_presence[key] for key in sorted(row.source_presence)},
            "source_count": row.source_count,
            "source_refs_summary": _sorted_source_ref_summary(row),
            "preparation_flags": {
                "is_empty_candidate": row.is_empty_candidate,
                "is_duplicate_candidate": row.is_duplicate_candidate,
                "is_garbage_candidate": row.is_garbage_candidate,
                "is_informational_candidate": row.is_informational_candidate,
                "is_navigation_candidate": row.is_navigation_candidate,
            },
            "preparation_flag_reasons": list(row.preparation_flag_reasons),
        }
    )


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _annotation_meta(row: AnnotatedCanonicalQueryRow, *, payload_hash: str) -> dict[str, Any]:
    return {
        "snapshot_hash": payload_hash,
        "canonical_entity_basis": row.canonical_entity_basis,
        "head_tail_bucket": row.head_tail_bucket,
        "bucket_basis": row.bucket_basis,
        "source_presence": dict(row.source_presence),
    }


def _semantic_snapshot_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "semantic_snapshot" in payload and isinstance(payload["semantic_snapshot"], dict):
        return dict(payload["semantic_snapshot"])

    source_presence = payload.get("source_presence") or {}
    preparation_flags = payload.get("preparation_flags") or {}
    return _serialize_value(
        {
            "normalized_query_id": payload.get("normalized_query_id"),
            "normalized_query_text": payload.get("normalized_query_text", ""),
            "pruning_status": payload.get("pruning_status", "review"),
            "pruning_reason_code": payload.get("pruning_reason_code", "migrated_pending"),
            "is_kept_for_pipeline": bool(payload.get("is_kept_for_pipeline")),
            "query_type": payload.get("query_type", payload.get("head_tail_bucket", "tail")),
            "intent_type": payload.get("intent_type", "unknown"),
            "annotation_reason_code": payload.get("annotation_reason_code", "migrated_pending"),
            "head_tail_bucket": payload.get("head_tail_bucket", payload.get("query_type", "tail")),
            "bucket_basis": payload.get("bucket_basis", "none"),
            "ranking_value_used": payload.get("ranking_value_used", "0"),
            "source_presence": {key: source_presence[key] for key in sorted(source_presence)},
            "source_count": int(payload.get("source_count", 0)),
            "source_refs_summary": sorted(payload.get("source_refs_summary") or payload.get("source_record_refs") or [], key=lambda item: item.get("source_type", "")),
            "preparation_flags": {
                "is_empty_candidate": bool(preparation_flags.get("is_empty_candidate", False)),
                "is_duplicate_candidate": bool(preparation_flags.get("is_duplicate_candidate", False)),
                "is_garbage_candidate": bool(preparation_flags.get("is_garbage_candidate", False)),
                "is_informational_candidate": bool(preparation_flags.get("is_informational_candidate", False)),
                "is_navigation_candidate": bool(preparation_flags.get("is_navigation_candidate", False)),
            },
            "preparation_flag_reasons": list(payload.get("preparation_flag_reasons") or []),
        }
    )


def _semantic_snapshot_hash(row: AnnotatedCanonicalQueryRow) -> tuple[dict[str, Any], str]:
    snapshot = _semantic_snapshot(row)
    return snapshot, _payload_hash(snapshot)


def _annotation_rationale(row: AnnotatedCanonicalQueryRow) -> str:
    return (
        f"pruning={row.pruning_status}:{row.pruning_reason_code}; "
        f"annotation={row.intent_type}:{row.annotation_reason_code}; "
        f"query_type={row.query_type}"
    )


def _load_existing_annotations(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> tuple[dict[str, SeoQueryAnnotation], dict[int, dict[str, Any]]]:
    annotations = session.scalars(
        select(SeoQueryAnnotation).where(
            SeoQueryAnnotation.project_id == project_id,
            SeoQueryAnnotation.category_id == category_id,
        )
    ).all()
    annotations_by_key = {str(item.normalized_query_text): item for item in annotations}

    latest_payload_by_annotation_id: dict[int, dict[str, Any]] = {}
    annotation_ids = [int(item.id) for item in annotations if item.id is not None]
    if annotation_ids:
        versions = session.scalars(
            select(SeoQueryAnnotationVersion).where(SeoQueryAnnotationVersion.annotation_id.in_(annotation_ids))
        ).all()
        latest_versions: dict[int, SeoQueryAnnotationVersion] = {}
        for version in versions:
            current = latest_versions.get(int(version.annotation_id))
            if current is None or int(version.version_number) > int(current.version_number):
                latest_versions[int(version.annotation_id)] = version
        latest_payload_by_annotation_id = {
            annotation_id: dict(version.annotation_payload or {})
            for annotation_id, version in latest_versions.items()
        }

    return annotations_by_key, latest_payload_by_annotation_id


def _sync_current_annotation(
    annotation: SeoQueryAnnotation,
    *,
    row: AnnotatedCanonicalQueryRow,
    meta: dict[str, Any],
) -> bool:
    changed = False
    next_meta = dict(meta)
    existing_meta = dict(annotation.meta or {})
    if "hybrid_annotation" in existing_meta and "hybrid_annotation" not in next_meta:
        next_meta["hybrid_annotation"] = existing_meta["hybrid_annotation"]
    values = {
        "normalized_query_id": row.normalized_query_id,
        "normalized_query_text": row.normalized_query_text,
        "annotation_status": "completed",
        "pruning_status": row.pruning_status,
        "pruning_reason_code": row.pruning_reason_code,
        "is_kept_for_pipeline": row.is_kept_for_pipeline,
        "query_type": row.query_type,
        "intent_type": row.intent_type,
        "annotation_reason_code": row.annotation_reason_code,
        "meta": next_meta,
    }
    for field_name, value in values.items():
        if getattr(annotation, field_name) != value:
            setattr(annotation, field_name, value)
            changed = True
    return changed


def _persist_annotations(
    session: Session,
    *,
    annotated_rows: list[AnnotatedCanonicalQueryRow],
) -> tuple[list[AnnotatedCanonicalQueryRow], int, int]:
    if not annotated_rows:
        return [], 0, 0

    project_id = annotated_rows[0].project_id
    category_id = annotated_rows[0].category_id
    annotations_by_key, latest_payload_by_annotation_id = _load_existing_annotations(
        session,
        project_id=project_id,
        category_id=category_id,
    )

    persisted_rows: list[AnnotatedCanonicalQueryRow] = []
    annotations_upserted = 0
    versions_created = 0

    for row in annotated_rows:
        payload = _annotation_payload(row)
        semantic_snapshot, payload_hash = _semantic_snapshot_hash(row)
        payload["semantic_snapshot"] = semantic_snapshot
        meta = _annotation_meta(row, payload_hash=payload_hash)
        annotation = annotations_by_key.get(row.normalized_query_text)

        if annotation is None:
            annotation = SeoQueryAnnotation(
                project_id=row.project_id,
                category_id=row.category_id,
                normalized_query_id=row.normalized_query_id,
                normalized_query_text=row.normalized_query_text,
                annotation_status="completed",
                pruning_status=row.pruning_status,
                pruning_reason_code=row.pruning_reason_code,
                is_kept_for_pipeline=row.is_kept_for_pipeline,
                query_type=row.query_type,
                intent_type=row.intent_type,
                annotation_reason_code=row.annotation_reason_code,
                latest_version_number=0,
                meta=meta,
            )
            session.add(annotation)
            session.flush()
            annotations_by_key[row.normalized_query_text] = annotation
            latest_payload_by_annotation_id[int(annotation.id)] = {}
            current_changed = True
        else:
            current_changed = _sync_current_annotation(annotation, row=row, meta=meta)

        latest_payload = latest_payload_by_annotation_id.get(int(annotation.id), {})
        latest_snapshot = _semantic_snapshot_from_payload(latest_payload)
        payload_changed = latest_snapshot != semantic_snapshot
        latest_version_number = int(annotation.latest_version_number or 0)
        persisted_version_number = latest_version_number

        if payload_changed:
            persisted_version_number = latest_version_number + 1
            session.add(
                SeoQueryAnnotationVersion(
                    project_id=row.project_id,
                    category_id=row.category_id,
                    annotation_id=annotation.id,
                    version_number=persisted_version_number,
                    annotation_payload=payload,
                    rationale=_annotation_rationale(row),
                )
            )
            annotation.latest_version_number = persisted_version_number
            latest_payload_by_annotation_id[int(annotation.id)] = payload
            versions_created += 1
            current_changed = True

        if current_changed:
            annotations_upserted += 1

        persisted_rows.append(
            AnnotatedCanonicalQueryRow(
                **{
                    **row.__dict__,
                    "annotation_id": int(annotation.id),
                    "annotation_version_number": persisted_version_number if persisted_version_number > 0 else None,
                }
            )
        )

    session.flush()
    return persisted_rows, annotations_upserted, versions_created


def _preview_from_row(row: AnnotatedCanonicalQueryRow) -> PrunedQueryPreview:
    return PrunedQueryPreview(
        project_id=row.project_id,
        category_id=row.category_id,
        normalized_query_text=row.normalized_query_text,
        display_query=row.display_query,
        normalized_query_id=row.normalized_query_id,
        pruning_status=row.pruning_status,
        pruning_reason_code=row.pruning_reason_code,
        is_kept_for_pipeline=row.is_kept_for_pipeline,
        query_type=row.query_type,
        intent_type=row.intent_type,
        annotation_reason_code=row.annotation_reason_code,
        source_count=row.source_count,
        source_presence_key=_presence_key(row.source_presence),
        ranking_value_used=_decimal_to_string(row.ranking_value_used),
        bucket_basis=row.bucket_basis,
        head_tail_bucket=row.head_tail_bucket,
        preparation_flag_reasons=list(row.preparation_flag_reasons),
    )


def _append_limited(items: list[PrunedQueryPreview], row: AnnotatedCanonicalQueryRow, *, limit: int) -> None:
    if len(items) < limit:
        items.append(_preview_from_row(row))


def _build_stale_row(annotation: SeoQueryAnnotation) -> AnnotatedCanonicalQueryRow:
    source_presence = dict((annotation.meta or {}).get("source_presence") or {})
    return AnnotatedCanonicalQueryRow(
        project_id=int(annotation.project_id),
        category_id=int(annotation.category_id),
        normalized_query_text=str(annotation.normalized_query_text),
        display_query=str(annotation.normalized_query_text),
        source_presence={key: bool(source_presence[key]) for key in sorted(source_presence)},
        source_count=int(sum(1 for present in source_presence.values() if present)),
        source_record_refs=[],
        frequency_total=Decimal("0"),
        orders_total=Decimal("0"),
        ranking_value_used=Decimal("0"),
        bucket_basis=str((annotation.meta or {}).get("bucket_basis") or "none"),
        head_tail_bucket=str((annotation.meta or {}).get("head_tail_bucket") or getattr(annotation, "query_type", "tail")),
        first_seen_at=None,
        last_seen_at=None,
        is_empty_candidate=False,
        is_duplicate_candidate=False,
        is_garbage_candidate=False,
        is_informational_candidate=False,
        is_navigation_candidate=False,
        preparation_flag_reasons=[],
        normalized_query_id=annotation.normalized_query_id,
        pruning_status=str(annotation.pruning_status),
        pruning_reason_code=str(annotation.pruning_reason_code),
        is_kept_for_pipeline=bool(annotation.is_kept_for_pipeline),
        query_type=str(annotation.query_type),
        intent_type=str(annotation.intent_type),
        annotation_reason_code=str(annotation.annotation_reason_code),
        annotation_id=int(annotation.id),
        annotation_version_number=int(annotation.latest_version_number or 0) or None,
    )


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    rows: list[AnnotatedCanonicalQueryRow],
    top_limit: int,
    samples_limit: int,
    annotations_upserted: int,
    versions_created: int,
    stale_rows: list[AnnotatedCanonicalQueryRow],
) -> QueryPruningDiagnostics:
    counts_by_pruning_reason_code = {key: 0 for key in _PRUNING_REASON_KEYS}
    counts_by_intent_type = {key: 0 for key in _INTENT_KEYS}
    kept_counts_by_query_type = {key: 0 for key in _QUERY_TYPE_KEYS}
    status_counter = Counter(row.pruning_status for row in rows)

    top_kept_queries: list[PrunedQueryPreview] = []
    sample_dropped_queries: list[PrunedQueryPreview] = []
    sample_review_queries: list[PrunedQueryPreview] = []
    sample_unknown_queries: list[PrunedQueryPreview] = []

    for row in rows:
        counts_by_pruning_reason_code.setdefault(row.pruning_reason_code, 0)
        counts_by_pruning_reason_code[row.pruning_reason_code] += 1
        counts_by_intent_type.setdefault(row.intent_type, 0)
        counts_by_intent_type[row.intent_type] += 1
        if row.is_kept_for_pipeline:
            kept_counts_by_query_type.setdefault(row.query_type, 0)
            kept_counts_by_query_type[row.query_type] += 1
            _append_limited(top_kept_queries, row, limit=top_limit)
        if row.pruning_status == "drop":
            _append_limited(sample_dropped_queries, row, limit=samples_limit)
        if row.pruning_status == "review":
            _append_limited(sample_review_queries, row, limit=samples_limit)
        if row.intent_type == "unknown":
            _append_limited(sample_unknown_queries, row, limit=samples_limit)

    stale_persisted_annotation_samples: list[PrunedQueryPreview] = []
    for row in stale_rows:
        _append_limited(stale_persisted_annotation_samples, row, limit=samples_limit)

    return QueryPruningDiagnostics(
        project_id=project_id,
        category_id=category_id,
        total_canonical_queries_processed=len(rows),
        keep_count=int(status_counter.get("keep", 0)),
        drop_count=int(status_counter.get("drop", 0)),
        review_count=int(status_counter.get("review", 0)),
        counts_by_pruning_reason_code=counts_by_pruning_reason_code,
        counts_by_intent_type=counts_by_intent_type,
        kept_counts_by_query_type=kept_counts_by_query_type,
        top_kept_queries=top_kept_queries,
        sample_dropped_queries=sample_dropped_queries,
        sample_review_queries=sample_review_queries,
        sample_unknown_queries=sample_unknown_queries,
        stale_persisted_annotation_count=len(stale_rows),
        stale_persisted_annotation_samples=stale_persisted_annotation_samples,
        removed_since_last_run_count=len(stale_rows),
        annotations_upserted=annotations_upserted,
        versions_created=versions_created,
    )


def run_query_pruning_and_basic_annotation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    top_limit: int = 20,
    samples_limit: int = 20,
    persist: bool = True,
) -> QueryPruningResult:
    """Run deterministic pruning and annotation on the current unified query dataset."""

    unified_dataset = assemble_unified_query_dataset(
        session,
        project_id=project_id,
        category_id=category_id,
        top_limit=top_limit,
        samples_limit=samples_limit,
    )
    annotated_rows = annotate_canonical_rows(unified_dataset.canonical_queries, rule_version="tightened")

    annotations_upserted = 0
    versions_created = 0
    persisted_rows = annotated_rows
    stale_rows: list[AnnotatedCanonicalQueryRow] = []
    if persist:
        persisted_rows, annotations_upserted, versions_created = _persist_annotations(
            session,
            annotated_rows=annotated_rows,
        )
        stale_rows = _load_overlay_state(
            session,
            project_id=project_id,
            category_id=category_id,
            unified_dataset=unified_dataset,
        ).stale_rows

    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        rows=persisted_rows,
        top_limit=max(1, int(top_limit)),
        samples_limit=max(1, int(samples_limit)),
        annotations_upserted=annotations_upserted,
        versions_created=versions_created,
        stale_rows=stale_rows,
    )
    return QueryPruningResult(
        project_id=project_id,
        category_id=category_id,
        annotated_queries=persisted_rows,
        diagnostics=diagnostics,
        unified_dataset=unified_dataset,
        annotations_upserted=annotations_upserted,
        versions_created=versions_created,
    )


def _load_overlay_state(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    unified_dataset: UnifiedQueryDatasetResult | None = None,
) -> _OverlayState:
    unified_dataset = unified_dataset or assemble_unified_query_dataset(session, project_id=project_id, category_id=category_id)
    annotation_rows = session.scalars(
        select(SeoQueryAnnotation).where(
            SeoQueryAnnotation.project_id == project_id,
            SeoQueryAnnotation.category_id == category_id,
            SeoQueryAnnotation.annotation_status == "completed",
        )
    ).all()
    annotations_by_key = {str(item.normalized_query_text): item for item in annotation_rows}
    current_keys = {row.normalized_query_text for row in unified_dataset.canonical_queries}

    overlay_rows: list[AnnotatedCanonicalQueryRow] = []
    for canonical_row in unified_dataset.canonical_queries:
        annotation = annotations_by_key.get(canonical_row.normalized_query_text)
        if annotation is None:
            continue
        overlay_rows.append(
            AnnotatedCanonicalQueryRow(
                **{
                    **canonical_row.__dict__,
                    "normalized_query_id": annotation.normalized_query_id or _normalized_query_id_for_row(canonical_row),
                    "pruning_status": annotation.pruning_status,
                    "pruning_reason_code": annotation.pruning_reason_code,
                    "is_kept_for_pipeline": bool(annotation.is_kept_for_pipeline),
                    "query_type": annotation.query_type,
                    "intent_type": annotation.intent_type,
                    "annotation_reason_code": annotation.annotation_reason_code,
                    "annotation_id": int(annotation.id),
                    "annotation_version_number": int(annotation.latest_version_number or 0) or None,
                }
            )
        )

    stale_rows = [
        _build_stale_row(annotation)
        for annotation in sorted(
            (item for item in annotation_rows if str(item.normalized_query_text) not in current_keys),
            key=lambda item: str(item.normalized_query_text),
        )
    ]
    return _OverlayState(overlay_rows=overlay_rows, stale_rows=stale_rows)


def get_clean_query_set(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None = None,
) -> list[AnnotatedCanonicalQueryRow]:
    """Return persisted kept queries from the fresh unified dataset only."""

    rows = get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
    if bucket is not None:
        rows = [row for row in rows if row.query_type == bucket]
    return [row for row in rows if row.is_kept_for_pipeline]


def get_pruning_slice(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    pruning_status: str,
    bucket: str | None = None,
) -> list[AnnotatedCanonicalQueryRow]:
    """Return persisted rows for one pruning status from the fresh unified dataset only."""

    rows = get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
    if bucket is not None:
        rows = [row for row in rows if row.query_type == bucket]
    return [row for row in rows if row.pruning_status == pruning_status]


def get_persisted_pruning_overlay(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> list[AnnotatedCanonicalQueryRow]:
    """Return current persisted pruning rows over the fresh unified dataset."""

    return _load_overlay_state(session, project_id=project_id, category_id=category_id).overlay_rows
