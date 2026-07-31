"""Evidence pack builder for SKU Meaning Preview / Annotation Tool."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.seo_sku_meaning import (
    SkuMeaningEvidencePack,
    SkuMeaningProductEvidence,
    SkuMeaningReviewEvidence,
)
from app.services.seo.expressive_llm.reviews_source import _combine_review_text
from app.services.seo.meaning_extraction import build_category_meaning, build_product_projection
from app.services.seo.meaning_extraction.product_projection import (
    ProductProjectionError,
    ProductProjectionScopeError,
)


class SkuMeaningEvidenceError(Exception):
    """Base evidence-pack error."""


class SkuMeaningProductNotFoundError(SkuMeaningEvidenceError):
    """Raised when the selected SKU is unavailable in the project."""


class SkuMeaningScopeError(SkuMeaningEvidenceError):
    """Raised when the selected SKU does not belong to the requested category."""


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text_value = str(value).strip()
    return text_value or None


def _json_loads_maybe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
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
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash_evidence(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _fetch_product_row(session: Session, *, project_id: int, nm_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT
                project_id,
                nm_id,
                vendor_code,
                title,
                brand,
                subject_id,
                subject_name,
                description,
                price_u,
                sale_price_u,
                rating,
                feedbacks,
                sizes,
                colors,
                pics,
                dimensions,
                characteristics,
                updated_at
            FROM v_wb_product_source
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"project_id": int(project_id), "nm_id": int(nm_id)},
    ).mappings().first()
    if row is None:
        raise SkuMeaningProductNotFoundError(f"SKU nm_id={nm_id} is not available in project_id={project_id}")
    return dict(row)


def _fetch_sku_reviews(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    limit: int,
) -> tuple[list[SkuMeaningReviewEvidence], list[str]]:
    warnings: list[str] = []
    if limit <= 0:
        return [], warnings

    try:
        rows = session.execute(
            text(
                """
                SELECT
                    fs.nm_id,
                    fs.product_valuation AS rating,
                    fs.created_date AS created_date,
                    fs.raw AS raw
                FROM wb_feedback_snapshots fs
                WHERE fs.project_id = :project_id
                  AND fs.nm_id = :nm_id
                ORDER BY fs.created_date DESC NULLS LAST, fs.id DESC
                LIMIT :limit
                """
            ),
            {"project_id": int(project_id), "nm_id": int(nm_id), "limit": int(limit)},
        ).mappings().all()
    except Exception as exc:
        warnings.append(f"reviews_unavailable:{type(exc).__name__}")
        return [], warnings

    reviews: list[SkuMeaningReviewEvidence] = []
    for idx, row in enumerate(rows):
        combined = _combine_review_text(row.get("raw"))
        if not combined:
            continue
        created_raw = row.get("created_date")
        created_at = None
        if isinstance(created_raw, datetime):
            created_at = created_raw.isoformat()
        elif created_raw is not None:
            created_at = str(created_raw)
        reviews.append(
            SkuMeaningReviewEvidence(
                ref=f"review:{idx}",
                nm_id=int(row.get("nm_id") or nm_id),
                rating=int(row["rating"]) if row.get("rating") is not None else None,
                text=combined,
                created_at=created_at,
            )
        )
    return reviews, warnings


def _product_evidence_from_row(row: Mapping[str, Any]) -> SkuMeaningProductEvidence:
    return SkuMeaningProductEvidence(
        project_id=int(row.get("project_id") or 0),
        nm_id=int(row.get("nm_id") or 0),
        vendor_code=row.get("vendor_code"),
        title=row.get("title"),
        brand=row.get("brand"),
        subject_id=int(row["subject_id"]) if row.get("subject_id") is not None else None,
        subject_name=row.get("subject_name"),
        description=row.get("description"),
        price_u=int(row["price_u"]) if row.get("price_u") is not None else None,
        sale_price_u=int(row["sale_price_u"]) if row.get("sale_price_u") is not None else None,
        rating=float(row["rating"]) if row.get("rating") is not None else None,
        feedbacks=int(row["feedbacks"]) if row.get("feedbacks") is not None else None,
        sizes=_json_loads_maybe(row.get("sizes")),
        colors=_json_loads_maybe(row.get("colors")),
        pics=_json_loads_maybe(row.get("pics")),
        dimensions=_json_loads_maybe(row.get("dimensions")),
        characteristics=_json_loads_maybe(row.get("characteristics")),
        updated_at=_iso_or_none(row.get("updated_at")),
    )


def resolve_category_id(product_row: Mapping[str, Any], requested_category_id: int | None) -> int:
    subject_id = product_row.get("subject_id")
    if requested_category_id is None:
        if subject_id is None:
            raise SkuMeaningScopeError("category_id is required because products.subject_id is empty")
        return int(subject_id)
    if subject_id is not None and int(subject_id) != int(requested_category_id):
        raise SkuMeaningScopeError(
            f"SKU nm_id={product_row.get('nm_id')} subject_id={subject_id} is outside category_id={requested_category_id}"
        )
    return int(requested_category_id)


def build_sku_evidence_pack(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int | None = None,
    review_limit: int = 30,
) -> SkuMeaningEvidencePack:
    """Build a human-readable and LLM-ready evidence pack for one SKU."""

    product_row = _fetch_product_row(session, project_id=project_id, nm_id=nm_id)
    resolved_category_id = resolve_category_id(product_row, category_id)
    product = _product_evidence_from_row(product_row)
    warnings: list[str] = []

    category_prior: dict[str, Any] = {}
    try:
        category_prior = build_category_meaning(
            session,
            project_id=int(project_id),
            category_id=int(resolved_category_id),
        ).to_dict()
    except Exception as exc:
        warnings.append(f"category_prior_unavailable:{type(exc).__name__}")

    product_projection: dict[str, Any] = {}
    product_projection_flags: dict[str, Any] = {}
    try:
        projection, flags = build_product_projection(
            session,
            project_id=int(project_id),
            category_id=int(resolved_category_id),
            nm_id=int(nm_id),
        )
        product_projection = projection.to_dict()
        product_projection_flags = flags.to_dict()
    except ProductProjectionScopeError as exc:
        raise SkuMeaningScopeError(str(exc)) from exc
    except ProductProjectionError as exc:
        warnings.append(f"product_projection_unavailable:{type(exc).__name__}")
    except Exception as exc:
        warnings.append(f"product_projection_unavailable:{type(exc).__name__}")

    reviews, review_warnings = _fetch_sku_reviews(
        session,
        project_id=int(project_id),
        nm_id=int(nm_id),
        limit=int(review_limit),
    )
    warnings.extend(review_warnings)

    evidence_refs = {
        "product.title": "Product card title",
        "product.description": "Product card description",
        "product.characteristics": "Product characteristics",
        "product.reviews": "SKU reviews from wb_feedback_snapshots",
        "category_prior": "Existing category meaning/category expressive prior",
        "product_projection": "Current deterministic ProductProjection baseline",
    }

    hash_payload = {
        "schema_version": "sku_evidence_pack_v0",
        "project_id": int(project_id),
        "category_id": int(resolved_category_id),
        "nm_id": int(nm_id),
        "product": product.model_dump(mode="json"),
        "reviews": [item.model_dump(mode="json") for item in reviews],
        "category_prior": category_prior,
        "product_projection": product_projection,
        "product_projection_flags": product_projection_flags,
    }
    evidence_hash = _hash_evidence(hash_payload)

    return SkuMeaningEvidencePack(
        project_id=int(project_id),
        category_id=int(resolved_category_id),
        nm_id=int(nm_id),
        evidence_hash=evidence_hash,
        product=product,
        reviews=reviews,
        category_prior=category_prior,
        product_projection=product_projection,
        product_projection_flags=product_projection_flags,
        evidence_refs=evidence_refs,
        warnings=warnings,
    )
