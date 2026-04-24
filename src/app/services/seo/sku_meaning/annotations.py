"""Persistence, query judgment, and eval export helpers for SKU meanings."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoQueryAnnotation,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoSkuMeaningAnnotation,
    SeoSkuMeaningAuditEvent,
    SeoSkuQueryJudgment,
)
from app.schemas.seo_sku_meaning import (
    EVAL_DATASET_SCHEMA_VERSION,
    SKU_MEANING_SCHEMA_VERSION,
    SkuMeaningAnnotationRequest,
    SkuMeaningAnnotationResponse,
    SkuMeaningCandidateQuery,
    SkuMeaningEvalExportRequest,
    SkuMeaningEvalExportResponse,
    SkuMeaningPayload,
    SkuQueryJudgmentInput,
    SkuQueryJudgmentResponse,
)
from app.services.seo.quality import (
    REASON_REVIEWS_ZERO,
    REASON_VISION_ABSENT,
    QualityMode,
    QualityState,
    infer_quality_mode,
    make_reason,
)
from app.services.seo.query_pipeline import normalize_query_text


class SkuMeaningAnnotationError(Exception):
    """Base annotation persistence error."""


def _infer_annotation_quality_mode(
    request: SkuMeaningAnnotationRequest,
) -> tuple[QualityMode, list[dict[str, Any]]]:
    """Infer quality_mode for a saved SKU meaning annotation.

    Iteration 1 signals we read out of ``source_metadata`` (conventions used
    by callers — any missing key is treated as "evidence absent"):

    - ``vision_present`` (bool) — was the vision pipeline available?
    - ``reviews_count`` (int) — number of reviews in evidence pack; 0 =>
      DEGRADED.
    - ``llm_draft_fallback`` (bool) — true if the LLM draft fell back to a
      deterministic path.
    - ``quality_mode`` — explicit override the caller already computed.
    """

    meta = dict(request.source_metadata or {})

    if meta.get("llm_draft_fallback"):
        state = QualityState(
            fallback_taken=True,
            extra_reasons=[make_reason("sku_draft_fallback", {"source": "llm_draft_fallback"})],
        )
        return infer_quality_mode(state)

    # Respect an explicit override passed by the caller.
    override = meta.get("quality_mode")
    if isinstance(override, str):
        try:
            return QualityMode(override.lower()), [dict(r) for r in meta.get("degraded_reasons") or []]
        except ValueError:
            pass

    evidence_signals: dict[str, bool] = {}
    if "vision_present" in meta:
        evidence_signals["vision_present"] = bool(meta.get("vision_present"))
    if "reviews_count" in meta:
        try:
            evidence_signals["reviews_present"] = int(meta.get("reviews_count") or 0) > 0
        except (TypeError, ValueError):
            evidence_signals["reviews_present"] = False

    state = QualityState(
        embedding_provider_max_mode=QualityMode.FULL,
        evidence_signals=evidence_signals,
    )
    return infer_quality_mode(state)


class SkuMeaningAnnotationNotFoundError(SkuMeaningAnnotationError):
    """Raised when an endpoint requires a saved annotation."""


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text_value = str(value).strip()
    return text_value or None


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _annotation_to_response(row: SeoSkuMeaningAnnotation) -> SkuMeaningAnnotationResponse:
    return SkuMeaningAnnotationResponse(
        id=int(row.id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        nm_id=int(row.nm_id),
        schema_version=str(row.schema_version or SKU_MEANING_SCHEMA_VERSION),
        status=str(row.status or "draft"),  # type: ignore[arg-type]
        meaning=SkuMeaningPayload.model_validate(row.meaning_payload or {}),
        reviewer=row.reviewer,
        evidence_hash=str(row.evidence_hash or ""),
        source_metadata=dict(row.source_metadata or {}),
        draft_model=row.draft_model,
        draft_prompt_version=row.draft_prompt_version,
        draft_artifact_path=row.draft_artifact_path,
        created_at=_iso_or_none(row.created_at),
        updated_at=_iso_or_none(row.updated_at),
    )


def _judgment_to_response(row: SeoSkuQueryJudgment) -> SkuQueryJudgmentResponse:
    return SkuQueryJudgmentResponse(
        id=int(row.id),
        annotation_id=int(row.annotation_id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        nm_id=int(row.nm_id),
        query_text=str(row.query_text or ""),
        normalized_query_text=str(row.normalized_query_text or ""),
        query_id=int(row.query_id) if row.query_id is not None else None,
        cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
        cluster_key=row.cluster_key,
        label=str(row.label),  # type: ignore[arg-type]
        rationale=row.rationale,
        reviewer=row.reviewer,
        matcher_version=row.matcher_version,
        source=str(row.source or "manual"),
        created_at=_iso_or_none(row.created_at),
        updated_at=_iso_or_none(row.updated_at),
    )


def _add_audit_event(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    event_type: str,
    annotation_id: int | None = None,
    actor: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        SeoSkuMeaningAuditEvent(
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
            annotation_id=annotation_id,
            event_type=str(event_type),
            actor=actor,
            event_payload=payload or {},
        )
    )


def get_annotation(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
    schema_version: str = SKU_MEANING_SCHEMA_VERSION,
) -> SkuMeaningAnnotationResponse | None:
    stmt = select(SeoSkuMeaningAnnotation).where(
        SeoSkuMeaningAnnotation.project_id == int(project_id),
        SeoSkuMeaningAnnotation.nm_id == int(nm_id),
        SeoSkuMeaningAnnotation.schema_version == schema_version,
    )
    if category_id is not None:
        stmt = stmt.where(SeoSkuMeaningAnnotation.category_id == int(category_id))
    row = session.scalars(stmt.order_by(SeoSkuMeaningAnnotation.updated_at.desc())).first()
    return _annotation_to_response(row) if row is not None else None


def _get_annotation_row(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    annotation_id: int | None = None,
    category_id: int | None = None,
) -> SeoSkuMeaningAnnotation:
    stmt = select(SeoSkuMeaningAnnotation).where(
        SeoSkuMeaningAnnotation.project_id == int(project_id),
        SeoSkuMeaningAnnotation.nm_id == int(nm_id),
    )
    if annotation_id is not None:
        stmt = stmt.where(SeoSkuMeaningAnnotation.id == int(annotation_id))
    if category_id is not None:
        stmt = stmt.where(SeoSkuMeaningAnnotation.category_id == int(category_id))
    row = session.scalars(stmt.order_by(SeoSkuMeaningAnnotation.updated_at.desc())).first()
    if row is None:
        raise SkuMeaningAnnotationNotFoundError("Save SKU meaning annotation before adding query judgments")
    return row


def save_annotation(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int,
    request: SkuMeaningAnnotationRequest,
) -> SkuMeaningAnnotationResponse:
    schema_version = request.meaning.schema_version or SKU_MEANING_SCHEMA_VERSION
    row = session.scalars(
        select(SeoSkuMeaningAnnotation).where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.nm_id == int(nm_id),
            SeoSkuMeaningAnnotation.schema_version == schema_version,
        )
    ).first()
    event_type = "annotation_created" if row is None else "annotation_updated"

    if row is None:
        row = SeoSkuMeaningAnnotation(
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
            schema_version=schema_version,
        )
        session.add(row)

    row.category_id = int(category_id)
    row.status = request.status
    row.meaning_payload = request.meaning.model_dump(mode="json")
    row.reviewer = request.reviewer
    row.evidence_hash = request.evidence_hash
    row.source_metadata = request.source_metadata or {}
    row.draft_model = request.draft_model
    row.draft_prompt_version = request.draft_prompt_version
    row.draft_artifact_path = request.draft_artifact_path
    # Iteration 1: persist quality_mode inferred from request metadata.
    quality_mode, degraded_reasons = _infer_annotation_quality_mode(request)
    row.quality_mode = quality_mode.value
    row.degraded_reasons = [dict(r) for r in degraded_reasons] or None
    session.flush()

    _add_audit_event(
        session,
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        annotation_id=int(row.id),
        event_type=event_type,
        actor=request.reviewer,
        payload={"status": request.status, "evidence_hash": request.evidence_hash},
    )
    return _annotation_to_response(row)


def list_candidate_queries(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 100,
    search: str | None = None,
) -> list[SkuMeaningCandidateQuery]:
    annotation = get_annotation(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
    existing_by_query: dict[str, SeoSkuQueryJudgment] = {}
    if annotation is not None:
        judgment_rows = session.scalars(
            select(SeoSkuQueryJudgment).where(SeoSkuQueryJudgment.annotation_id == annotation.id)
        ).all()
        existing_by_query = {str(row.normalized_query_text): row for row in judgment_rows}

    stmt = (
        select(
            SeoQueryAnnotation.id,
            SeoQueryAnnotation.normalized_query_text,
            SeoQueryAnnotation.query_type,
            SeoQueryAnnotation.intent_type,
            SeoQueryAnnotation.pruning_status,
            SeoQueryAnnotation.is_kept_for_pipeline,
            SeoQueryClusterMembership.ranking_value_used,
            SeoQueryCluster.id.label("cluster_id"),
            SeoQueryCluster.cluster_key,
            SeoQueryCluster.label,
            SeoQueryCluster.top_query_text,
        )
        .select_from(SeoQueryAnnotation)
        .outerjoin(
            SeoQueryClusterMembership,
            and_(
                SeoQueryClusterMembership.project_id == SeoQueryAnnotation.project_id,
                SeoQueryClusterMembership.category_id == SeoQueryAnnotation.category_id,
                SeoQueryClusterMembership.normalized_query_text == SeoQueryAnnotation.normalized_query_text,
            ),
        )
        .outerjoin(SeoQueryCluster, SeoQueryCluster.id == SeoQueryClusterMembership.cluster_id)
        .where(
            SeoQueryAnnotation.project_id == int(project_id),
            SeoQueryAnnotation.category_id == int(category_id),
            SeoQueryAnnotation.pruning_status != "drop",
        )
    )
    normalized_search = (search or "").strip()
    if normalized_search:
        stmt = stmt.where(SeoQueryAnnotation.normalized_query_text.ilike(f"%{normalized_search}%"))
    rows = session.execute(
        stmt.order_by(
            SeoQueryAnnotation.is_kept_for_pipeline.desc(),
            desc(SeoQueryClusterMembership.ranking_value_used),
            SeoQueryAnnotation.normalized_query_text.asc(),
        ).limit(max(1, min(int(limit), 300)))
    ).all()

    items: list[SkuMeaningCandidateQuery] = []
    for row in rows:
        normalized = str(row.normalized_query_text or "")
        existing = existing_by_query.get(normalized)
        ranking = row.ranking_value_used
        items.append(
            SkuMeaningCandidateQuery(
                query_text=normalized,
                normalized_query_text=normalized,
                ranking_value_used=str(ranking) if ranking is not None else None,
                bucket=row.query_type,
                intent_type=row.intent_type,
                pruning_status=row.pruning_status,
                query_id=int(row.id) if row.id is not None else None,
                cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
                cluster_key=row.cluster_key,
                cluster_label_candidate=row.label or row.top_query_text or row.cluster_key,
                existing_label=str(existing.label) if existing is not None else None,  # type: ignore[arg-type]
                existing_rationale=existing.rationale if existing is not None else None,
            )
        )
    return items


def save_query_judgments(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None,
    annotation_id: int | None,
    items: list[SkuQueryJudgmentInput],
) -> list[SkuQueryJudgmentResponse]:
    annotation = _get_annotation_row(
        session,
        project_id=project_id,
        nm_id=nm_id,
        annotation_id=annotation_id,
        category_id=category_id,
    )
    responses: list[SkuQueryJudgmentResponse] = []
    for item in items:
        normalized = item.normalized_query_text or normalize_query_text(item.query_text)
        row = session.scalars(
            select(SeoSkuQueryJudgment).where(
                SeoSkuQueryJudgment.annotation_id == int(annotation.id),
                SeoSkuQueryJudgment.normalized_query_text == normalized,
            )
        ).first()
        event_type = "query_judgment_created" if row is None else "query_judgment_updated"
        if row is None:
            row = SeoSkuQueryJudgment(
                project_id=int(project_id),
                category_id=int(annotation.category_id),
                annotation_id=int(annotation.id),
                nm_id=int(nm_id),
                normalized_query_text=normalized,
            )
            session.add(row)
        row.query_text = item.query_text
        row.query_id = item.query_id
        row.cluster_id = item.cluster_id
        row.cluster_key = item.cluster_key
        row.label = item.label
        row.rationale = item.rationale
        row.reviewer = item.reviewer
        row.matcher_version = item.matcher_version
        row.source = item.source or "manual"
        session.flush()
        _add_audit_event(
            session,
            project_id=int(project_id),
            category_id=int(annotation.category_id),
            nm_id=int(nm_id),
            annotation_id=int(annotation.id),
            event_type=event_type,
            actor=item.reviewer,
            payload={"query": normalized, "label": item.label},
        )
        responses.append(_judgment_to_response(row))
    return responses


def _export_item(annotation: SeoSkuMeaningAnnotation, judgments: list[SeoSkuQueryJudgment]) -> dict[str, Any]:
    return {
        "schema_version": EVAL_DATASET_SCHEMA_VERSION,
        "project_id": int(annotation.project_id),
        "nm_id": int(annotation.nm_id),
        "category_id": int(annotation.category_id),
        "sku_meaning": _json_ready(annotation.meaning_payload or {}),
        "evidence_summary": {
            "evidence_hash": annotation.evidence_hash,
            "source_metadata": _json_ready(annotation.source_metadata or {}),
            "annotation_status": annotation.status,
            "schema_version": annotation.schema_version,
        },
        "query_judgments": [
            {
                "query_text": row.query_text,
                "normalized_query_text": row.normalized_query_text,
                "query_id": row.query_id,
                "cluster_id": row.cluster_id,
                "cluster_key": row.cluster_key,
                "label": row.label,
                "rationale": row.rationale,
                "matcher_version": row.matcher_version,
                "source": row.source,
            }
            for row in judgments
        ],
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _items_to_jsonl(items: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items) + ("\n" if items else "")


def _items_to_csv(items: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "schema_version",
            "project_id",
            "category_id",
            "nm_id",
            "sku_meaning_json",
            "evidence_summary_json",
            "query_judgments_json",
            "created_at",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "schema_version": item["schema_version"],
                "project_id": item["project_id"],
                "category_id": item["category_id"],
                "nm_id": item["nm_id"],
                "sku_meaning_json": json.dumps(item["sku_meaning"], ensure_ascii=False, sort_keys=True),
                "evidence_summary_json": json.dumps(item["evidence_summary"], ensure_ascii=False, sort_keys=True),
                "query_judgments_json": json.dumps(item["query_judgments"], ensure_ascii=False, sort_keys=True),
                "created_at": item["created_at"],
            }
        )
    return output.getvalue()


def export_eval_dataset(
    session: Session,
    *,
    project_id: int,
    request: SkuMeaningEvalExportRequest,
    actor: str | None = None,
) -> SkuMeaningEvalExportResponse:
    stmt = select(SeoSkuMeaningAnnotation).where(SeoSkuMeaningAnnotation.project_id == int(project_id))
    if request.category_id is not None:
        stmt = stmt.where(SeoSkuMeaningAnnotation.category_id == int(request.category_id))
    if request.nm_ids:
        stmt = stmt.where(SeoSkuMeaningAnnotation.nm_id.in_([int(item) for item in request.nm_ids]))
    if not request.include_drafts:
        stmt = stmt.where(SeoSkuMeaningAnnotation.status == "verified")
    annotations = session.scalars(stmt.order_by(SeoSkuMeaningAnnotation.category_id.asc(), SeoSkuMeaningAnnotation.nm_id.asc())).all()

    items: list[dict[str, Any]] = []
    for annotation in annotations:
        judgments = session.scalars(
            select(SeoSkuQueryJudgment)
            .where(SeoSkuQueryJudgment.annotation_id == int(annotation.id))
            .order_by(SeoSkuQueryJudgment.normalized_query_text.asc())
        ).all()
        items.append(_export_item(annotation, list(judgments)))
        _add_audit_event(
            session,
            project_id=int(project_id),
            category_id=int(annotation.category_id),
            nm_id=int(annotation.nm_id),
            annotation_id=int(annotation.id),
            event_type="eval_export_created",
            actor=actor,
            payload={"format": request.format, "include_drafts": request.include_drafts},
        )

    content = _items_to_csv(items) if request.format == "csv" else _items_to_jsonl(items)
    return SkuMeaningEvalExportResponse(
        project_id=int(project_id),
        category_id=request.category_id,
        exported_count=len(items),
        format=request.format,
        content=content,
        items=items,
    )
