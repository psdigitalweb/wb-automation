"""Product-facing SEO workflow services."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import Integer, and_, delete, desc, func, select, text
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMeaningAxes,
    SeoCategoryMatchingReadiness,
    SeoCategorySelectedQuery,
    SeoMeaningAtom,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryNormalized,
    SeoSkuMeaningAnnotation,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)
from app.schemas.seo_products import (
    SeoCategorySelectedQueryItem,
    SeoCategorySelectedQueryListResponse,
    SeoCategorySelectedQuerySaveRequest,
    SeoProductAiVisionVerdict,
    SeoProductAnalysisRunResponse,
    SeoProductAnalysisStatusResponse,
    SeoProductListItem,
    SeoProductListResponse,
    SeoProductQuerySetSummary,
    SeoProductReadinessItem,
    SeoProductReadinessResponse,
    SeoProductSummaryResponse,
    SeoQuerySelectionItem,
    SeoQuerySelectionUpdateRequest,
    SeoQuerySetResponse,
    SeoReadableBlock,
)
from app.schemas.seo_query_meaning_matcher import MEANING_AWARE_MATCHER_VERSION, MeaningAwareMatcherItem
from app.schemas.seo_sku_meaning import SkuMeaningAnnotationRequest, SkuMeaningPayload
from app.services.seo.atoms.v1.vision import VISION_PROMPT_VERSION, render_vision_prompt
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


def _first_photo_url_from_pics(pics: Any) -> str | None:
    if pics is None:
        return None
    if isinstance(pics, str):
        stripped = pics.strip()
        if stripped.startswith("http"):
            return stripped
        try:
            pics = json.loads(stripped)
        except json.JSONDecodeError:
            return None
    if not isinstance(pics, list):
        return None
    for item in pics:
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, Mapping):
            candidate = str(
                item.get("big")
                or item.get("url")
                or item.get("c516x688")
                or item.get("hq")
                or item.get("c128")
                or item.get("square")
                or ""
            ).strip()
        else:
            candidate = ""
        if candidate.startswith("http"):
            return candidate
    return None


def _clean_selected_image_urls(selected_image_urls: list[str] | None) -> list[str]:
    urls: list[str] = []
    for raw_url in selected_image_urls or []:
        url = str(raw_url or "").strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)
        if len(urls) >= 4:
            break
    return urls


def _evidence_with_selected_images(evidence: Any, selected_image_urls: list[str] | None) -> Any:
    urls = _clean_selected_image_urls(selected_image_urls)
    if not urls:
        return evidence
    product = evidence.product.model_copy(update={"pics": urls})
    image_hash = stable_hash({"evidence_hash": evidence.evidence_hash, "selected_image_urls": urls})
    return evidence.model_copy(update={"product": product, "evidence_hash": image_hash})


def _fetch_product_scope(session: Session, *, project_id: int, nm_id: int) -> Mapping[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT project_id, nm_id, subject_id, subject_name, title
            FROM products
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"project_id": int(project_id), "nm_id": int(nm_id)},
    ).mappings().first()
    return row


def list_seo_products(
    session: Session,
    *,
    project_id: int,
    category_id: int | None = None,
    q: str | None = None,
    analysis_status: str | None = None,
    stock_status: str | None = None,
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
    if stock_status == "in_stock":
        where.append("COALESCE(stock.total_quantity, 0) > 0")
    elif stock_status == "out_of_stock":
        where.append("COALESCE(stock.total_quantity, 0) = 0")
    where_sql = " AND ".join(where)
    stock_cte = """
        WITH stock_latest AS (
            SELECT latest.nm_id, COALESCE(SUM(ss.quantity), 0) AS total_quantity
            FROM (
                SELECT ss.nm_id, MAX(ss.snapshot_at) AS snapshot_at
                FROM stock_snapshots ss
                WHERE ss.project_id = :project_id
                GROUP BY ss.nm_id
            ) latest
            JOIN stock_snapshots ss
              ON ss.project_id = :project_id
             AND ss.nm_id = latest.nm_id
             AND ss.snapshot_at = latest.snapshot_at
            GROUP BY latest.nm_id
        ),
        review_counts AS (
            SELECT fs.nm_id, COUNT(*) AS review_count
            FROM wb_feedback_snapshots fs
            WHERE fs.project_id = :project_id
              AND COALESCE(fs.is_archived, FALSE) = FALSE
            GROUP BY fs.nm_id
        )
    """
    total = int(
        session.execute(
            text(
                f"""
                {stock_cte}
                SELECT COUNT(*)
                FROM products p
                LEFT JOIN stock_latest stock ON stock.nm_id = p.nm_id
                WHERE {where_sql}
                """
            ),
            params,
        ).scalar_one()
        or 0
    )
    rows = session.execute(
        text(
            f"""
            {stock_cte}
            SELECT
                p.nm_id,
                p.vendor_code,
                p.title,
                p.brand,
                p.subject_id,
                p.subject_name,
                p.rating,
                p.feedbacks,
                p.pics,
                COALESCE(reviews.review_count, 0) AS review_count,
                stock.total_quantity AS stock_quantity
            FROM products p
            LEFT JOIN stock_latest stock ON stock.nm_id = p.nm_id
            LEFT JOIN review_counts reviews ON reviews.nm_id = p.nm_id
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
                article=row.get("vendor_code"),
                title=row.get("title"),
                name=row.get("title"),
                photo_url=_first_photo_url_from_pics(row.get("pics")),
                brand=row.get("brand"),
                category_id=product_category_id,
                category_name=row.get("subject_name"),
                subject_id=product_category_id,
                subject_name=row.get("subject_name"),
                rating=_num_or_none(row.get("rating")),
                feedbacks=int(row["feedbacks"]) if row.get("feedbacks") is not None else None,
                review_count=int(row["review_count"]) if row.get("review_count") is not None else 0,
                stock_quantity=int(row["stock_quantity"]) if row.get("stock_quantity") is not None else 0,
                in_stock=bool(row.get("stock_quantity") and int(row["stock_quantity"]) > 0),
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


def _vision_evidence_block_from_payload(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None

    def atom_value(atom: Any) -> str | None:
        if not isinstance(atom, Mapping):
            return None
        value = str(atom.get("value") or "").strip()
        return value or None

    facts = payload.get("facts") if isinstance(payload.get("facts"), list) else []
    positive_atoms = payload.get("positive_atoms") if isinstance(payload.get("positive_atoms"), list) else []
    negative_atoms = payload.get("negative_fit_atoms") if isinstance(payload.get("negative_fit_atoms"), list) else []
    product_types: list[str] = []
    colors: list[str] = []
    designs: list[str] = []
    ocr_text: list[str] = []
    other_visual: list[str] = []
    styles: list[str] = []
    audiences: list[str] = []
    weak_audiences: list[str] = []

    def add_unique(target: list[str], value: str | None) -> None:
        if value and value not in target:
            target.append(value)

    for atom in facts:
        if not isinstance(atom, Mapping):
            continue
        value = atom_value(atom)
        field = str(atom.get("field") or "")
        if field == "product_type":
            add_unique(product_types, value)
        elif field == "color":
            add_unique(colors, value)
        elif field == "design":
            add_unique(designs, value)
        elif field == "ocr_text":
            add_unique(ocr_text, value)
        else:
            add_unique(other_visual, value)
    for atom in positive_atoms:
        if not isinstance(atom, Mapping):
            continue
        atom_type = str(atom.get("type") or "")
        value = atom_value(atom)
        if atom_type == "expressive":
            add_unique(styles, value)
        elif atom_type == "recipient":
            add_unique(audiences, value)
    for atom in negative_atoms:
        if isinstance(atom, Mapping) and str(atom.get("type") or "") == "recipient":
            add_unique(weak_audiences, atom_value(atom))

    lines = ["Фото товара подтверждает:", "", "Визуально видно:"]
    if product_types:
        lines.append(f"- товар на фото: {', '.join(product_types)};")
    if colors:
        lines.append(f"- цвет: {', '.join(colors)};")
    if designs:
        lines.append(f"- дизайн: {', '.join(designs)};")
    if other_visual:
        lines.append(f"- дополнительные визуальные признаки: {', '.join(other_visual)};")
    if styles:
        lines.append(f"- стиль: {', '.join(styles)};")
    if len(lines) == 3:
        lines.append("- нет сохраненных визуальных признаков;")
    if ocr_text:
        lines.extend(["", "Прочитано на изображении:"])
        lines.extend(f'- "{item}"' for item in ocr_text)
    if audiences or weak_audiences:
        lines.extend(["", "Аудитория по визуальному впечатлению:"])
        if audiences:
            lines.append(f"- подходящий сигнал: {', '.join(audiences)};")
        if weak_audiences:
            lines.append(f"- слабый сигнал: {', '.join(weak_audiences)};")
    lines.extend(
        [
            "",
            "Используй блок фото как дополнительное evidence к карточке товара.",
            "Не считай OCR-текст физическим свойством товара, если он не подтверждается карточкой.",
        ]
    )
    return "\n".join(lines)


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
    selected_image_urls: list[str] | None = None,
) -> SeoProductAnalysisRunResponse:
    evidence = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    selected_urls = _clean_selected_image_urls(selected_image_urls)
    if selected_urls:
        evidence = _evidence_with_selected_images(evidence, selected_urls)
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
            source_metadata={
                "source": "product_seo_analysis",
                "selected_image_urls": selected_urls,
            },
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


def _count_category_queries(session: Session, *, project_id: int, category_id: int) -> tuple[int, int, int, bool, bool]:
    query_count = int(
        session.scalar(
            select(func.coalesce(func.sum(SeoQueryBatch.row_count), 0)).where(
                SeoQueryBatch.project_id == int(project_id),
                SeoQueryBatch.category_id == int(category_id),
                SeoQueryBatch.status != "deleted",
            )
        )
        or 0
    )
    normalized_query_count = int(
        session.scalar(
            select(func.count(func.distinct(SeoQueryNormalized.normalized_query))).where(
                SeoQueryNormalized.project_id == int(project_id),
                SeoQueryNormalized.category_id == int(category_id),
            )
        )
        or 0
    )
    cluster_count = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryCluster).where(
                SeoQueryCluster.project_id == int(project_id),
                SeoQueryCluster.category_id == int(category_id),
            )
        )
        or 0
    )
    expressive_prior_ready = (
        session.scalar(
            select(SeoCategoryMeaningAxes.id)
            .where(
                SeoCategoryMeaningAxes.project_id == int(project_id),
                SeoCategoryMeaningAxes.category_id == int(category_id),
                SeoCategoryMeaningAxes.status == "ready",
            )
            .order_by(desc(SeoCategoryMeaningAxes.updated_at), desc(SeoCategoryMeaningAxes.id))
            .limit(1)
        )
        is not None
    )
    latest_completed_batch_exists = (
        session.scalar(
            select(SeoQueryBatch.id)
            .where(
                SeoQueryBatch.project_id == int(project_id),
                SeoQueryBatch.category_id == int(category_id),
                SeoQueryBatch.status == "completed",
            )
            .order_by(desc(SeoQueryBatch.created_at), desc(SeoQueryBatch.id))
            .limit(1)
        )
        is not None
    )
    return query_count, normalized_query_count, cluster_count, expressive_prior_ready, latest_completed_batch_exists


def _latest_vision_row(
    session: Session,
    *,
    project_id: int,
    category_id: int | None,
    nm_id: int,
    annotation: SeoSkuMeaningAnnotation | None,
) -> SeoMeaningAtom | None:
    stmt = select(SeoMeaningAtom).where(
        SeoMeaningAtom.project_id == int(project_id),
        SeoMeaningAtom.entity_type == "sku_vision",
        SeoMeaningAtom.nm_id == int(nm_id),
    )
    if category_id is not None:
        stmt = stmt.where(SeoMeaningAtom.category_id == int(category_id))
    if annotation is not None:
        stmt = stmt.where(SeoMeaningAtom.entity_id == int(annotation.id))
    return session.scalars(stmt.order_by(desc(SeoMeaningAtom.updated_at), desc(SeoMeaningAtom.id))).first()


def _vision_verdict_from_row(row: SeoMeaningAtom | None) -> SeoProductAiVisionVerdict:
    if row is None:
        return SeoProductAiVisionVerdict(ready=False, status=None, label="AI vision не выполнен")
    ready = str(row.status) == "ready"
    if not ready:
        label = "AI vision не готов" if str(row.status) != "error" else "AI vision завершился ошибкой"
        return SeoProductAiVisionVerdict(ready=False, status=str(row.status), label=label)
    payload = row.atoms_payload if isinstance(row.atoms_payload, Mapping) else {}
    groups = _strings_from_atoms(payload)
    items = groups["visual"] + groups["expressive"] + groups["audience"]
    raw_image_urls = payload.get("selected_image_urls") if isinstance(payload.get("selected_image_urls"), list) else []
    image_urls = [str(url) for url in raw_image_urls if isinstance(url, str) and url.startswith("http")]
    return SeoProductAiVisionVerdict(
        ready=True,
        status=str(row.status),
        label="AI vision готов",
        items=items[:12],
        image_urls=image_urls,
        prompt_version=str(payload.get("prompt_version") or row.prompt_version or "") or None,
        input_prompt=str(payload.get("input_prompt") or "") or None,
        evidence_block=_vision_evidence_block_from_payload(payload),
    )


def _latest_query_set_summary(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoProductQuerySetSummary | None:
    query_set = session.scalars(
        select(SeoSkuQuerySet)
        .where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
        )
        .order_by(
            desc(SeoSkuQuerySet.approval_state == "approved"),
            desc(SeoSkuQuerySet.status == "confirmed"),
            desc(SeoSkuQuerySet.updated_at),
            desc(SeoSkuQuerySet.id),
        )
    ).first()
    if query_set is None:
        return None
    item_rows = session.execute(
        select(
            func.count(SeoSkuQuerySetItem.id),
            func.sum(
                SeoSkuQuerySetItem.selection_state.in_(("auto_selected", "pinned")).cast(Integer)
            ),
        ).where(SeoSkuQuerySetItem.query_set_id == int(query_set.id))
    ).one()
    items_total = int(item_rows[0] or 0)
    selected_items = int(item_rows[1] or 0)
    approval_state = getattr(query_set, "approval_state", None)
    return SeoProductQuerySetSummary(
        query_set_id=int(query_set.id),
        status=str(query_set.status or "draft"),
        approval_state=str(approval_state) if approval_state is not None else None,
        trust_state=str(getattr(query_set, "trust_state", "")) or None,
        items_total=items_total,
        selected_items=selected_items,
        approved=selected_items > 0,
        updated_at=query_set.updated_at,
    )


def get_product_readiness(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
) -> SeoProductReadinessResponse:
    """Return SKU query-selection prerequisites from saved product/category evidence."""
    product_scope = _fetch_product_scope(session, project_id=project_id, nm_id=nm_id)
    product_card_exists = product_scope is not None
    resolved_category_id = category_id
    if resolved_category_id is None and product_scope is not None and product_scope.get("subject_id") is not None:
        resolved_category_id = int(product_scope["subject_id"])
    category_id_known = resolved_category_id is not None

    query_count = 0
    normalized_query_count = 0
    cluster_count = 0
    expressive_prior_ready = False
    query_data_ready = False
    if resolved_category_id is not None:
        (
            query_count,
            normalized_query_count,
            cluster_count,
            expressive_prior_ready,
            latest_completed_batch_exists,
        ) = _count_category_queries(
            session,
            project_id=project_id,
            category_id=int(resolved_category_id),
        )
        query_data_ready = latest_completed_batch_exists and query_count > 0 and normalized_query_count > 0 and cluster_count > 0

    annotation = _latest_annotation(session, project_id=project_id, nm_id=nm_id, category_id=resolved_category_id)
    vision_row = _latest_vision_row(
        session,
        project_id=project_id,
        category_id=resolved_category_id,
        nm_id=nm_id,
        annotation=annotation,
    )
    ai_vision = _vision_verdict_from_row(vision_row)
    if product_card_exists and resolved_category_id is not None and not ai_vision.input_prompt:
        try:
            vision_evidence = build_sku_evidence_pack(session, project_id=project_id, nm_id=nm_id, category_id=int(resolved_category_id))
            if ai_vision.image_urls:
                vision_evidence = _evidence_with_selected_images(vision_evidence, ai_vision.image_urls)
            ai_vision = ai_vision.model_copy(
                update={
                    "prompt_version": VISION_PROMPT_VERSION,
                    "input_prompt": render_vision_prompt(vision_evidence.model_dump(mode="json")),
                }
            )
        except Exception:
            pass
    existing_query_set = (
        _latest_query_set_summary(
            session,
            project_id=project_id,
            category_id=int(resolved_category_id),
            nm_id=nm_id,
        )
        if resolved_category_id is not None
        else None
    )
    category_readiness = _category_readiness(session, project_id=project_id, category_id=resolved_category_id)
    category_ready = category_readiness is not None and str(category_readiness.status) in {"ready_for_matching", "ready_with_fallback"}
    readiness = [
        SeoProductReadinessItem(
            key="product_card",
            label="Карточка товара",
            ready=product_card_exists,
            details="найдена" if product_card_exists else "товар не найден в проекте",
        ),
        SeoProductReadinessItem(
            key="category",
            label="Категория товара",
            ready=category_id_known,
            details=f"category_id={resolved_category_id}" if resolved_category_id is not None else "category_id не определён",
        ),
        SeoProductReadinessItem(
            key="category_ready",
            label="Категория готова",
            ready=category_ready,
            details=_label_category_status(category_readiness.status if category_readiness is not None else None),
        ),
        SeoProductReadinessItem(
            key="query_data",
            label="Query data категории",
            ready=query_data_ready,
            details=f"{normalized_query_count} нормализованных запросов" if query_data_ready else "нет готового корпуса запросов",
        ),
        SeoProductReadinessItem(
            key="clusters",
            label="Кластеры построены",
            ready=cluster_count > 0,
            details=f"{cluster_count} кластеров" if cluster_count > 0 else "кластеры отсутствуют",
        ),
        SeoProductReadinessItem(
            key="expressive_prior",
            label="Expressive prior",
            ready=expressive_prior_ready,
            details="готов" if expressive_prior_ready else "не найден готовый expressive prior",
        ),
        SeoProductReadinessItem(
            key="ai_vision",
            label="AI vision",
            ready=ai_vision.ready,
            details=ai_vision.label,
        ),
        SeoProductReadinessItem(
            key="query_set",
            label="Подобранные запросы",
            ready=existing_query_set is not None and existing_query_set.selected_items > 0,
            details=(
                f"{existing_query_set.selected_items} выбрано"
                if existing_query_set is not None
                else "подобранные запросы отсутствуют"
            ),
        ),
    ]
    required = {
        "category_id_known": category_id_known,
        "query_data_ready": query_data_ready,
        "expressive_prior_ready": expressive_prior_ready,
        "ai_vision_ready": ai_vision.ready,
    }
    blocking_reasons = []
    if not required["category_id_known"]:
        blocking_reasons.append("Не определена категория товара.")
    if not required["query_data_ready"]:
        blocking_reasons.append("Для категории не готов корпус запросов и кластеры.")
    if not required["expressive_prior_ready"]:
        blocking_reasons.append("Для категории не готов expressive prior.")
    if not required["ai_vision_ready"]:
        blocking_reasons.append("AI vision по товару не выполнен или не готов.")
    return SeoProductReadinessResponse(
        project_id=int(project_id),
        nm_id=int(nm_id),
        category_id=resolved_category_id,
        product_card_exists=product_card_exists,
        category_id_known=category_id_known,
        query_count=query_count,
        normalized_query_count=normalized_query_count,
        cluster_count=cluster_count,
        expressive_prior_ready=expressive_prior_ready,
        ai_vision=ai_vision,
        existing_query_set=existing_query_set,
        readiness=readiness,
        can_select_queries=not blocking_reasons,
        blocking_reasons=blocking_reasons,
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


def _clean_selected_query(value: str) -> str:
    return normalize_query_text(value)


def list_category_selected_queries(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> SeoCategorySelectedQueryListResponse:
    category_rows = session.scalars(
        select(SeoCategorySelectedQuery)
        .where(
            SeoCategorySelectedQuery.project_id == int(project_id),
            SeoCategorySelectedQuery.category_id == int(category_id),
        )
        .order_by(SeoCategorySelectedQuery.sort_order.asc(), SeoCategorySelectedQuery.id.asc())
    ).all()
    saved_rows = session.execute(
        select(
            SeoSkuQuerySetItem.display_query,
            SeoSkuQuerySetItem.normalized_query_text,
            func.count(func.distinct(SeoSkuQuerySet.nm_id)).label("sku_count"),
            func.max(SeoSkuQuerySetItem.ranking_value_used).label("ranking_value_used"),
        )
        .join(SeoSkuQuerySet, SeoSkuQuerySet.id == SeoSkuQuerySetItem.query_set_id)
        .where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.status == "confirmed",
            SeoSkuQuerySetItem.selection_state != "excluded",
        )
        .group_by(SeoSkuQuerySetItem.normalized_query_text, SeoSkuQuerySetItem.display_query)
        .order_by(desc(func.count(func.distinct(SeoSkuQuerySet.nm_id))), SeoSkuQuerySetItem.display_query.asc())
    ).all()

    items: list[SeoCategorySelectedQueryItem] = []
    seen: set[str] = set()
    saved_meta: dict[str, tuple[int, float | None]] = {}
    for row in saved_rows:
        query = _clean_selected_query(str(row.display_query or row.normalized_query_text or ""))
        if not query:
            continue
        ranking_value = float(row.ranking_value_used) if row.ranking_value_used is not None else None
        current = saved_meta.get(query)
        if current is None or int(row.sku_count or 0) > current[0]:
            saved_meta[query] = (int(row.sku_count or 0), ranking_value)

    for row in category_rows:
        query = _clean_selected_query(str(row.query_text))
        if not query or query in seen:
            continue
        sku_count, ranking_value = saved_meta.get(query, (0, None))
        seen.add(query)
        items.append(
            SeoCategorySelectedQueryItem(
                id=int(row.id),
                query_text=query,
                sort_order=int(row.sort_order or 0),
                source="category_list",
                sku_count=sku_count,
                ranking_value_used=ranking_value,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )

    next_sort_order = len(items)
    for index, row in enumerate(saved_rows):
        query = _clean_selected_query(str(row.display_query or row.normalized_query_text or ""))
        if not query or query in seen:
            continue
        seen.add(query)
        items.append(
            SeoCategorySelectedQueryItem(
                id=-(index + 1),
                query_text=query,
                sort_order=next_sort_order,
                source="saved_sku",
                sku_count=int(row.sku_count or 0),
                ranking_value_used=float(row.ranking_value_used) if row.ranking_value_used is not None else None,
                created_at=None,
                updated_at=None,
            )
        )
        next_sort_order += 1

    return SeoCategorySelectedQueryListResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        total=len(items),
        items=items,
    )


def save_category_selected_queries(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    request: SeoCategorySelectedQuerySaveRequest,
) -> SeoCategorySelectedQueryListResponse:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in request.queries:
        query = _clean_selected_query(value)
        if not query or query in seen:
            continue
        seen.add(query)
        cleaned.append(query)

    session.execute(
        delete(SeoCategorySelectedQuery).where(
            SeoCategorySelectedQuery.project_id == int(project_id),
            SeoCategorySelectedQuery.category_id == int(category_id),
        )
    )
    session.flush()
    for index, query in enumerate(cleaned):
        session.add(
            SeoCategorySelectedQuery(
                project_id=int(project_id),
                category_id=int(category_id),
                query_text=query,
                sort_order=index,
            )
        )
    session.flush()
    return list_category_selected_queries(session, project_id=int(project_id), category_id=int(category_id))


def apply_category_selected_queries_to_product(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    query_texts: list[str] | None = None,
) -> SeoQuerySetResponse:
    selected = list_category_selected_queries(session, project_id=int(project_id), category_id=int(category_id))
    if not selected.items:
        raise ValueError("Список запросов категории пуст.")
    selected_items = selected.items
    if query_texts is not None:
        requested_keys = {_clean_selected_query(value) for value in query_texts}
        requested_keys.discard("")
        if not requested_keys:
            raise ValueError("Выберите хотя бы один запрос из списка категории.")
        category_keys = {item.query_text for item in selected.items}
        missing = sorted(requested_keys - category_keys)
        if missing:
            raise ValueError(f"В списке категории нет запросов: {', '.join(missing[:5])}.")
        selected_items = [item for item in selected.items if item.query_text in requested_keys]
    if not selected_items:
        raise ValueError("Выберите хотя бы один запрос из списка категории.")

    scope_filters = (
        SeoSkuQuerySet.project_id == int(project_id),
        SeoSkuQuerySet.category_id == int(category_id),
        SeoSkuQuerySet.nm_id == int(nm_id),
    )
    query_set = session.scalars(
        select(SeoSkuQuerySet)
        .where(*scope_filters, SeoSkuQuerySet.status.in_(("draft", "confirmed")))
        .order_by(desc(SeoSkuQuerySet.status == "confirmed"), desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))
    ).first()
    if query_set is None:
        query_set = SeoSkuQuerySet(project_id=int(project_id), category_id=int(category_id), nm_id=int(nm_id), status="confirmed")
        session.add(query_set)
        session.flush()
    else:
        query_set.status = "confirmed"

    stale_query_sets = session.scalars(
        select(SeoSkuQuerySet).where(
            *scope_filters,
            SeoSkuQuerySet.status.in_(("draft", "confirmed")),
            SeoSkuQuerySet.id != int(query_set.id),
        )
    ).all()
    for stale in stale_query_sets:
        session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(stale.id)))
        session.delete(stale)

    query_set.matcher_version = "category_selected_queries"
    query_set.atoms_version = "category_selected_queries_v1"
    query_set.source_hash = stable_hash(
        {
            "kind": "category_selected_queries",
            "project_id": int(project_id),
            "category_id": int(category_id),
            "queries": [item.query_text for item in selected_items],
        }
    )
    session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id == int(query_set.id)))
    for item in selected_items:
        session.add(
            SeoSkuQuerySetItem(
                query_set_id=int(query_set.id),
                normalized_query_text=item.query_text,
                display_query=item.query_text,
                cluster_key=None,
                bucket="primary",
                score=Decimal("1"),
                ranking_value_used=None,
                selection_state="auto_selected",
                reasons_payload={
                    "source": "category_selected_queries",
                    "user_reasons": ["Выбрано из списка запросов категории."],
                    "matched_atoms": [],
                    "missing_atoms": [],
                    "conflict_atoms": [],
                },
            )
        )
    session.flush()
    return _query_set_to_response(session, query_set)


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
        .order_by(desc(SeoSkuQuerySet.status == "confirmed"), desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))
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
