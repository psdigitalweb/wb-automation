"""Product-facing SEO workflow services."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import and_, delete, desc, func, select, text
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMatchingReadiness,
    SeoMeaningAtom,
    SeoSkuMeaningAnnotation,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)
from app.schemas.seo_products import (
    SeoProductAnalysisRunResponse,
    SeoProductAnalysisStatusResponse,
    SeoProductListItem,
    SeoProductListResponse,
    SeoProductSummaryResponse,
    SeoQuerySelectionItem,
    SeoQuerySelectionUpdateRequest,
    SeoQuerySetResponse,
    SeoReadableBlock,
)
from app.schemas.seo_query_meaning_matcher import MEANING_AWARE_MATCHER_VERSION, MeaningAwareMatcherItem
from app.schemas.seo_sku_meaning import SkuMeaningAnnotationRequest, SkuMeaningPayload
from app.services.seo.meaning_atoms import ATOMS_SOURCE_VERSION, ensure_sku_atoms, get_atoms_payload
from app.services.seo.query_meaning_matcher.canonical import listify, stable_hash
from app.services.seo.query_meaning_matcher.matcher import run_meaning_aware_matcher
from app.services.seo.query_pipeline import normalize_query_text
from app.services.seo.sku_meaning.annotations import get_annotation, save_annotation
from app.services.seo.sku_meaning.draft import generate_sku_meaning_draft
from app.services.seo.sku_meaning.evidence import build_sku_evidence_pack


def _label_category_status(status: str | None) -> str:
    if status == "ready_for_matching":
        return "Готова к подбору"
    if status == "ready_with_fallback":
        return "Можно использовать, но качество ниже"
    if status == "building":
        return "Обрабатывается"
    return "Нужно действие"


def _label_product_status(has_meaning: bool, has_atoms: bool) -> str:
    if has_meaning and has_atoms:
        return "Готов к подбору"
    return "Нужно проанализировать"


def _label_vision_status(has_vision: bool, errored: bool = False) -> str:
    if has_vision:
        return "Фото учтены"
    if errored:
        return "Фото не учтены: анализ фото недоступен"
    return "Фото не учтены"


def _num_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def list_seo_products(
    session: Session,
    *,
    project_id: int,
    category_id: int | None = None,
    q: str | None = None,
    analysis_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SeoProductListResponse:
    where = ["p.project_id = :project_id"]
    params: dict[str, Any] = {"project_id": int(project_id), "limit": max(1, min(int(limit), 200)), "offset": max(0, int(offset))}
    if category_id is not None:
        where.append("p.subject_id = :category_id")
        params["category_id"] = int(category_id)
    if q:
        where.append("(CAST(p.nm_id AS TEXT) ILIKE :q OR p.vendor_code ILIKE :q OR p.title ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    where_sql = " AND ".join(where)
    total = int(session.execute(text(f"SELECT COUNT(*) FROM products p WHERE {where_sql}"), params).scalar_one() or 0)
    rows = session.execute(
        text(
            f"""
            SELECT p.nm_id, p.vendor_code, p.title, p.brand, p.subject_id, p.subject_name, p.rating, p.feedbacks
            FROM products p
            WHERE {where_sql}
            ORDER BY p.updated_at DESC NULLS LAST, p.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()

    items: list[SeoProductListItem] = []
    for row in rows:
        nm_id = int(row["nm_id"])
        product_category_id = int(row["subject_id"]) if row.get("subject_id") is not None else None
        annotation = _latest_annotation(session, project_id=project_id, nm_id=nm_id, category_id=product_category_id)
        has_meaning = annotation is not None
        has_sku_atoms = (
            annotation is not None
            and get_atoms_payload(
                session,
                project_id=project_id,
                category_id=int(annotation.category_id),
                entity_type="sku_meaning",
                entity_id=int(annotation.id),
                nm_id=nm_id,
            )
            is not None
        )
        has_vision = (
            annotation is not None
            and get_atoms_payload(
                session,
                project_id=project_id,
                category_id=int(annotation.category_id),
                entity_type="sku_vision",
                entity_id=int(annotation.id),
                nm_id=nm_id,
            )
            is not None
        )
        readiness = _category_readiness(session, project_id=project_id, category_id=product_category_id)
        item_status = _label_product_status(has_meaning, has_sku_atoms)
        if analysis_status and analysis_status not in {"all", item_status, "ready" if has_meaning and has_sku_atoms else "needs_action"}:
            continue
        items.append(
            SeoProductListItem(
                nm_id=nm_id,
                vendor_code=row.get("vendor_code"),
                title=row.get("title"),
                brand=row.get("brand"),
                category_id=product_category_id,
                category_name=row.get("subject_name"),
                rating=_num_or_none(row.get("rating")),
                feedbacks=int(row["feedbacks"]) if row.get("feedbacks") is not None else None,
                analysis_status=item_status,
                category_status=_label_category_status(readiness.status if readiness is not None else None),
                has_sku_meaning=has_meaning,
                has_sku_atoms=bool(has_sku_atoms),
                has_vision_atoms=bool(has_vision),
            )
        )
    return SeoProductListResponse(project_id=int(project_id), total=total, items=items)


def _latest_annotation(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
) -> SeoSkuMeaningAnnotation | None:
    stmt = select(SeoSkuMeaningAnnotation).where(
        SeoSkuMeaningAnnotation.project_id == int(project_id),
        SeoSkuMeaningAnnotation.nm_id == int(nm_id),
    )
    if category_id is not None:
        stmt = stmt.where(SeoSkuMeaningAnnotation.category_id == int(category_id))
    return session.scalars(stmt.order_by(desc(SeoSkuMeaningAnnotation.updated_at), desc(SeoSkuMeaningAnnotation.id))).first()


def _category_readiness(session: Session, *, project_id: int, category_id: int | None) -> SeoCategoryMatchingReadiness | None:
    if category_id is None:
        return None
    return session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()


def _strings_from_meaning(meaning: Mapping[str, Any]) -> dict[str, list[str]]:
    functional = meaning.get("functional") if isinstance(meaning.get("functional"), Mapping) else {}
    expressive = meaning.get("expressive") if isinstance(meaning.get("expressive"), Mapping) else {}
    return {
        "functional": listify(functional.get("product_type")) + listify(functional.get("use_cases")) + listify(functional.get("attributes")),
        "expressive": listify(expressive.get("styles")) + listify(expressive.get("vibes")) + listify(expressive.get("emotions")),
        "audience": listify(meaning.get("audience")),
        "negative": listify(meaning.get("negative_constraints")),
        "occasion": listify(expressive.get("gift_contexts")),
    }


def _strings_from_atoms(payload: Mapping[str, Any] | None) -> dict[str, list[str]]:
    def add_unique(target: list[str], value: Any) -> None:
        text_value = str(value or "").strip()
        if text_value and text_value not in target:
            target.append(text_value)

    groups = {"visual": [], "expressive": [], "audience": [], "negative": []}
    if not payload:
        return groups
    facts = payload.get("facts") if isinstance(payload.get("facts"), list) else []
    positive_atoms = payload.get("positive_atoms") if isinstance(payload.get("positive_atoms"), list) else []
    negative_atoms = payload.get("negative_fit_atoms") if isinstance(payload.get("negative_fit_atoms"), list) else []
    for atom in facts:
        if not isinstance(atom, Mapping):
            continue
        atom_type = str(atom.get("type") or "")
        field = str(atom.get("field") or "")
        if atom_type in {"visual", "attribute"} or field in {"design", "motif", "color", "packaging", "ocr_text", "shape"}:
            add_unique(groups["visual"], atom.get("value"))
    for atom in positive_atoms:
        if not isinstance(atom, Mapping):
            continue
        atom_type = str(atom.get("type") or "")
        if atom_type == "expressive":
            add_unique(groups["expressive"], atom.get("value"))
        elif atom_type == "recipient":
            add_unique(groups["audience"], atom.get("value"))
    for atom in negative_atoms:
        if isinstance(atom, Mapping):
            add_unique(groups["negative"], atom.get("value"))
    return groups


def get_product_seo_summary(session: Session, *, project_id: int, nm_id: int, category_id: int | None = None) -> SeoProductSummaryResponse:
    evidence = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    annotation = _latest_annotation(session, project_id=project_id, nm_id=nm_id, category_id=evidence.category_id)
    readiness = _category_readiness(session, project_id=project_id, category_id=evidence.category_id)
    has_sku_atoms = False
    has_vision = False
    vision_error = False
    meaning_payload: dict[str, Any] = {}
    vision_payload: dict[str, Any] | None = None
    if annotation is not None:
        meaning_payload = dict(annotation.meaning_payload or {})
        has_sku_atoms = (
            get_atoms_payload(
                session,
                project_id=project_id,
                category_id=evidence.category_id,
                entity_type="sku_meaning",
                entity_id=int(annotation.id),
                nm_id=nm_id,
            )
            is not None
        )
        vision_row = session.scalars(
            select(SeoMeaningAtom).where(
                SeoMeaningAtom.project_id == int(project_id),
                SeoMeaningAtom.category_id == int(evidence.category_id),
                SeoMeaningAtom.entity_type == "sku_vision",
                SeoMeaningAtom.entity_id == int(annotation.id),
                SeoMeaningAtom.nm_id == int(nm_id),
            )
        ).first()
        has_vision = vision_row is not None and vision_row.status == "ready"
        vision_error = vision_row is not None and vision_row.status == "error"
        if has_vision:
            vision_payload = dict(vision_row.atoms_payload or {})
    groups = _strings_from_meaning(meaning_payload)
    vision_groups = _strings_from_atoms(vision_payload)
    product = evidence.product.model_dump(mode="json")
    blocks = [
        SeoReadableBlock(title="Что мы поняли о товаре", items=groups["functional"], empty_text="Товар еще не проанализирован."),
        SeoReadableBlock(title="Что видно на фото", items=vision_groups["visual"], empty_text="Фото еще не проанализированы или модель не нашла полезных признаков."),
        SeoReadableBlock(title="Стиль и эмоциональный контекст", items=groups["expressive"] + groups["occasion"], empty_text="Стиль пока не определен."),
        SeoReadableBlock(title="Для кого подходит", items=groups["audience"] + vision_groups["audience"], empty_text="Аудитория пока не определена."),
        SeoReadableBlock(title="Какие запросы не подходят", items=groups["negative"] + vision_groups["negative"], empty_text="Явных ограничений пока нет."),
    ]
    return SeoProductSummaryResponse(
        project_id=int(project_id),
        nm_id=int(nm_id),
        category_id=int(evidence.category_id),
        product=product,
        product_status_label=_label_product_status(annotation is not None, has_sku_atoms),
        category_status_label=_label_category_status(readiness.status if readiness is not None else None),
        vision_status_label=_label_vision_status(has_vision, vision_error),
        blocks=blocks,
        diagnostics={
            "annotation_id": int(annotation.id) if annotation is not None else None,
            "evidence_hash": evidence.evidence_hash,
            "warnings": evidence.warnings,
        },
        # Iteration 1: surface the annotation-level quality_mode so the UI
        # can render a QualityBadge next to "product analysis" status.
        quality_mode=getattr(annotation, "quality_mode", None) if annotation is not None else None,
        degraded_reasons=list(getattr(annotation, "degraded_reasons", None) or []) if annotation is not None else [],
    )


def run_product_analysis(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
    force_refresh: bool = False,
    include_vision: bool = True,
) -> SeoProductAnalysisRunResponse:
    evidence = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    warnings = list(evidence.warnings)
    draft_model = None
    draft_prompt_version = None
    draft_artifact_path = None
    try:
        draft = generate_sku_meaning_draft(evidence, force_refresh=force_refresh)
        meaning = draft.meaning
        draft_model = draft.model
        draft_prompt_version = draft.prompt_version
        draft_artifact_path = draft.artifact_path
    except Exception as exc:
        warnings.append(f"sku_meaning_draft_failed:{type(exc).__name__}")
        meaning = SkuMeaningPayload(
            functional={
                "product_type": evidence.product.subject_name or "",
                "attributes": listify(evidence.product.characteristics),
            },
            confidence={"fallback": 0.4},
            evidence_refs=["product.title", "product.characteristics"],
            review_status="needs_more_data",
        )
    annotation_response = save_annotation(
        session,
        project_id=project_id,
        nm_id=nm_id,
        category_id=evidence.category_id,
        request=SkuMeaningAnnotationRequest(
            category_id=evidence.category_id,
            meaning=meaning,
            status=meaning.review_status,
            evidence_hash=evidence.evidence_hash,
            reviewer="seo_product_analysis",
            source_metadata={"source": "product_seo_analysis"},
            draft_model=draft_model,
            draft_prompt_version=draft_prompt_version,
            draft_artifact_path=draft_artifact_path,
        ),
    )
    annotation = session.get(SeoSkuMeaningAnnotation, int(annotation_response.id))
    atoms_result = ensure_sku_atoms(
        session,
        project_id=project_id,
        category_id=evidence.category_id,
        nm_id=nm_id,
        evidence_payload=evidence.model_dump(mode="json"),
        annotation=annotation,
        force_refresh=force_refresh,
        include_vision=include_vision,
    )
    session.flush()
    return SeoProductAnalysisRunResponse(
        project_id=int(project_id),
        nm_id=int(nm_id),
        category_id=int(evidence.category_id),
        status="completed",
        product_status_label="Готов к подбору",
        vision_status_label=_label_vision_status(str(atoms_result.get("vision_status")) == "ready", str(atoms_result.get("vision_status")) == "error"),
        annotation_id=int(annotation_response.id),
        evidence_hash=evidence.evidence_hash,
        warnings=warnings,
    )


def get_product_analysis_status(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
) -> SeoProductAnalysisStatusResponse:
    annotation = _latest_annotation(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    resolved_category_id = int(annotation.category_id) if annotation is not None else category_id
    has_sku_atoms = False
    has_vision = False
    if annotation is not None:
        has_sku_atoms = get_atoms_payload(
            session,
            project_id=project_id,
            category_id=int(annotation.category_id),
            entity_type="sku_meaning",
            entity_id=int(annotation.id),
            nm_id=nm_id,
        ) is not None
        has_vision = get_atoms_payload(
            session,
            project_id=project_id,
            category_id=int(annotation.category_id),
            entity_type="sku_vision",
            entity_id=int(annotation.id),
            nm_id=nm_id,
        ) is not None
    return SeoProductAnalysisStatusResponse(
        project_id=int(project_id),
        nm_id=int(nm_id),
        category_id=resolved_category_id,
        status="ready" if annotation is not None and has_sku_atoms else "needs_action",
        product_status_label=_label_product_status(annotation is not None, has_sku_atoms),
        has_sku_meaning=annotation is not None,
        has_sku_atoms=has_sku_atoms,
        has_vision_atoms=has_vision,
    )


def _query_set_to_response(session: Session, query_set: SeoSkuQuerySet, *, matcher: Any = None) -> SeoQuerySetResponse:
    rows = session.scalars(
        select(SeoSkuQuerySetItem)
        .where(SeoSkuQuerySetItem.query_set_id == int(query_set.id))
        .order_by(SeoSkuQuerySetItem.bucket.asc(), desc(SeoSkuQuerySetItem.score), SeoSkuQuerySetItem.display_query.asc())
    ).all()
    items = [
        SeoQuerySelectionItem(
            id=int(row.id),
            normalized_query_text=str(row.normalized_query_text),
            display_query=str(row.display_query),
            cluster_key=row.cluster_key,
            bucket=str(row.bucket),
            user_bucket_label=_bucket_label(str(row.bucket)),
            score=float(row.score or 0),
            ranking_value_used=float(row.ranking_value_used) if row.ranking_value_used is not None else None,
            selection_state=str(row.selection_state or "auto_selected"),  # type: ignore[arg-type]
            user_reasons=list((row.reasons_payload or {}).get("user_reasons") or []),
            matched_atoms=list((row.reasons_payload or {}).get("matched_atoms") or []),
            missing_atoms=list((row.reasons_payload or {}).get("missing_atoms") or []),
            conflict_atoms=list((row.reasons_payload or {}).get("conflict_atoms") or []),
        )
        for row in rows
    ]
    return SeoQuerySetResponse(
        id=int(query_set.id),
        project_id=int(query_set.project_id),
        category_id=int(query_set.category_id),
        nm_id=int(query_set.nm_id),
        status=str(query_set.status or "draft"),  # type: ignore[arg-type]
        matcher_version=query_set.matcher_version,
        atoms_version=query_set.atoms_version,
        items=items,
        matcher=matcher,
        # Iteration 1 additive quality surface.
        quality_mode=getattr(query_set, "quality_mode", None),
        degraded_reasons=list(getattr(query_set, "degraded_reasons", None) or []),
        matcher_run_id=getattr(query_set, "matcher_run_id", None),
    )


def _bucket_label(bucket: str) -> str:
    return {"primary": "Лучшие", "secondary": "Подходящие", "broad": "Слишком общие", "rejected": "Не подходят"}.get(bucket, bucket)


def _selection_state_for_bucket(bucket: str) -> str:
    return "auto_selected" if bucket in {"primary", "secondary"} else "excluded"


def run_query_selection(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 400,
    include_rejected: bool = True,
) -> SeoQuerySetResponse:
    matcher = run_meaning_aware_matcher(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        limit=limit,
        include_rejected=include_rejected,
    )
    source_hash = stable_hash(matcher.model_dump(mode="json"))
    query_set = session.scalars(
        select(SeoSkuQuerySet).where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
            SeoSkuQuerySet.status == "draft",
        )
    ).first()
    if query_set is None:
        query_set = SeoSkuQuerySet(project_id=int(project_id), category_id=int(category_id), nm_id=int(nm_id), status="draft")
        session.add(query_set)
        session.flush()
    query_set.matcher_version = MEANING_AWARE_MATCHER_VERSION
    query_set.atoms_version = matcher.diagnostics.atoms_version
    query_set.source_hash = source_hash
    session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(query_set.id)))
    for bucket, bucket_items in matcher.buckets.items():
        for item in bucket_items:
            _add_query_set_item(session, query_set, item)
    session.flush()
    return _query_set_to_response(session, query_set, matcher=matcher)


def _add_query_set_item(session: Session, query_set: SeoSkuQuerySet, item: MeaningAwareMatcherItem) -> None:
    normalized = normalize_query_text(item.query)
    session.add(
        SeoSkuQuerySetItem(
            query_set_id=int(query_set.id),
            normalized_query_text=normalized,
            display_query=item.query,
            cluster_key=item.cluster_key,
            bucket=item.bucket,
            score=Decimal(str(item.score)),
            ranking_value_used=Decimal(str(item.ranking_value_used)) if item.ranking_value_used is not None else None,
            selection_state=_selection_state_for_bucket(str(item.bucket)),
            reasons_payload={
                "user_reasons": item.user_reasons,
                "reasons": item.reasons,
                "matched_atoms": item.matched_atoms,
                "missing_atoms": item.missing_atoms,
                "conflict_atoms": item.conflict_atoms,
            },
        )
    )


def _copy_query_set_items(session: Session, *, source: SeoSkuQuerySet, target: SeoSkuQuerySet) -> None:
    source_items = session.scalars(
        select(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(source.id))
    ).all()
    for item in source_items:
        session.add(
            SeoSkuQuerySetItem(
                query_set_id=int(target.id),
                normalized_query_text=str(item.normalized_query_text),
                display_query=str(item.display_query),
                cluster_key=item.cluster_key,
                bucket=str(item.bucket),
                score=item.score,
                ranking_value_used=item.ranking_value_used,
                selection_state=str(item.selection_state or "auto_selected"),
                reasons_payload=dict(item.reasons_payload or {}),
            )
        )


def _copy_query_set_metadata(*, source: SeoSkuQuerySet, target: SeoSkuQuerySet) -> None:
    target.matcher_version = source.matcher_version
    target.atoms_version = source.atoms_version
    target.source_hash = source.source_hash


def get_query_selection(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoQuerySetResponse:
    row = session.scalars(
        select(SeoSkuQuerySet)
        .where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
        )
        .order_by(desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))
    ).first()
    if row is None:
        return SeoQuerySetResponse(project_id=int(project_id), category_id=int(category_id), nm_id=int(nm_id), items=[])
    return _query_set_to_response(session, row)


def update_query_selection(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    request: SeoQuerySelectionUpdateRequest,
) -> SeoQuerySetResponse:
    scope_filters = (
        SeoSkuQuerySet.project_id == int(project_id),
        SeoSkuQuerySet.category_id == int(request.category_id),
        SeoSkuQuerySet.nm_id == int(nm_id),
    )
    row = session.scalars(
        select(SeoSkuQuerySet).where(*scope_filters, SeoSkuQuerySet.status == "draft")
    ).first()
    if row is None:
        source = session.scalars(
            select(SeoSkuQuerySet)
            .where(*scope_filters)
            .order_by(desc(SeoSkuQuerySet.status == "confirmed"), desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))
        ).first()
        row = SeoSkuQuerySet(project_id=int(project_id), category_id=int(request.category_id), nm_id=int(nm_id), status="draft")
        session.add(row)
        session.flush()
        if source is not None:
            _copy_query_set_metadata(source=source, target=row)
            _copy_query_set_items(session, source=source, target=row)
    updates = {normalize_query_text(item.normalized_query_text): item.selection_state for item in request.items}
    if updates:
        items = session.scalars(select(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(row.id))).all()
        for item in items:
            state = updates.get(normalize_query_text(str(item.normalized_query_text)))
            if state:
                item.selection_state = state
    if request.status == "confirmed":
        confirmed = session.scalars(
            select(SeoSkuQuerySet).where(*scope_filters, SeoSkuQuerySet.status == "confirmed")
        ).first()
        if confirmed is not None and int(confirmed.id) != int(row.id):
            _copy_query_set_metadata(source=row, target=confirmed)
            session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(confirmed.id)))
            session.flush()
            _copy_query_set_items(session, source=row, target=confirmed)
            session.delete(row)
            session.flush()
            row = confirmed
        else:
            row.status = "confirmed"
    session.flush()
    return _query_set_to_response(session, row)
