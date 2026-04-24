"""Side-by-side comparison runner for current matcher vs atoms matcher."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SeoQueryClusterMembership, SeoQueryMeaning, SeoSkuMeaningAnnotation
from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.atoms.v1.llm_extractors import extract_query_atoms, extract_sku_atoms
from app.services.seo.atoms.v1.schemas import (
    ComparisonResult,
    ComparisonRow,
    QueryAtomsRecord,
    SkuAtoms,
)
from app.services.seo.experiments.meaning_atoms.matcher import match_atoms
from app.services.seo.experiments.meaning_atoms.report import apply_eval_labels, compute_metrics, load_eval_labels, write_artifacts
from app.services.seo.providers.base import ChatProvider
from app.services.seo.query_meaning_matcher.matcher import run_meaning_aware_matcher
from app.services.seo.query_pipeline import normalize_query_text
from app.services.seo.sku_meaning.evidence import build_sku_evidence_pack


def _timestamped_output_dir(base_dir: Path, *, project_id: int, category_id: int) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_dir / f"{stamp}_project{int(project_id)}_category{int(category_id)}"


def select_sample_nm_ids(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    requested_nm_ids: list[int] | None = None,
    sample_size: int = 10,
) -> list[int]:
    if requested_nm_ids:
        return [int(item) for item in requested_nm_ids][: max(1, int(sample_size))]

    rows = session.scalars(
        select(SeoSkuMeaningAnnotation.nm_id)
        .where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.category_id == int(category_id),
        )
        .order_by(SeoSkuMeaningAnnotation.updated_at.desc())
    ).all()
    ordered: list[int] = []
    if int(category_id) == 812 and 292541341 in [int(item) for item in rows]:
        ordered.append(292541341)
    for row in rows:
        nm_id = int(row)
        if nm_id not in ordered:
            ordered.append(nm_id)
        if len(ordered) >= int(sample_size):
            break
    return ordered


def _ranking_by_cluster(session: Session, *, project_id: int, category_id: int, cluster_ids: list[int]) -> dict[int, float]:
    if not cluster_ids:
        return {}
    rows = session.execute(
        select(SeoQueryClusterMembership.cluster_id, SeoQueryClusterMembership.ranking_value_used)
        .where(
            SeoQueryClusterMembership.project_id == int(project_id),
            SeoQueryClusterMembership.category_id == int(category_id),
            SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
        )
        .order_by(desc(SeoQueryClusterMembership.ranking_value_used))
    ).all()
    result: dict[int, float] = {}
    for cluster_id, ranking in rows:
        if cluster_id is None:
            continue
        try:
            value = float(ranking or 0)
        except Exception:
            value = 0.0
        result[int(cluster_id)] = max(result.get(int(cluster_id), 0.0), value)
    return result


def _query_display(row: SeoQueryMeaning) -> str:
    examples = row.source_query_examples if isinstance(row.source_query_examples, list) else []
    return str(examples[0]) if examples else str(row.cluster_key)


def _load_query_meanings(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    query_limit: int,
) -> list[tuple[SeoQueryMeaning, float | None]]:
    rows = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
        )
    ).all()
    ranking = _ranking_by_cluster(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_ids=[int(row.cluster_id) for row in rows if row.cluster_id is not None],
    )
    paired = [(row, ranking.get(int(row.cluster_id)) if row.cluster_id is not None else None) for row in rows]
    paired.sort(key=lambda item: (-(item[1] or 0), _query_display(item[0])))
    return paired[: max(1, int(query_limit))]


def _load_query_meanings_by_cluster_keys(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    cluster_keys: set[str],
) -> list[tuple[SeoQueryMeaning, float | None]]:
    if not cluster_keys:
        return []
    rows = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
            SeoQueryMeaning.cluster_key.in_(sorted(cluster_keys)),
        )
    ).all()
    ranking = _ranking_by_cluster(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_ids=[int(row.cluster_id) for row in rows if row.cluster_id is not None],
    )
    return [(row, ranking.get(int(row.cluster_id)) if row.cluster_id is not None else None) for row in rows]


def _annotation_for_sku(session: Session, *, project_id: int, category_id: int, nm_id: int) -> SeoSkuMeaningAnnotation | None:
    return session.scalars(
        select(SeoSkuMeaningAnnotation)
        .where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.category_id == int(category_id),
            SeoSkuMeaningAnnotation.nm_id == int(nm_id),
        )
        .order_by(SeoSkuMeaningAnnotation.updated_at.desc())
    ).first()


def _safe_evidence_payload(session: Session, *, project_id: int, category_id: int, nm_id: int) -> dict[str, Any]:
    try:
        return build_sku_evidence_pack(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
        ).model_dump(mode="json")
    except Exception as exc:
        return {
            "schema_version": "sku_evidence_pack_v0",
            "project_id": int(project_id),
            "category_id": int(category_id),
            "nm_id": int(nm_id),
            "evidence_hash": f"fallback:{type(exc).__name__}",
            "product": {},
            "reviews": [],
            "category_prior": {},
            "product_projection": {},
            "product_projection_flags": {},
            "warnings": [f"evidence_unavailable:{type(exc).__name__}"],
        }


def _current_matcher_items(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int,
    include_rejected: bool,
) -> dict[str, MeaningAwareMatcherItem]:
    nested = session.begin_nested()
    try:
        response = run_meaning_aware_matcher(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
            limit=int(limit),
            include_rejected=include_rejected,
        )
        items: dict[str, MeaningAwareMatcherItem] = {}
        for bucket_items in response.buckets.values():
            for item in bucket_items:
                key = str(item.cluster_key or normalize_query_text(item.query))
                items[key] = item
        return items
    except Exception:
        return {}
    finally:
        try:
            if nested.is_active:
                nested.rollback()
        except Exception:
            session.rollback()
        session.expire_all()


def _query_payload(row: SeoQueryMeaning, *, ranking_value: float | None) -> dict[str, Any]:
    return {
        "query": _query_display(row),
        "cluster_key": row.cluster_key,
        "cluster_id": row.cluster_id,
        "source_query_examples": row.source_query_examples or [],
        "current_query_meaning": row.meaning_payload or {},
        "canonical_text": row.canonical_text,
        "genericness": row.genericness,
        "constraints": row.constraints or [],
        "conflicts_if_missing": row.conflicts_if_missing or [],
        "ranking_value_used": ranking_value,
    }


def _diff_type(row: ComparisonRow) -> str:
    if row.current_bucket == row.atoms_bucket:
        return "same"
    if row.current_bucket == "primary" and row.atoms_bucket != "primary":
        return "bad_primary_removed"
    if row.current_bucket != "primary" and row.atoms_bucket == "primary":
        return "target_lifted"
    if row.atoms_bucket == "rejected":
        return "atoms_rejected"
    return "changed"


def _merge_rows(
    *,
    nm_id: int,
    current: dict[str, MeaningAwareMatcherItem],
    atoms: dict[str, Any],
) -> list[ComparisonRow]:
    keys = sorted(set(current) | set(atoms))
    rows: list[ComparisonRow] = []
    for key in keys:
        current_item = current.get(key)
        atoms_item = atoms.get(key)
        row = ComparisonRow(
            nm_id=int(nm_id),
            query=str(atoms_item.query if atoms_item is not None else current_item.query if current_item is not None else key),
            cluster_key=str(atoms_item.cluster_key if atoms_item is not None else current_item.cluster_key if current_item is not None else key),
            ranking_value_used=(
                atoms_item.ranking_value_used
                if atoms_item is not None
                else current_item.ranking_value_used
                if current_item is not None
                else None
            ),
            current_bucket=str(current_item.bucket) if current_item is not None else None,
            current_score=float(current_item.score) if current_item is not None else None,
            atoms_bucket=str(atoms_item.bucket) if atoms_item is not None else None,
            atoms_score=float(atoms_item.score) if atoms_item is not None else None,
            diff_type="pending",
            current_reasons=list(current_item.reasons) if current_item is not None else [],
            atoms_reasons=list(atoms_item.reasons) if atoms_item is not None else [],
            matched_atoms=list(atoms_item.matched_atoms) if atoms_item is not None else [],
            missing_atoms=list(atoms_item.missing_atoms) if atoms_item is not None else [],
            conflict_atoms=list(atoms_item.conflict_atoms) if atoms_item is not None else [],
        )
        row.diff_type = _diff_type(row)
        rows.append(row)
    return rows


def run_comparison(
    session: Session,
    *,
    project_id: int = 1,
    category_id: int = 812,
    nm_ids: list[int] | None = None,
    sample_size: int = 10,
    limit_per_sku: int = 120,
    query_limit: int = 500,
    output_dir: Path,
    eval_labels_path: Path | None = None,
    provider: ChatProvider | None = None,
    force_refresh_llm: bool = False,
    include_rejected: bool = True,
) -> ComparisonResult:
    resolved_nm_ids = select_sample_nm_ids(
        session,
        project_id=project_id,
        category_id=category_id,
        requested_nm_ids=nm_ids,
        sample_size=sample_size,
    )
    run_dir = _timestamped_output_dir(output_dir, project_id=project_id, category_id=category_id)
    cache_dir = output_dir / "llm_cache"
    current_by_sku: dict[int, dict[str, MeaningAwareMatcherItem]] = {}
    current_cluster_keys: set[str] = set()
    for nm_id in resolved_nm_ids:
        current = _current_matcher_items(
            session,
            project_id=project_id,
            category_id=category_id,
            nm_id=nm_id,
            limit=limit_per_sku,
            include_rejected=include_rejected,
        )
        current_by_sku[int(nm_id)] = current
        current_cluster_keys.update(key for key in current if key)

    query_rows = _load_query_meanings(session, project_id=project_id, category_id=category_id, query_limit=query_limit)
    loaded_keys = {str(row.cluster_key) for row, _ in query_rows}
    extra_rows = _load_query_meanings_by_cluster_keys(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_keys=current_cluster_keys - loaded_keys,
    )
    query_rows.extend(extra_rows)
    query_records: list[QueryAtomsRecord] = []
    for query_row, ranking_value in query_rows:
        atoms = extract_query_atoms(
            _query_payload(query_row, ranking_value=ranking_value),
            provider=provider,
            cache_dir=cache_dir,
            force_refresh=force_refresh_llm,
        )
        query_records.append(
            QueryAtomsRecord(
                query=_query_display(query_row),
                cluster_key=str(query_row.cluster_key),
                cluster_id=int(query_row.cluster_id) if query_row.cluster_id is not None else None,
                query_meaning_id=int(query_row.id),
                ranking_value_used=ranking_value,
                current_genericness=str(query_row.genericness or ""),
                atoms=atoms,
            )
        )

    rows: list[ComparisonRow] = []
    sku_atom_items: list[SkuAtoms] = []
    for nm_id in resolved_nm_ids:
        annotation = _annotation_for_sku(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
        meaning_payload: Mapping[str, Any] = annotation.meaning_payload if annotation is not None else {}
        evidence_payload = _safe_evidence_payload(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
        sku_atoms = extract_sku_atoms(
            evidence_payload,
            meaning_payload=meaning_payload,
            provider=provider,
            cache_dir=cache_dir,
            force_refresh=force_refresh_llm,
        )
        sku_atom_items.append(sku_atoms)
        current = current_by_sku.get(int(nm_id), {})
        atoms_results = {
            record.cluster_key: match_atoms(
                sku_atoms,
                record.atoms,
                query_text=record.query,
                cluster_key=record.cluster_key,
                ranking_value_used=record.ranking_value_used,
            )
            for record in query_records
        }
        rows.extend(_merge_rows(nm_id=nm_id, current=current, atoms=atoms_results))

    labels = load_eval_labels(eval_labels_path)
    apply_eval_labels(rows, labels)
    result = ComparisonResult(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_ids=resolved_nm_ids,
        rows=rows,
        metrics=compute_metrics(rows),
    )
    write_artifacts(result, output_dir=run_dir, sku_atoms=sku_atom_items, query_atoms=query_records)
    return result
