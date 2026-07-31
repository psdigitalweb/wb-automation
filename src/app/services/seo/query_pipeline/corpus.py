"""Category query corpus summary and destructive maintenance helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryBootstrapRun,
    SeoCategoryMatchingReadiness,
    SeoCategoryMeaningAxes,
    SeoContentVersion,
    SeoGenerationRun,
    SeoMeaningAtom,
    SeoMeaningEmbedding,
    SeoQueryAnnotation,
    SeoQueryAnnotationVersion,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryMeaning,
    SeoQueryNormalized,
    SeoQueryRaw,
    SeoQueryScore,
    SeoScoreExplanation,
    SeoScoreRun,
    SeoSkuQueryJudgment,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)
from app.services.seo.query_pipeline.normalization import normalize_query_text


@dataclass(frozen=True)
class CorpusNormalizedQuery:
    id: int
    normalized_query: str
    display_query: str
    raw_query_example: str
    raw_row_count: int
    frequency_total: str
    normalization_version: str


@dataclass(frozen=True)
class QueryCorpusSummary:
    project_id: int
    category_id: int
    active_batches_count: int
    total_batches_count: int
    total_raw_rows: int
    total_normalized_rows: int
    unique_normalized_queries: int
    duplicate_across_batches_count: int
    latest_batch_id: int | None
    total_matching_rows: int
    normalized_queries: list[CorpusNormalizedQuery] = field(default_factory=list)


@dataclass(frozen=True)
class QueryCorpusDeleteResult:
    project_id: int
    category_id: int
    action: str
    deleted_batch_id: int | None
    deleted_counts: dict[str, int]
    preserved_judgments_count: int
    deleted_judgments_count: int
    remaining_active_batches_count: int
    remaining_unique_queries_count: int


def _decimal_to_string(value: Any) -> str:
    if value is None:
        return "0"
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    normalized = decimal_value.normalize()
    return format(normalized, "f") if normalized == normalized.to_integral() else format(normalized, "f").rstrip("0").rstrip(".")


def _count_result(result: Any) -> int:
    value = getattr(result, "rowcount", None)
    return int(value) if value is not None and value >= 0 else 0


def _add_count(counts: dict[str, int], table_name: str, value: int) -> None:
    counts[table_name] = int(counts.get(table_name, 0)) + int(value)


def _completed_batches_query(project_id: int, category_id: int):
    return select(SeoQueryBatch).where(
        SeoQueryBatch.project_id == int(project_id),
        SeoQueryBatch.category_id == int(category_id),
        SeoQueryBatch.status == "completed",
    )


def completed_batch_ids(session: Session, *, project_id: int, category_id: int) -> list[int]:
    return [
        int(row.id)
        for row in session.scalars(
            _completed_batches_query(project_id, category_id).order_by(SeoQueryBatch.created_at.asc(), SeoQueryBatch.id.asc())
        ).all()
    ]


def remaining_normalized_query_texts(session: Session, *, project_id: int, category_id: int) -> set[str]:
    batch_ids = completed_batch_ids(session, project_id=project_id, category_id=category_id)
    if not batch_ids:
        return set()
    rows = session.scalars(
        select(SeoQueryNormalized.normalized_query)
        .where(
            SeoQueryNormalized.project_id == int(project_id),
            SeoQueryNormalized.category_id == int(category_id),
            SeoQueryNormalized.batch_id.in_(batch_ids),
        )
        .distinct()
    ).all()
    return {str(item) for item in rows}


def get_query_corpus_summary(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
) -> QueryCorpusSummary:
    batch_ids = completed_batch_ids(session, project_id=project_id, category_id=category_id)
    total_batches = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryBatch).where(
                SeoQueryBatch.project_id == int(project_id),
                SeoQueryBatch.category_id == int(category_id),
            )
        )
        or 0
    )
    latest_batch = session.scalars(
        _completed_batches_query(project_id, category_id).order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc()).limit(1)
    ).first()

    if not batch_ids:
        return QueryCorpusSummary(
            project_id=int(project_id),
            category_id=int(category_id),
            active_batches_count=0,
            total_batches_count=total_batches,
            total_raw_rows=0,
            total_normalized_rows=0,
            unique_normalized_queries=0,
            duplicate_across_batches_count=0,
            latest_batch_id=None,
            total_matching_rows=0,
            normalized_queries=[],
        )

    base_filters = [
        SeoQueryNormalized.project_id == int(project_id),
        SeoQueryNormalized.category_id == int(category_id),
        SeoQueryNormalized.batch_id.in_(batch_ids),
    ]
    normalized_search = normalize_query_text(q or "")
    if normalized_search:
        base_filters.append(SeoQueryNormalized.normalized_query.contains(normalized_search))

    grouped = (
        select(
            func.min(SeoQueryNormalized.id).label("id"),
            SeoQueryNormalized.normalized_query.label("normalized_query"),
            func.min(SeoQueryNormalized.display_query).label("display_query"),
            func.sum(SeoQueryNormalized.raw_row_count).label("raw_row_count"),
            func.sum(SeoQueryNormalized.frequency_total).label("frequency_total"),
            func.min(SeoQueryNormalized.normalization_version).label("normalization_version"),
            func.count(SeoQueryNormalized.id).label("batch_record_count"),
        )
        .where(*base_filters)
        .group_by(SeoQueryNormalized.normalized_query)
        .subquery()
    )
    total_matching = int(session.scalar(select(func.count()).select_from(grouped)) or 0)
    rows = session.execute(
        select(grouped)
        .order_by(grouped.c.frequency_total.desc(), grouped.c.normalized_query.asc())
        .limit(max(1, min(int(limit), 500)))
        .offset(max(0, int(offset)))
    ).mappings().all()

    total_raw_rows = int(
        session.scalar(
            select(func.coalesce(func.sum(SeoQueryBatch.row_count), 0)).where(
                SeoQueryBatch.project_id == int(project_id),
                SeoQueryBatch.category_id == int(category_id),
                SeoQueryBatch.status == "completed",
            )
        )
        or 0
    )
    total_normalized_rows = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryNormalized).where(
                SeoQueryNormalized.project_id == int(project_id),
                SeoQueryNormalized.category_id == int(category_id),
                SeoQueryNormalized.batch_id.in_(batch_ids),
            )
        )
        or 0
    )
    unique_queries = int(
        session.scalar(
            select(func.count(func.distinct(SeoQueryNormalized.normalized_query))).where(
                SeoQueryNormalized.project_id == int(project_id),
                SeoQueryNormalized.category_id == int(category_id),
                SeoQueryNormalized.batch_id.in_(batch_ids),
            )
        )
        or 0
    )

    return QueryCorpusSummary(
        project_id=int(project_id),
        category_id=int(category_id),
        active_batches_count=len(batch_ids),
        total_batches_count=total_batches,
        total_raw_rows=total_raw_rows,
        total_normalized_rows=total_normalized_rows,
        unique_normalized_queries=unique_queries,
        duplicate_across_batches_count=max(total_normalized_rows - unique_queries, 0),
        latest_batch_id=int(latest_batch.id) if latest_batch is not None else None,
        total_matching_rows=total_matching,
        normalized_queries=[
            CorpusNormalizedQuery(
                id=int(row["id"]),
                normalized_query=str(row["normalized_query"] or ""),
                display_query=str(row["display_query"] or row["normalized_query"] or ""),
                raw_query_example=str(row["display_query"] or row["normalized_query"] or ""),
                raw_row_count=int(row["raw_row_count"] or 0),
                frequency_total=_decimal_to_string(row["frequency_total"]),
                normalization_version=str(row["normalization_version"] or "v1_minimal"),
            )
            for row in rows
        ],
    )


def cancel_active_category_bootstrap_runs(session: Session, *, project_id: int, category_id: int) -> int:
    result = session.execute(
        update(SeoCategoryBootstrapRun)
        .where(
            SeoCategoryBootstrapRun.project_id == int(project_id),
            SeoCategoryBootstrapRun.category_id == int(category_id),
            SeoCategoryBootstrapRun.status.in_(["queued", "running"]),
        )
        .values(status="cancelled", current_step="cancelled", error="Cancelled by query corpus mutation")
    )
    return _count_result(result)


def _delete_generation_and_scoring(session: Session, *, project_id: int, category_id: int, counts: dict[str, int]) -> None:
    query_set_ids = select(SeoSkuQuerySet.id).where(
        SeoSkuQuerySet.project_id == int(project_id),
        SeoSkuQuerySet.category_id == int(category_id),
    )
    _add_count(
        counts,
        "seo_sku_query_set_items",
        _count_result(session.execute(delete(SeoSkuQuerySetItem).where(SeoSkuQuerySetItem.query_set_id.in_(query_set_ids)))),
    )
    _add_count(
        counts,
        "seo_sku_query_sets",
        _count_result(
            session.execute(
                delete(SeoSkuQuerySet).where(
                    SeoSkuQuerySet.project_id == int(project_id),
                    SeoSkuQuerySet.category_id == int(category_id),
                )
            )
        ),
    )
    content_ids = select(SeoContentVersion.id).where(
        SeoContentVersion.project_id == int(project_id),
        SeoContentVersion.category_id == int(category_id),
    )
    _add_count(
        counts,
        "seo_generation_runs",
        _count_result(session.execute(delete(SeoGenerationRun).where(SeoGenerationRun.content_version_id.in_(content_ids)))),
    )
    _add_count(
        counts,
        "seo_content_versions",
        _count_result(
            session.execute(
                delete(SeoContentVersion).where(
                    SeoContentVersion.project_id == int(project_id),
                    SeoContentVersion.category_id == int(category_id),
                )
            )
        ),
    )

    score_run_ids = select(SeoScoreRun.id).where(
        SeoScoreRun.project_id == int(project_id),
        SeoScoreRun.category_id == int(category_id),
    )
    query_score_ids = select(SeoQueryScore.id).where(SeoQueryScore.score_run_id.in_(score_run_ids))
    _add_count(
        counts,
        "seo_score_explanations",
        _count_result(session.execute(delete(SeoScoreExplanation).where(SeoScoreExplanation.query_score_id.in_(query_score_ids)))),
    )
    _add_count(
        counts,
        "seo_query_scores",
        _count_result(session.execute(delete(SeoQueryScore).where(SeoQueryScore.score_run_id.in_(score_run_ids)))),
    )
    _add_count(
        counts,
        "seo_score_runs",
        _count_result(
            session.execute(
                delete(SeoScoreRun).where(
                    SeoScoreRun.project_id == int(project_id),
                    SeoScoreRun.category_id == int(category_id),
                )
            )
        ),
    )


def _delete_query_derived_state(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    counts: dict[str, int],
    delete_bootstrap_state: bool,
) -> None:
    _delete_generation_and_scoring(session, project_id=project_id, category_id=category_id, counts=counts)
    _add_count(
        counts,
        "seo_meaning_embeddings",
        _count_result(
            session.execute(
                delete(SeoMeaningEmbedding).where(
                    SeoMeaningEmbedding.project_id == int(project_id),
                    SeoMeaningEmbedding.category_id == int(category_id),
                    SeoMeaningEmbedding.entity_type.in_(["query_meaning", "category_axes"]),
                )
            )
        ),
    )
    _add_count(
        counts,
        "seo_meaning_atoms",
        _count_result(
            session.execute(
                delete(SeoMeaningAtom).where(
                    SeoMeaningAtom.project_id == int(project_id),
                    SeoMeaningAtom.category_id == int(category_id),
                    SeoMeaningAtom.entity_type.in_(["query_meaning", "category_axes"]),
                )
            )
        ),
    )
    _add_count(
        counts,
        "seo_query_meanings",
        _count_result(
            session.execute(
                delete(SeoQueryMeaning).where(
                    SeoQueryMeaning.project_id == int(project_id),
                    SeoQueryMeaning.category_id == int(category_id),
                )
            )
        ),
    )
    _add_count(
        counts,
        "seo_category_meaning_axes",
        _count_result(
            session.execute(
                delete(SeoCategoryMeaningAxes).where(
                    SeoCategoryMeaningAxes.project_id == int(project_id),
                    SeoCategoryMeaningAxes.category_id == int(category_id),
                )
            )
        ),
    )
    _add_count(
        counts,
        "seo_query_cluster_memberships",
        _count_result(
            session.execute(
                delete(SeoQueryClusterMembership).where(
                    SeoQueryClusterMembership.project_id == int(project_id),
                    SeoQueryClusterMembership.category_id == int(category_id),
                )
            )
        ),
    )
    _add_count(
        counts,
        "seo_query_clusters",
        _count_result(
            session.execute(
                delete(SeoQueryCluster).where(
                    SeoQueryCluster.project_id == int(project_id),
                    SeoQueryCluster.category_id == int(category_id),
                )
            )
        ),
    )
    annotation_ids = select(SeoQueryAnnotation.id).where(
        SeoQueryAnnotation.project_id == int(project_id),
        SeoQueryAnnotation.category_id == int(category_id),
    )
    _add_count(
        counts,
        "seo_query_annotation_versions",
        _count_result(session.execute(delete(SeoQueryAnnotationVersion).where(SeoQueryAnnotationVersion.annotation_id.in_(annotation_ids)))),
    )
    _add_count(
        counts,
        "seo_query_annotations",
        _count_result(
            session.execute(
                delete(SeoQueryAnnotation).where(
                    SeoQueryAnnotation.project_id == int(project_id),
                    SeoQueryAnnotation.category_id == int(category_id),
                )
            )
        ),
    )
    if delete_bootstrap_state:
        _add_count(
            counts,
            "seo_category_matching_readiness",
            _count_result(
                session.execute(
                    delete(SeoCategoryMatchingReadiness).where(
                        SeoCategoryMatchingReadiness.project_id == int(project_id),
                        SeoCategoryMatchingReadiness.category_id == int(category_id),
                    )
                )
            ),
        )
        _add_count(
            counts,
            "seo_category_bootstrap_runs",
            _count_result(
                session.execute(
                    delete(SeoCategoryBootstrapRun).where(
                        SeoCategoryBootstrapRun.project_id == int(project_id),
                        SeoCategoryBootstrapRun.category_id == int(category_id),
                    )
                )
            ),
        )


def _sync_judgments_after_batch_delete(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    remaining_queries: set[str],
    counts: dict[str, int],
) -> tuple[int, int]:
    rows = session.scalars(
        select(SeoSkuQueryJudgment).where(
            SeoSkuQueryJudgment.project_id == int(project_id),
            SeoSkuQueryJudgment.category_id == int(category_id),
        )
    ).all()
    preserved = 0
    deleted_ids: list[int] = []
    for row in rows:
        normalized = normalize_query_text(str(row.normalized_query_text or row.query_text or ""))
        if normalized and normalized in remaining_queries:
            row.query_id = None
            row.cluster_id = None
            row.cluster_key = None
            row.normalized_query_text = normalized
            preserved += 1
        else:
            deleted_ids.append(int(row.id))
    deleted = 0
    if deleted_ids:
        deleted = _count_result(session.execute(delete(SeoSkuQueryJudgment).where(SeoSkuQueryJudgment.id.in_(deleted_ids))))
        _add_count(counts, "seo_sku_query_judgments", deleted)
    session.flush()
    return preserved, deleted


def delete_query_batch(session: Session, *, project_id: int, batch_id: int) -> QueryCorpusDeleteResult:
    batch = session.scalars(
        select(SeoQueryBatch).where(
            SeoQueryBatch.id == int(batch_id),
            SeoQueryBatch.project_id == int(project_id),
        )
    ).first()
    if batch is None:
        raise ValueError("SEO query import batch not found")

    category_id = int(batch.category_id)
    counts: dict[str, int] = {}
    _add_count(counts, "seo_category_bootstrap_runs_cancelled", cancel_active_category_bootstrap_runs(session, project_id=project_id, category_id=category_id))
    _delete_query_derived_state(session, project_id=project_id, category_id=category_id, counts=counts, delete_bootstrap_state=True)
    _add_count(counts, "seo_queries_raw", _count_result(session.execute(delete(SeoQueryRaw).where(SeoQueryRaw.batch_id == int(batch_id)))))
    _add_count(counts, "seo_queries_normalized", _count_result(session.execute(delete(SeoQueryNormalized).where(SeoQueryNormalized.batch_id == int(batch_id)))))
    _add_count(counts, "seo_query_batches", _count_result(session.execute(delete(SeoQueryBatch).where(SeoQueryBatch.id == int(batch_id)))))
    session.flush()

    remaining_queries = remaining_normalized_query_texts(session, project_id=project_id, category_id=category_id)
    preserved, deleted = _sync_judgments_after_batch_delete(
        session,
        project_id=project_id,
        category_id=category_id,
        remaining_queries=remaining_queries,
        counts=counts,
    )
    remaining_batches = completed_batch_ids(session, project_id=project_id, category_id=category_id)
    return QueryCorpusDeleteResult(
        project_id=int(project_id),
        category_id=category_id,
        action="delete_batch",
        deleted_batch_id=int(batch_id),
        deleted_counts=counts,
        preserved_judgments_count=preserved,
        deleted_judgments_count=deleted,
        remaining_active_batches_count=len(remaining_batches),
        remaining_unique_queries_count=len(remaining_queries),
    )


def clear_query_corpus(session: Session, *, project_id: int, category_id: int) -> QueryCorpusDeleteResult:
    counts: dict[str, int] = {}
    _add_count(counts, "seo_category_bootstrap_runs_cancelled", cancel_active_category_bootstrap_runs(session, project_id=project_id, category_id=category_id))
    _add_count(
        counts,
        "seo_sku_query_judgments",
        _count_result(
            session.execute(
                delete(SeoSkuQueryJudgment).where(
                    SeoSkuQueryJudgment.project_id == int(project_id),
                    SeoSkuQueryJudgment.category_id == int(category_id),
                )
            )
        ),
    )
    _delete_query_derived_state(session, project_id=project_id, category_id=category_id, counts=counts, delete_bootstrap_state=True)
    batch_ids = [
        int(item)
        for item in session.scalars(
            select(SeoQueryBatch.id).where(
                SeoQueryBatch.project_id == int(project_id),
                SeoQueryBatch.category_id == int(category_id),
            )
        ).all()
    ]
    if batch_ids:
        _add_count(counts, "seo_queries_raw", _count_result(session.execute(delete(SeoQueryRaw).where(SeoQueryRaw.batch_id.in_(batch_ids)))))
        _add_count(
            counts,
            "seo_queries_normalized",
            _count_result(session.execute(delete(SeoQueryNormalized).where(SeoQueryNormalized.batch_id.in_(batch_ids)))),
        )
        _add_count(counts, "seo_query_batches", _count_result(session.execute(delete(SeoQueryBatch).where(SeoQueryBatch.id.in_(batch_ids)))))
    session.flush()
    return QueryCorpusDeleteResult(
        project_id=int(project_id),
        category_id=int(category_id),
        action="clear_category",
        deleted_batch_id=None,
        deleted_counts=counts,
        preserved_judgments_count=0,
        deleted_judgments_count=int(counts.get("seo_sku_query_judgments", 0)),
        remaining_active_batches_count=0,
        remaining_unique_queries_count=0,
    )
