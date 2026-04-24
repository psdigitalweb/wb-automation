"""Persistent meaning-atoms extraction and storage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import desc, func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import settings
from app.models import SeoMeaningAtom, SeoQueryMeaning, SeoSkuMeaningAnnotation
from app.services.seo.atoms.v1.guards import apply_query_guards, apply_sku_guards, append_atom_unique
from app.services.seo.atoms.v1.llm_extractors import extract_query_atoms, extract_sku_atoms
from app.services.seo.atoms.v1.schemas import MeaningAtom, QueryAtoms, SkuAtoms
from app.services.seo.atoms.v1.vision import extract_vision_sku_atoms
from app.services.seo.query_meaning_matcher.canonical import listify, stable_hash


ATOMS_SOURCE_VERSION = "production_atoms_v1_visual_motifs"
QUERY_ATOMS_SOURCE_VERSION = "query_atoms_from_meaning_v0"
SKU_ATOMS_SOURCE_VERSION = "sku_atoms_from_meaning_v0"
VISION_ATOMS_SOURCE_VERSION = "sku_vision_atoms_v0"


def _atoms_table_exists(session: Session) -> bool:
    bind = session.get_bind()
    try:
        return bool(inspect(bind).has_table("seo_meaning_atoms"))
    except Exception:
        return True


def _cache_dir() -> Path:
    override = os.getenv("SEO_MEANING_ATOMS_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(settings.INTERNAL_DATA_DIR) / "seo_meaning_atoms_cache"


def _summary_from_atoms(payload: Mapping[str, Any]) -> str:
    product_type = str(payload.get("product_type") or "").strip()
    parts: list[str] = []
    if product_type:
        parts.append(f"товар: {product_type}")
    for key, label in (
        ("facts", "факты"),
        ("positive_atoms", "подходит"),
        ("negative_fit_atoms", "не подходит"),
        ("required_atoms", "требует"),
        ("preferred_atoms", "желательно"),
        ("excluded_atoms", "исключает"),
    ):
        values = []
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw[:8]:
                if isinstance(item, Mapping):
                    value = item.get("value")
                    field = item.get("field") or item.get("type")
                    if value not in (None, "", []):
                        values.append(f"{field}:{value}")
        if values:
            parts.append(f"{label}: {', '.join(values)}")
    return "\n".join(parts)


def get_latest_atoms_record(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    entity_type: str,
    entity_id: int | None = None,
    nm_id: int | None = None,
) -> SeoMeaningAtom | None:
    if not _atoms_table_exists(session):
        return None
    stmt = select(SeoMeaningAtom).where(
        SeoMeaningAtom.project_id == int(project_id),
        SeoMeaningAtom.category_id == int(category_id),
        SeoMeaningAtom.entity_type == str(entity_type),
    )
    if entity_id is not None:
        stmt = stmt.where(SeoMeaningAtom.entity_id == int(entity_id))
    if nm_id is not None:
        stmt = stmt.where(SeoMeaningAtom.nm_id == int(nm_id))
    try:
        return session.scalars(stmt.order_by(desc(SeoMeaningAtom.updated_at), desc(SeoMeaningAtom.id))).first()
    except OperationalError as exc:
        if "seo_meaning_atoms" in str(exc).lower():
            return None
        raise


def get_atoms_payload(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    entity_type: str,
    entity_id: int | None = None,
    nm_id: int | None = None,
) -> dict[str, Any] | None:
    row = get_latest_atoms_record(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type=entity_type,
        entity_id=entity_id,
        nm_id=nm_id,
    )
    if row is None or row.status != "ready":
        return None
    return dict(row.atoms_payload or {})


def _upsert_atoms_record(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    entity_type: str,
    input_hash: str,
    atoms_payload: Mapping[str, Any],
    entity_id: int | None = None,
    nm_id: int | None = None,
    source_version: str,
    model: str | None = None,
    prompt_version: str | None = None,
    status: str = "ready",
    error: str | None = None,
) -> SeoMeaningAtom:
    stmt = select(SeoMeaningAtom).where(
        SeoMeaningAtom.project_id == int(project_id),
        SeoMeaningAtom.category_id == int(category_id),
        SeoMeaningAtom.entity_type == str(entity_type),
    )
    if entity_id is None:
        stmt = stmt.where(SeoMeaningAtom.entity_id.is_(None))
    else:
        stmt = stmt.where(SeoMeaningAtom.entity_id == int(entity_id))
    if nm_id is None:
        stmt = stmt.where(SeoMeaningAtom.nm_id.is_(None))
    else:
        stmt = stmt.where(SeoMeaningAtom.nm_id == int(nm_id))
    row = session.scalars(stmt.order_by(desc(SeoMeaningAtom.updated_at), desc(SeoMeaningAtom.id))).first()
    if row is None:
        row = SeoMeaningAtom(
            project_id=int(project_id),
            category_id=int(category_id),
            entity_type=str(entity_type),
            entity_id=int(entity_id) if entity_id is not None else None,
            nm_id=int(nm_id) if nm_id is not None else None,
        )
        session.add(row)
    row.schema_version = str(atoms_payload.get("schema_version") or "meaning_atoms_v0")
    row.source_version = source_version
    row.model = model
    row.prompt_version = prompt_version
    row.input_hash = str(input_hash)
    row.atoms_payload = dict(atoms_payload)
    row.canonical_summary = _summary_from_atoms(atoms_payload)
    row.status = status
    row.error = error
    session.flush()
    return row


def _query_atoms_from_meaning(row: SeoQueryMeaning) -> QueryAtoms:
    payload = row.meaning_payload if isinstance(row.meaning_payload, Mapping) else {}
    functional = payload.get("functional") if isinstance(payload.get("functional"), Mapping) else {}
    expressive = payload.get("expressive") if isinstance(payload.get("expressive"), Mapping) else {}
    examples = [str(item) for item in listify(row.source_query_examples) if str(item).strip()]
    query_text = examples[0] if examples else str(row.cluster_key or "")
    atoms = QueryAtoms(
        cluster_key=str(row.cluster_key or ""),
        query=query_text,
        source_query_examples=examples,
        product_type=str(functional.get("product_type") or ""),
        buyer_intent=query_text,
        genericness=str(row.genericness or payload.get("genericness") or "specific"),
        confidence=dict(payload.get("confidence") or {}) if isinstance(payload.get("confidence"), Mapping) else {},
        evidence_refs=["query_meaning"],
    )
    if atoms.product_type:
        append_atom_unique(
            atoms.required_atoms,
            MeaningAtom(type="product_type", field="product_type", value=atoms.product_type, importance="hard", source="query_meaning", confidence=0.9),
        )
    for value in listify(functional.get("attributes")) + listify(functional.get("use_cases")):
        append_atom_unique(
            atoms.preferred_atoms,
            MeaningAtom(type="attribute", field="attribute", value=value, importance="soft", source="query_meaning", confidence=0.65),
        )
    for value in listify(expressive.get("styles")) + listify(expressive.get("vibes")) + listify(expressive.get("emotions")):
        append_atom_unique(
            atoms.preferred_atoms,
            MeaningAtom(type="expressive", field="expressive", value=value, importance="soft", source="query_meaning", confidence=0.7),
        )
    for value in listify(payload.get("audience")):
        append_atom_unique(
            atoms.preferred_atoms,
            MeaningAtom(type="recipient", field="recipient", value=value, importance="soft", source="query_meaning", confidence=0.65),
        )
    for value in listify(payload.get("occasion")) + listify(expressive.get("gift_contexts")):
        append_atom_unique(
            atoms.preferred_atoms,
            MeaningAtom(type="occasion", field="occasion", value=value, importance="soft", source="query_meaning", confidence=0.6),
        )
    for value in listify(row.constraints or payload.get("constraints")):
        append_atom_unique(
            atoms.required_atoms,
            MeaningAtom(type="attribute", field="constraint", value=value, importance="hard", source="query_meaning", confidence=0.75),
        )
    return apply_query_guards(atoms, [query_text, *examples])


def build_query_atoms_for_category(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int | None = 5000,
    force_refresh: bool = False,
    use_llm: bool = False,
) -> dict[str, Any]:
    stmt = (
        select(SeoQueryMeaning)
        .where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
        )
        .order_by(SeoQueryMeaning.id.asc())
    )
    if limit is not None and int(limit) > 0:
        stmt = stmt.limit(max(1, int(limit)))
    rows = session.scalars(stmt).all()
    created = updated = skipped = errors = 0
    error_items: list[dict[str, Any]] = []
    cache_dir = _cache_dir() / "query_atoms"
    for row in rows:
        payload_for_hash = {
            "query_meaning_id": int(row.id),
            "input_hash": row.input_hash,
            "meaning_payload": row.meaning_payload or {},
            "canonical_text": row.canonical_text or "",
            "source_version": ATOMS_SOURCE_VERSION,
        }
        input_hash = stable_hash(payload_for_hash)
        existing = get_latest_atoms_record(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
        )
        if existing is not None and existing.input_hash == input_hash and existing.status == "ready" and not force_refresh:
            skipped += 1
            continue
        try:
            before_exists = existing is not None
            if use_llm:
                examples = [str(item) for item in listify(row.source_query_examples) if str(item).strip()]
                atoms = extract_query_atoms(
                    {
                        "cluster_key": row.cluster_key,
                        "query": examples[0] if examples else row.cluster_key,
                        "source_query_examples": examples,
                        "current_query_meaning": row.meaning_payload or {},
                        "canonical_text": row.canonical_text,
                        "genericness": row.genericness,
                        "constraints": row.constraints or [],
                    },
                    cache_dir=cache_dir,
                    force_refresh=force_refresh,
                )
            else:
                atoms = _query_atoms_from_meaning(row)
            _upsert_atoms_record(
                session,
                project_id=project_id,
                category_id=category_id,
                entity_type="query_meaning",
                entity_id=int(row.id),
                input_hash=input_hash,
                atoms_payload=atoms.model_dump(mode="json"),
                source_version=QUERY_ATOMS_SOURCE_VERSION if not use_llm else ATOMS_SOURCE_VERSION,
                prompt_version="query_atoms_v0",
            )
            if before_exists:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            errors += 1
            error_items.append({"query_meaning_id": int(row.id), "cluster_key": row.cluster_key, "error": str(exc)})
    session.flush()
    return {
        "total": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_items": error_items[:20],
    }


def _fallback_sku_atoms(
    *,
    evidence_payload: Mapping[str, Any],
    meaning_payload: Mapping[str, Any],
) -> SkuAtoms:
    product = evidence_payload.get("product") if isinstance(evidence_payload.get("product"), Mapping) else {}
    functional = meaning_payload.get("functional") if isinstance(meaning_payload.get("functional"), Mapping) else {}
    atoms = SkuAtoms(
        project_id=int(evidence_payload.get("project_id")) if evidence_payload.get("project_id") is not None else None,
        category_id=int(evidence_payload.get("category_id")) if evidence_payload.get("category_id") is not None else None,
        nm_id=int(evidence_payload.get("nm_id")) if evidence_payload.get("nm_id") is not None else None,
        product_type=str(functional.get("product_type") or product.get("subject_name") or ""),
        product_identity=str(product.get("title") or ""),
        confidence={"fallback": 0.55},
        evidence_refs=["sku_meaning", "product_data"],
    )
    return apply_sku_guards(atoms, evidence=evidence_payload, meaning_payload=meaning_payload)


def ensure_sku_atoms(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    evidence_payload: Mapping[str, Any],
    annotation: SeoSkuMeaningAnnotation | None,
    force_refresh: bool = False,
    include_vision: bool = True,
) -> dict[str, Any]:
    meaning_payload = dict(annotation.meaning_payload or {}) if annotation is not None else {}
    annotation_id = int(annotation.id) if annotation is not None else None
    input_hash = stable_hash(
        {
            "kind": "sku_atoms",
            "evidence_hash": evidence_payload.get("evidence_hash"),
            "meaning_payload": meaning_payload,
            "source_version": ATOMS_SOURCE_VERSION,
        }
    )
    existing = get_latest_atoms_record(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=annotation_id,
        nm_id=nm_id,
    )
    sku_atoms: SkuAtoms | None = None
    if existing is not None and existing.input_hash == input_hash and existing.status == "ready" and not force_refresh:
        sku_atoms = SkuAtoms.model_validate(existing.atoms_payload or {})
    else:
        try:
            sku_atoms = extract_sku_atoms(
                evidence_payload,
                meaning_payload=meaning_payload,
                cache_dir=_cache_dir() / "sku_atoms",
                force_refresh=force_refresh,
            )
            source_version = ATOMS_SOURCE_VERSION
        except Exception:
            sku_atoms = _fallback_sku_atoms(evidence_payload=evidence_payload, meaning_payload=meaning_payload)
            source_version = SKU_ATOMS_SOURCE_VERSION
        _upsert_atoms_record(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="sku_meaning",
            entity_id=annotation_id,
            nm_id=nm_id,
            input_hash=input_hash,
            atoms_payload=sku_atoms.model_dump(mode="json"),
            source_version=source_version,
            prompt_version="sku_atoms_v0",
        )

    vision_status = "not_run"
    if include_vision:
        vision_hash = stable_hash(
            {
                "kind": "sku_vision_atoms",
                "evidence_hash": evidence_payload.get("evidence_hash"),
                "source_version": VISION_ATOMS_SOURCE_VERSION,
            }
        )
        existing_vision = get_latest_atoms_record(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="sku_vision",
            entity_id=annotation_id,
            nm_id=nm_id,
        )
        if existing_vision is not None and existing_vision.input_hash == vision_hash and existing_vision.status == "ready" and not force_refresh:
            vision_status = "ready"
        else:
            try:
                vision_atoms = extract_vision_sku_atoms(
                    evidence_payload,
                    cache_dir=_cache_dir() / "vision_atoms",
                    force_refresh=force_refresh,
                )
                useful = bool(vision_atoms.facts or vision_atoms.positive_atoms or vision_atoms.negative_fit_atoms)
                _upsert_atoms_record(
                    session,
                    project_id=project_id,
                    category_id=category_id,
                    entity_type="sku_vision",
                    entity_id=annotation_id,
                    nm_id=nm_id,
                    input_hash=vision_hash,
                    atoms_payload=vision_atoms.model_dump(mode="json"),
                    source_version=VISION_ATOMS_SOURCE_VERSION,
                    prompt_version="sku_vision_atoms_v0",
                    status="ready" if useful else "empty",
                )
                vision_status = "ready" if useful else "empty"
            except Exception as exc:
                _upsert_atoms_record(
                    session,
                    project_id=project_id,
                    category_id=category_id,
                    entity_type="sku_vision",
                    entity_id=annotation_id,
                    nm_id=nm_id,
                    input_hash=vision_hash,
                    atoms_payload={},
                    source_version=VISION_ATOMS_SOURCE_VERSION,
                    prompt_version="sku_vision_atoms_v0",
                    status="error",
                    error=str(exc),
                )
                vision_status = "error"
    session.flush()
    return {"sku_atoms": sku_atoms.model_dump(mode="json") if sku_atoms is not None else {}, "vision_status": vision_status}


def merge_sku_and_vision_atoms(sku_payload: Mapping[str, Any] | None, vision_payload: Mapping[str, Any] | None) -> SkuAtoms | None:
    if not sku_payload:
        return None
    sku = SkuAtoms.model_validate(dict(sku_payload))
    if not vision_payload:
        return sku
    vision = SkuAtoms.model_validate(dict(vision_payload))
    for item in vision.facts:
        append_atom_unique(sku.facts, item)
    for item in vision.positive_atoms:
        append_atom_unique(sku.positive_atoms, item)
    for item in vision.negative_fit_atoms:
        append_atom_unique(sku.negative_fit_atoms, item)
    return sku


def count_ready_query_atoms(session: Session, *, project_id: int, category_id: int) -> int:
    if not _atoms_table_exists(session):
        return 0
    try:
        return int(
            session.execute(
                select(func.count(SeoMeaningAtom.id)).where(
                    SeoMeaningAtom.project_id == int(project_id),
                    SeoMeaningAtom.category_id == int(category_id),
                    SeoMeaningAtom.entity_type == "query_meaning",
                    SeoMeaningAtom.status == "ready",
                )
            ).scalar_one()
            or 0
        )
    except OperationalError as exc:
        if "seo_meaning_atoms" in str(exc).lower():
            return 0
        raise
