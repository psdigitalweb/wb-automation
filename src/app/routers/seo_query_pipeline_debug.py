"""Project-scoped internal SEO query pipeline debug endpoint."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoQueryAnnotation, SeoQueryCluster, SeoQueryClusterMembership
from app.schemas.seo_query_pipeline_debug import (
    SeoQueryPipelineActualScoringDiagnostics,
    SeoQueryPipelineActualScoringItem,
    SeoQueryPipelineClusterItem,
    SeoQueryPipelineClusterMemberItem,
    SeoQueryPipelineHybridClusterDetailItem,
    SeoQueryPipelineHybridClusterMemberItem,
    SeoQueryPipelineDebugResponse,
    SeoQueryPipelineHybridDiagnostics,
    SeoQueryPipelineHybridItem,
    SeoQueryPipelineDiagnosticsSummary,
    SeoQueryPipelinePagination,
    SeoQueryPipelineProfileItem,
    SeoQueryPipelineProfilesDiagnostics,
    SeoQueryPipelineQueryItem,
    SeoQueryPipelineScoringPrepDiagnostics,
    SeoQueryPipelineScoringPrepItem,
)
from app.services.seo.query_pipeline import (
    DEFAULT_GATING_STRATEGY,
    get_persisted_pruning_overlay,
    run_query_profile_extraction,
)
from app.services.seo.scoring.preparation import (
    QueryScoringPreparationNotFoundError,
    QueryScoringPreparationScopeError,
    run_query_scoring_preparation,
)
from app.services.seo.scoring.actual import run_query_actual_scoring
from app.services.seo.query_pipeline.hybrid import run_query_hybrid_annotation
from app.services.seo.query_pipeline.audit import run_query_pipeline_audit
from app.services.seo.query_pipeline.pruning import AnnotatedCanonicalQueryRow
from app.services.seo.query_pipeline.semantic import run_semantic_clustering_experiment
from app.services.seo.query_pipeline.unified_dataset import _decimal_to_string


router = APIRouter(prefix="/api/v1", tags=["seo-query-pipeline-debug"])

_PRUNING_STATUS_VALUES = ("keep", "drop", "review")
_HYBRID_PROVENANCE_VALUES = ("individual", "cluster", "rejected", "fallback")


def _paginate(*, page: int, page_size: int, total_count: int) -> SeoQueryPipelinePagination:
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    safe_page = 1 if total_pages == 0 else min(max(page, 1), total_pages)
    return SeoQueryPipelinePagination(
        page=safe_page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
    )


def _sorted_query_rows(
    *,
    keep_rows: list[AnnotatedCanonicalQueryRow],
    drop_rows: list[AnnotatedCanonicalQueryRow],
    review_rows: list[AnnotatedCanonicalQueryRow],
) -> list[AnnotatedCanonicalQueryRow]:
    combined_rows = [*keep_rows, *drop_rows, *review_rows]
    combined_rows.sort(
        key=lambda row: (
            -float(row.ranking_value_used),
            row.normalized_query_text,
        )
    )
    return combined_rows


def _normalize_status_filters(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set(_PRUNING_STATUS_VALUES)
    selected = {
        item.strip()
        for item in raw_value.split(",")
        if item.strip() in _PRUNING_STATUS_VALUES
    }
    return selected or set(_PRUNING_STATUS_VALUES)


def _normalize_hybrid_provenance_filters(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set(_HYBRID_PROVENANCE_VALUES)
    selected = {
        item.strip()
        for item in raw_value.split(",")
        if item.strip() in _HYBRID_PROVENANCE_VALUES
    }
    return selected or set(_HYBRID_PROVENANCE_VALUES)


def _filter_query_rows(
    rows: list[AnnotatedCanonicalQueryRow],
    *,
    statuses: set[str],
    bucket: str,
    intent: str,
    search: str | None,
) -> list[AnnotatedCanonicalQueryRow]:
    normalized_search = (search or "").strip().lower()
    filtered: list[AnnotatedCanonicalQueryRow] = []
    for row in rows:
        if row.pruning_status not in statuses:
            continue
        if bucket != "all" and row.query_type != bucket:
            continue
        if intent != "all" and row.intent_type != intent:
            continue
        if normalized_search and normalized_search not in row.normalized_query_text.lower():
            continue
        filtered.append(row)
    return filtered


def _query_items_for_page(
    session,
    *,
    project_id: int,
    category_id: int,
    rows: list[AnnotatedCanonicalQueryRow],
) -> list[SeoQueryPipelineQueryItem]:
    if not rows:
        return []

    query_texts = [row.normalized_query_text for row in rows]
    membership_rows = session.execute(
        select(
            SeoQueryClusterMembership.normalized_query_text,
            SeoQueryCluster.cluster_key,
            SeoQueryCluster.label,
            SeoQueryCluster.top_query_text,
        )
        .join(SeoQueryCluster, SeoQueryCluster.id == SeoQueryClusterMembership.cluster_id)
        .where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
            SeoQueryClusterMembership.normalized_query_text.in_(query_texts),
        )
    ).all()

    cluster_lookup = {
        str(normalized_query_text): {
            "cluster_key": str(cluster_key),
            "cluster_label_candidate": str(label or top_query_text or cluster_key),
        }
        for normalized_query_text, cluster_key, label, top_query_text in membership_rows
    }

    return [
        SeoQueryPipelineQueryItem(
            normalized_query_text=row.normalized_query_text,
            ranking_value_used=_decimal_to_string(row.ranking_value_used),
            bucket=row.query_type,
            pruning_status=row.pruning_status,
            intent_type=row.intent_type,
            cluster_key=cluster_lookup.get(row.normalized_query_text, {}).get("cluster_key"),
            cluster_label_candidate=cluster_lookup.get(row.normalized_query_text, {}).get("cluster_label_candidate"),
        )
        for row in rows
    ]


def _cluster_items_for_page(
    session,
    *,
    project_id: int,
    category_id: int,
    page: int,
    page_size: int,
) -> tuple[list[SeoQueryPipelineClusterItem], SeoQueryPipelinePagination, int]:
    total_count = int(
        session.execute(
            select(func.count()).select_from(SeoQueryCluster).where(
                SeoQueryCluster.project_id == project_id,
                SeoQueryCluster.category_id == category_id,
            )
        ).scalar_one()
    )
    pagination = _paginate(page=page, page_size=page_size, total_count=total_count)
    if total_count == 0:
        return [], pagination, 0

    offset = (pagination.page - 1) * page_size
    cluster_rows = session.scalars(
        select(SeoQueryCluster)
        .where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
        )
        .order_by(SeoQueryCluster.query_count.desc(), SeoQueryCluster.cluster_key.asc())
        .offset(offset)
        .limit(page_size)
    ).all()
    cluster_ids = [int(row.id) for row in cluster_rows]
    if not cluster_ids:
        return [], pagination, 0

    singleton_cluster_count = int(
        session.execute(
            select(func.count()).select_from(SeoQueryCluster).where(
                SeoQueryCluster.project_id == project_id,
                SeoQueryCluster.category_id == category_id,
                SeoQueryCluster.query_count == 1,
            )
        ).scalar_one()
    )

    membership_rows = session.execute(
        select(
            SeoQueryClusterMembership.cluster_id,
            SeoQueryClusterMembership.normalized_query_text,
            SeoQueryClusterMembership.query_type,
            SeoQueryClusterMembership.ranking_value_used,
            SeoQueryClusterMembership.membership_reason_code,
            SeoQueryAnnotation.intent_type,
        )
        .join(SeoQueryAnnotation, SeoQueryAnnotation.id == SeoQueryClusterMembership.annotation_id)
        .where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
            SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
        )
        .order_by(
            SeoQueryClusterMembership.cluster_id.asc(),
            SeoQueryClusterMembership.ranking_value_used.desc(),
            SeoQueryClusterMembership.normalized_query_text.asc(),
        )
    ).all()

    members_by_cluster_id: dict[int, list[SeoQueryPipelineClusterMemberItem]] = defaultdict(list)
    for cluster_id, normalized_query_text, query_type, ranking_value_used, membership_reason_code, intent_type in membership_rows:
        members_by_cluster_id[int(cluster_id)].append(
            SeoQueryPipelineClusterMemberItem(
                normalized_query_text=str(normalized_query_text),
                bucket=str(query_type),
                ranking_value_used=_decimal_to_string(ranking_value_used),
                intent_type=str(intent_type or "unknown"),
                membership_reason_code=str(membership_reason_code),
            )
        )

    items = [
        SeoQueryPipelineClusterItem(
            cluster_key=str(cluster_row.cluster_key),
            cluster_label_candidate=str(cluster_row.label or cluster_row.top_query_text or cluster_row.cluster_key),
            query_count=int(cluster_row.query_count or 0),
            head_query_count=int(cluster_row.head_query_count or 0),
            mid_query_count=int(cluster_row.mid_query_count or 0),
            tail_query_count=int(cluster_row.tail_query_count or 0),
            members=members_by_cluster_id.get(int(cluster_row.id), []),
        )
        for cluster_row in cluster_rows
    ]
    return items, pagination, singleton_cluster_count


def _filter_hybrid_rows(
    rows,
    *,
    provenances: set[str],
    bucket: str,
    cluster_key: str | None,
    only_anchors: bool,
    only_fallback: bool,
):
    normalized_cluster_key = (cluster_key or "").strip()
    filtered = []
    for row in rows:
        if row.provenance not in provenances:
            continue
        is_anchor = row.provenance in {"individual", "fallback"}
        if only_fallback and row.provenance != "fallback":
            continue
        if only_anchors and not is_anchor:
            continue
        if bucket != "all" and row.query_type != bucket:
            continue
        if normalized_cluster_key and row.source_cluster_key != normalized_cluster_key:
            continue
        filtered.append(row)
    return filtered


def _hybrid_items_for_page(rows, *, cluster_meta_by_key: dict[str, dict]) -> list[SeoQueryPipelineHybridItem]:
    return [
        SeoQueryPipelineHybridItem(
            normalized_query_text=row.normalized_query_text,
            ranking_value_used=_decimal_to_string(row.ranking_value_used),
            bucket=row.query_type,
            cluster_key=row.source_cluster_key,
            is_anchor=row.provenance in {"individual", "fallback"},
            cluster_label_candidate=(cluster_meta_by_key.get(row.source_cluster_key or "", {}) or {}).get("cluster_label_candidate"),
            cluster_query_count=(cluster_meta_by_key.get(row.source_cluster_key or "", {}) or {}).get("query_count"),
            provenance=row.provenance,
            source_anchor_query=row.source_anchor_query,
            intent_type=row.intent_type,
            inheritance_reason_code=row.inheritance_reason_code,
        )
        for row in rows
    ]


def _hybrid_cluster_details_for_page(
    session,
    *,
    project_id: int,
    category_id: int,
    page_rows,
    all_rows,
) -> tuple[list[SeoQueryPipelineHybridClusterDetailItem], dict[str, dict]]:
    cluster_keys = sorted({str(row.source_cluster_key) for row in page_rows if row.source_cluster_key})
    if not cluster_keys:
        return [], {}

    cluster_rows = session.scalars(
        select(SeoQueryCluster).where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
            SeoQueryCluster.cluster_key.in_(cluster_keys),
        )
    ).all()
    cluster_id_to_key = {int(cluster_row.id): str(cluster_row.cluster_key) for cluster_row in cluster_rows}
    cluster_meta_by_key = {
        str(cluster_row.cluster_key): {
            "cluster_label_candidate": str(cluster_row.label or cluster_row.top_query_text or cluster_row.cluster_key),
            "query_count": max(int(cluster_row.query_count or 0), 0),
        }
        for cluster_row in cluster_rows
    }
    if not cluster_id_to_key:
        return [], cluster_meta_by_key

    hybrid_row_by_query = {row.normalized_query_text: row for row in all_rows}
    membership_rows = session.execute(
        select(
            SeoQueryClusterMembership.cluster_id,
            SeoQueryClusterMembership.normalized_query_text,
            SeoQueryClusterMembership.ranking_value_used,
        )
        .where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
            SeoQueryClusterMembership.cluster_id.in_(list(cluster_id_to_key.keys())),
        )
        .order_by(
            SeoQueryClusterMembership.cluster_id.asc(),
            SeoQueryClusterMembership.ranking_value_used.desc(),
            SeoQueryClusterMembership.normalized_query_text.asc(),
        )
    ).all()

    members_by_cluster_key: dict[str, list[SeoQueryPipelineHybridClusterMemberItem]] = defaultdict(list)
    anchor_query_by_cluster_key: dict[str, str] = {}
    for cluster_id, normalized_query_text, _ranking_value_used in membership_rows:
        cluster_key = cluster_id_to_key.get(int(cluster_id))
        if not cluster_key:
            continue
        hybrid_row = hybrid_row_by_query.get(str(normalized_query_text))
        if hybrid_row is None:
            continue
        if hybrid_row.provenance in {"individual", "fallback"} and cluster_key not in anchor_query_by_cluster_key:
            anchor_query_by_cluster_key[cluster_key] = hybrid_row.normalized_query_text
        members_by_cluster_key[cluster_key].append(
            SeoQueryPipelineHybridClusterMemberItem(
                normalized_query_text=hybrid_row.normalized_query_text,
                bucket=hybrid_row.query_type,
                is_anchor=hybrid_row.provenance in {"individual", "fallback"},
                provenance=hybrid_row.provenance,
                source_anchor_query=hybrid_row.source_anchor_query,
                intent_type=hybrid_row.intent_type,
                inheritance_reason_code=hybrid_row.inheritance_reason_code,
            )
        )

    details = [
        SeoQueryPipelineHybridClusterDetailItem(
            cluster_key=cluster_key,
            cluster_label_candidate=(cluster_meta_by_key.get(cluster_key, {}) or {}).get("cluster_label_candidate") or cluster_key,
            query_count=(cluster_meta_by_key.get(cluster_key, {}) or {}).get("query_count") or len(members_by_cluster_key.get(cluster_key, [])),
            anchor_query=anchor_query_by_cluster_key.get(cluster_key),
            members=members_by_cluster_key.get(cluster_key, []),
        )
        for cluster_key in cluster_keys
    ]
    return details, cluster_meta_by_key


@router.get(
    "/projects/{project_id}/seo/query-pipeline/debug",
    response_model=SeoQueryPipelineDebugResponse,
)
async def get_seo_query_pipeline_debug_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category/subject scope"),
    tab: Literal["queries", "clusters", "audit", "compare", "hybrid", "profiles", "scoring_prep", "scoring"] = Query("queries"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    nm_id: int | None = Query(None, description="Target nm_id for scoring/scoring preparation tabs"),
    pruning_statuses: str | None = Query(None, description="Comma-separated keep/drop/review filters"),
    bucket: Literal["all", "head", "mid", "tail"] = Query("all"),
    intent: str = Query("all"),
    search: str | None = Query(None),
    hybrid_provenances: str | None = Query(None, description="Comma-separated individual/cluster/rejected/fallback filters"),
    hybrid_bucket: Literal["all", "head", "mid", "tail"] = Query("all"),
    hybrid_cluster_key: str | None = Query(None, description="Exact cluster_key filter for hybrid rows"),
    hybrid_only_anchors: bool = Query(False),
    hybrid_only_fallback: bool = Query(False),
    strategy: str = Query(DEFAULT_GATING_STRATEGY),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    session = SessionLocal()
    try:
        overlay_rows = get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
        keep_rows = [row for row in overlay_rows if row.pruning_status == "keep"]
        drop_rows = [row for row in overlay_rows if row.pruning_status == "drop"]
        review_rows = [row for row in overlay_rows if row.pruning_status == "review"]
        all_rows = _sorted_query_rows(keep_rows=keep_rows, drop_rows=drop_rows, review_rows=review_rows)
        audit_payload: dict = {}
        compare_payload: dict = {}
        statuses = _normalize_status_filters(pruning_statuses)
        filtered_rows = _filter_query_rows(
            all_rows,
            statuses=statuses,
            bucket=bucket,
            intent=intent,
            search=search,
        )
        queries_pagination = _paginate(page=page, page_size=page_size, total_count=len(filtered_rows))
        hybrid_pagination = _paginate(page=page, page_size=page_size, total_count=0)
        profiles_pagination = _paginate(page=page, page_size=page_size, total_count=0)
        scoring_prep_pagination = _paginate(page=page, page_size=page_size, total_count=0)
        actual_scoring_pagination = _paginate(page=page, page_size=page_size, total_count=0)

        singleton_clusters = int(
            session.execute(
                select(func.count()).select_from(SeoQueryCluster).where(
                    SeoQueryCluster.project_id == project_id,
                    SeoQueryCluster.category_id == category_id,
                    SeoQueryCluster.query_count == 1,
                )
            ).scalar_one()
        )
        total_clusters = int(
            session.execute(
                select(func.count()).select_from(SeoQueryCluster).where(
                    SeoQueryCluster.project_id == project_id,
                    SeoQueryCluster.category_id == category_id,
                )
            ).scalar_one()
        )

        query_items: list[SeoQueryPipelineQueryItem] = []
        cluster_items: list[SeoQueryPipelineClusterItem] = []
        hybrid_items: list[SeoQueryPipelineHybridItem] = []
        hybrid_cluster_details: list[SeoQueryPipelineHybridClusterDetailItem] = []
        profile_items: list[SeoQueryPipelineProfileItem] = []
        scoring_prep_items: list[SeoQueryPipelineScoringPrepItem] = []
        actual_scoring_items: list[SeoQueryPipelineActualScoringItem] = []
        hybrid_diagnostics = SeoQueryPipelineHybridDiagnostics(
            total_queries_processed=0,
            individual_count=0,
            cluster_derived_count=0,
            rejected_count=0,
            fallback_count=0,
        )
        profiles_diagnostics = SeoQueryPipelineProfilesDiagnostics(
            total_profiles_built=0,
            strong_profiles_count=0,
            medium_profiles_count=0,
            weak_profiles_count=0,
            empty_profiles_count=0,
        )
        scoring_prep_diagnostics = SeoQueryPipelineScoringPrepDiagnostics(
            project_id=project_id,
            category_id=category_id,
            nm_id=int(nm_id or 0),
        )
        actual_scoring_diagnostics = SeoQueryPipelineActualScoringDiagnostics(
            project_id=project_id,
            category_id=category_id,
            nm_id=int(nm_id or 0),
        )
        clusters_pagination = _paginate(page=page, page_size=page_size, total_count=total_clusters)

        if tab == "queries":
            offset = (queries_pagination.page - 1) * page_size
            query_page_rows = filtered_rows[offset : offset + page_size]
            query_items = _query_items_for_page(
                session,
                project_id=project_id,
                category_id=category_id,
                rows=query_page_rows,
            )
        elif tab == "clusters":
            cluster_items, clusters_pagination, singleton_clusters = _cluster_items_for_page(
                session,
                project_id=project_id,
                category_id=category_id,
                page=page,
                page_size=page_size,
            )
        elif tab == "audit":
            audit_payload = run_query_pipeline_audit(
                session,
                project_id=project_id,
                category_id=category_id,
                overlay_rows=overlay_rows,
            ).to_dict()
        elif tab == "compare":
            compare_payload = run_semantic_clustering_experiment(
                session,
                project_id=project_id,
                category_id=category_id,
                strategy=strategy,
                top_limit=20,
                samples_limit=20,
            ).to_debug_payload()
        elif tab == "hybrid":
            hybrid_result = run_query_hybrid_annotation(
                session,
                project_id=project_id,
                category_id=category_id,
                top_limit=max(page_size, 20),
                samples_limit=max(page_size, 20),
                persist=True,
            )
            overlay_rows = get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
            keep_rows = [row for row in overlay_rows if row.pruning_status == "keep"]
            drop_rows = [row for row in overlay_rows if row.pruning_status == "drop"]
            review_rows = [row for row in overlay_rows if row.pruning_status == "review"]
            all_rows = _sorted_query_rows(keep_rows=keep_rows, drop_rows=drop_rows, review_rows=review_rows)
            singleton_clusters = int(
                session.execute(
                    select(func.count()).select_from(SeoQueryCluster).where(
                        SeoQueryCluster.project_id == project_id,
                        SeoQueryCluster.category_id == category_id,
                        SeoQueryCluster.query_count == 1,
                    )
                ).scalar_one()
            )
            total_clusters = int(
                session.execute(
                    select(func.count()).select_from(SeoQueryCluster).where(
                        SeoQueryCluster.project_id == project_id,
                        SeoQueryCluster.category_id == category_id,
                    )
                ).scalar_one()
            )
            hybrid_provenance_filters = _normalize_hybrid_provenance_filters(hybrid_provenances)
            filtered_hybrid_rows = _filter_hybrid_rows(
                hybrid_result.annotated_queries,
                provenances=hybrid_provenance_filters,
                bucket=hybrid_bucket,
                cluster_key=hybrid_cluster_key,
                only_anchors=hybrid_only_anchors,
                only_fallback=hybrid_only_fallback,
            )
            hybrid_pagination = _paginate(page=page, page_size=page_size, total_count=len(filtered_hybrid_rows))
            offset = (hybrid_pagination.page - 1) * page_size
            hybrid_page_rows = filtered_hybrid_rows[offset : offset + page_size]
            hybrid_cluster_details, cluster_meta_by_key = _hybrid_cluster_details_for_page(
                session,
                project_id=project_id,
                category_id=category_id,
                page_rows=hybrid_page_rows,
                all_rows=hybrid_result.annotated_queries,
            )
            hybrid_items = _hybrid_items_for_page(hybrid_page_rows, cluster_meta_by_key=cluster_meta_by_key)
            hybrid_diagnostics = SeoQueryPipelineHybridDiagnostics.model_validate(hybrid_result.diagnostics.to_dict())
        else:
            if tab == "profiles":
                profile_result = run_query_profile_extraction(
                    session,
                    project_id=project_id,
                    category_id=category_id,
                    top_limit=max(page_size, 20),
                    samples_limit=max(page_size, 20),
                    refresh_hybrid=True,
                    persist=False,
                )
                profiles_pagination = _paginate(
                    page=page,
                    page_size=page_size,
                    total_count=len(profile_result.profiles),
                )
                offset = (profiles_pagination.page - 1) * page_size
                profile_page_rows = profile_result.profiles[offset : offset + page_size]
                profile_items = [
                    SeoQueryPipelineProfileItem.model_validate(profile.to_dict())
                    for profile in profile_page_rows
                ]
                profiles_diagnostics = SeoQueryPipelineProfilesDiagnostics.model_validate(
                    profile_result.diagnostics.to_dict()
                )
            elif tab == "scoring_prep":
                if nm_id is None:
                    raise HTTPException(status_code=400, detail="nm_id is required for scoring_prep tab")
                try:
                    scoring_prep_result = run_query_scoring_preparation(
                        session,
                        project_id=project_id,
                        category_id=category_id,
                        nm_id=int(nm_id),
                        top_limit=max(page_size, 20),
                        samples_limit=max(page_size, 20),
                        refresh_hybrid=True,
                    )
                except QueryScoringPreparationNotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except QueryScoringPreparationScopeError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

                scoring_prep_pagination = _paginate(
                    page=page,
                    page_size=page_size,
                    total_count=len(scoring_prep_result.preparations),
                )
                offset = (scoring_prep_pagination.page - 1) * page_size
                scoring_prep_page_rows = scoring_prep_result.preparations[offset : offset + page_size]
                scoring_prep_items = [
                    SeoQueryPipelineScoringPrepItem.model_validate(item.to_dict())
                    for item in scoring_prep_page_rows
                ]
                scoring_prep_diagnostics = SeoQueryPipelineScoringPrepDiagnostics.model_validate(
                    scoring_prep_result.diagnostics.to_dict()
                )
            else:
                if nm_id is None:
                    raise HTTPException(status_code=400, detail="nm_id is required for scoring tab")
                try:
                    actual_scoring_result = run_query_actual_scoring(
                        session,
                        project_id=project_id,
                        category_id=category_id,
                        nm_id=int(nm_id),
                        top_limit=max(page_size, 20),
                    )
                except QueryScoringPreparationNotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except QueryScoringPreparationScopeError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

                actual_scoring_pagination = _paginate(
                    page=page,
                    page_size=page_size,
                    total_count=len(actual_scoring_result.scores),
                )
                offset = (actual_scoring_pagination.page - 1) * page_size
                actual_score_page_rows = actual_scoring_result.scores[offset : offset + page_size]
                actual_scoring_items = [
                    SeoQueryPipelineActualScoringItem.model_validate(item.to_dict())
                    for item in actual_score_page_rows
                ]
                actual_scoring_diagnostics = SeoQueryPipelineActualScoringDiagnostics.model_validate(
                    actual_scoring_result.diagnostics.to_dict()
                )

        return SeoQueryPipelineDebugResponse(
            project_id=project_id,
            category_id=category_id,
            diagnostics=SeoQueryPipelineDiagnosticsSummary(
                total_queries=len(all_rows),
                keep_count=len(keep_rows),
                drop_count=len(drop_rows),
                review_count=len(review_rows),
                total_clusters=total_clusters,
                singleton_clusters=singleton_clusters,
            ),
            audit=audit_payload,
            compare=compare_payload,
            hybrid_diagnostics=hybrid_diagnostics,
            profiles_diagnostics=profiles_diagnostics,
            scoring_prep_diagnostics=scoring_prep_diagnostics,
            actual_scoring_diagnostics=actual_scoring_diagnostics,
            queries_pagination=queries_pagination,
            clusters_pagination=clusters_pagination,
            hybrid_pagination=hybrid_pagination,
            profiles_pagination=profiles_pagination,
            scoring_prep_pagination=scoring_prep_pagination,
            actual_scoring_pagination=actual_scoring_pagination,
            queries=query_items,
            clusters=cluster_items,
            hybrid=hybrid_items,
            hybrid_cluster_details=hybrid_cluster_details,
            profiles=profile_items,
            scoring_preparations=scoring_prep_items,
            actual_scores=actual_scoring_items,
        )
    finally:
        session.close()
