"""Project-scoped internal SEO query import debug endpoints."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import func, select, text

from app.db import SessionLocal
from app.deps import allow_local_debug_read, require_project_admin
from app.models import (
    SeoCategoryMeaningAxes,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryNormalized,
)
from app.schemas.seo_query_import import (
    SeoCategoryQueryClusterDetailResponse,
    SeoCategoryQueryClusterItem,
    SeoCategoryQueryClusterListResponse,
    SeoCategoryQueryClusterMemberItem,
    SeoCategoryQueryDataExpressivePrior,
    SeoCategoryQueryDataLatestBatch,
    SeoCategoryQueryDataReadiness,
    SeoCategoryQueryDataStatusResponse,
    SeoCategoryReviewArchiveCounts,
    SeoQueryCorpusResponse,
    SeoQueryCorpusSummary,
    SeoQueryDeleteResponse,
    SeoQueryImportBatchDetailResponse,
    SeoQueryImportBatchMeta,
    SeoQueryImportDiagnostics,
    SeoQueryImportNormalizedQueryItem,
    SeoQueryImportNormalizedQueryList,
    SeoQueryImportSuspiciousRowPreview,
)
from app.services.seo.query_pipeline import CsvImportError, import_queries_from_csv
from app.services.seo.query_pipeline import run_query_clustering
from app.services.seo.query_pipeline.corpus import (
    clear_query_corpus,
    delete_query_batch,
    get_query_corpus_summary,
)
from app.services.seo.category_bootstrap import create_category_bootstrap_run, get_category_bootstrap_status, run_category_bootstrap_background
from app.settings import SEO_QUERY_IMPORT_TMP_DIR


router = APIRouter(prefix="/api/v1", tags=["seo-query-import"])


def _decimal_to_response_string(value: Decimal | float | int | str | None) -> str:
    if value is None:
        return "0"
    return str(value)


def _normalize_suspicious_preview(meta: dict | None) -> list[SeoQueryImportSuspiciousRowPreview]:
    items = []
    for item in (meta or {}).get("suspicious_rows_preview", []) or []:
        if not isinstance(item, dict):
            continue
        items.append(
            SeoQueryImportSuspiciousRowPreview(
                row_number=int(item.get("row_number", 0)),
                reason=str(item.get("reason", "")),
                raw_query=item.get("raw_query"),
                payload=dict(item.get("payload") or {}),
            )
        )
    return items


def _build_batch_detail_response(
    *,
    session,
    batch: SeoQueryBatch,
    limit: int,
    offset: int,
    q: str | None,
) -> SeoQueryImportBatchDetailResponse:
    total = session.scalar(
        select(func.count()).select_from(SeoQueryNormalized).where(SeoQueryNormalized.batch_id == batch.id)
    )
    rows = session.scalars(
        select(SeoQueryNormalized)
        .where(SeoQueryNormalized.batch_id == batch.id)
        .order_by(
            SeoQueryNormalized.frequency_total.desc(),
            SeoQueryNormalized.raw_row_count.desc(),
            SeoQueryNormalized.normalized_query.asc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()

    meta = dict(batch.meta or {})
    bootstrap_meta = meta.get("category_bootstrap") if isinstance(meta.get("category_bootstrap"), dict) else {}
    query_column_resolved = meta.get("query_column_resolved")
    frequency_column_resolved = meta.get("frequency_column_resolved")
    normalization_version = meta.get("normalization_version")
    raw_rows_imported = int(batch.row_count or 0)
    raw_rows_skipped = int(meta.get("raw_rows_skipped") or 0)
    normalized_rows_created = int(batch.normalized_row_count or 0)
    duplicate_groups_collapsed = max(raw_rows_imported - normalized_rows_created, 0)
    duplicate_raw_rows_detected = int(meta.get("duplicate_raw_rows_detected") or 0)

    return SeoQueryImportBatchDetailResponse(
        batch=_batch_meta_from_batch(batch),
        diagnostics=SeoQueryImportDiagnostics(
            raw_rows_imported=raw_rows_imported,
            raw_rows_skipped=raw_rows_skipped,
            normalized_rows_created=normalized_rows_created,
            duplicate_groups_collapsed=duplicate_groups_collapsed,
            duplicate_raw_rows_detected=duplicate_raw_rows_detected,
        ),
        suspicious_rows_preview=_normalize_suspicious_preview(meta),
        normalized_queries=SeoQueryImportNormalizedQueryList(
            total=int(total or 0),
            limit=limit,
            offset=offset,
            q=q,
            items=[
                SeoQueryImportNormalizedQueryItem(
                    id=int(row.id),
                    normalized_query=row.normalized_query,
                    display_query=row.display_query,
                    raw_query_example=str((row.sample_source_payload or {}).get("raw_query") or row.display_query),
                    raw_row_count=int(row.raw_row_count or 0),
                    frequency_total=_decimal_to_response_string(row.frequency_total),
                    normalization_version=row.normalization_version,
                )
                for row in rows
            ],
        ),
        bootstrap_run_id=int(bootstrap_meta["run_id"]) if bootstrap_meta.get("run_id") else None,
        readiness_status=bootstrap_meta.get("readiness_status"),
    )


def _batch_meta_from_batch(batch: SeoQueryBatch) -> SeoQueryImportBatchMeta:
    meta = dict(batch.meta or {})
    return SeoQueryImportBatchMeta(
        batch_id=int(batch.id),
        project_id=int(batch.project_id),
        category_id=int(batch.category_id),
        status=str(batch.status),
        source_type=str(batch.source_type),
        source_path=batch.source_path,
        original_filename=batch.original_filename,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        query_column_resolved=meta.get("query_column_resolved"),
        frequency_column_resolved=meta.get("frequency_column_resolved"),
        normalization_version=meta.get("normalization_version"),
    )


def _load_batch_or_404(*, session, project_id: int, batch_id: int) -> SeoQueryBatch:
    batch = session.scalar(
        select(SeoQueryBatch).where(
            SeoQueryBatch.id == batch_id,
            SeoQueryBatch.project_id == project_id,
        )
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEO query import batch not found")
    return batch


def _load_latest_batch_or_404(*, session, project_id: int, category_id: int) -> SeoQueryBatch:
    batch = session.scalar(
        select(SeoQueryBatch)
        .where(
            SeoQueryBatch.project_id == project_id,
            SeoQueryBatch.category_id == category_id,
        )
        .order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc())
        .limit(1)
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SEO query import batch found for this project/category",
        )
    return batch


def _latest_batch(*, session, project_id: int, category_id: int) -> SeoQueryBatch | None:
    return session.scalar(
        select(SeoQueryBatch)
        .where(
            SeoQueryBatch.project_id == project_id,
            SeoQueryBatch.category_id == category_id,
        )
        .order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc())
        .limit(1)
    )


def _latest_expressive_prior(*, session, project_id: int, category_id: int) -> SeoCategoryMeaningAxes | None:
    return session.scalar(
        select(SeoCategoryMeaningAxes)
        .where(
            SeoCategoryMeaningAxes.project_id == project_id,
            SeoCategoryMeaningAxes.category_id == category_id,
            SeoCategoryMeaningAxes.status == "ready",
        )
        .order_by(SeoCategoryMeaningAxes.updated_at.desc(), SeoCategoryMeaningAxes.id.desc())
        .limit(1)
    )


def _cluster_item_from_row(
    row: SeoQueryCluster,
    *,
    top_frequency_by_cluster_id: dict[int, str],
) -> SeoCategoryQueryClusterItem:
    cluster_id = int(row.id)
    return SeoCategoryQueryClusterItem(
        cluster_id=cluster_id,
        cluster_key=str(row.cluster_key),
        label=row.label,
        top_query=row.top_query_text,
        query_count=int(row.query_count or 0),
        top_frequency=top_frequency_by_cluster_id.get(cluster_id),
    )


def _string_list_from_payload(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                result.append(cleaned)
    return result


def _confidence_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    raw_confidence = payload.get("confidence")
    if not isinstance(raw_confidence, dict):
        return {}
    confidence: dict[str, float] = {}
    for key, value in raw_confidence.items():
        try:
            confidence[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return confidence


def _expressive_prior_from_row(row: SeoCategoryMeaningAxes | None) -> SeoCategoryQueryDataExpressivePrior:
    if row is None:
        return SeoCategoryQueryDataExpressivePrior(ready=False)
    payload = row.axes_payload if isinstance(row.axes_payload, dict) else {}
    return SeoCategoryQueryDataExpressivePrior(
        ready=True,
        status=row.status,
        source=row.source,
        schema_version=row.schema_version,
        axes_id=int(row.id),
        llm_model=row.llm_model,
        prompt_version=row.prompt_version,
        updated_at=row.updated_at,
        confidence=_confidence_from_payload(payload),
        evidence_refs=_string_list_from_payload(payload, "evidence_refs"),
        expressive_axes=_string_list_from_payload(payload, "expressive_axes"),
        audience_axes=_string_list_from_payload(payload, "audience_axes"),
        occasion_axes=_string_list_from_payload(payload, "occasion_axes"),
        use_case_axes=_string_list_from_payload(payload, "use_case_axes"),
        product_type_axes=_string_list_from_payload(payload, "product_type_axes"),
        attribute_axes=_string_list_from_payload(payload, "attribute_axes"),
        constraint_axes=_string_list_from_payload(payload, "constraint_axes"),
        negative_constraint_axes=_string_list_from_payload(payload, "negative_constraint_axes"),
    )


def _review_archive_counts(*, session, project_id: int, category_id: int) -> SeoCategoryReviewArchiveCounts:
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        text_present_sql = """
            NULLIF(TRIM(COALESCE(json_extract(fs.raw, '$.text'), '')), '') IS NOT NULL
            OR NULLIF(TRIM(COALESCE(json_extract(fs.raw, '$.pros'), '')), '') IS NOT NULL
            OR NULLIF(TRIM(COALESCE(json_extract(fs.raw, '$.cons'), '')), '') IS NOT NULL
        """
    else:
        text_present_sql = """
            NULLIF(BTRIM(COALESCE(fs.raw->>'text', '')), '') IS NOT NULL
            OR NULLIF(BTRIM(COALESCE(fs.raw->>'pros', '')), '') IS NOT NULL
            OR NULLIF(BTRIM(COALESCE(fs.raw->>'cons', '')), '') IS NOT NULL
        """

    query = text(
        f"""
        SELECT
            COUNT(*) AS total_review_rows,
            SUM(CASE WHEN ({text_present_sql}) THEN 1 ELSE 0 END) AS text_review_rows,
            COUNT(DISTINCT fs.nm_id) AS sku_with_reviews,
            COUNT(DISTINCT CASE WHEN ({text_present_sql}) THEN fs.nm_id END) AS sku_with_text_reviews,
            SUM(CASE WHEN fs.product_valuation IS NOT NULL AND fs.product_valuation >= 4 THEN 1 ELSE 0 END)
                AS rating_positive_rows
        FROM wb_feedback_snapshots fs
        JOIN products p
          ON p.project_id = fs.project_id
         AND p.nm_id = fs.nm_id
        WHERE fs.project_id = :project_id
          AND p.subject_id = :category_id
        """
    )
    try:
        row = session.execute(
            query,
            {"project_id": int(project_id), "category_id": int(category_id)},
        ).mappings().one()
    except Exception:
        return SeoCategoryReviewArchiveCounts()
    return SeoCategoryReviewArchiveCounts(
        total_review_rows=int(row.get("total_review_rows") or 0),
        text_review_rows=int(row.get("text_review_rows") or 0),
        sku_with_reviews=int(row.get("sku_with_reviews") or 0),
        sku_with_text_reviews=int(row.get("sku_with_text_reviews") or 0),
        rating_positive_rows=int(row.get("rating_positive_rows") or 0),
    )


def _ensure_temp_dir() -> str:
    try:
        os.makedirs(SEO_QUERY_IMPORT_TMP_DIR, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SEO query import temp storage is not writable. "
                "Please contact administrator (check SEO_QUERY_IMPORT_TMP_DIR permissions)."
            ),
        ) from exc
    return SEO_QUERY_IMPORT_TMP_DIR


@router.get(
    "/projects/{project_id}/seo/categories/{category_id}/query-data/status",
    response_model=SeoCategoryQueryDataStatusResponse,
)
async def get_seo_category_query_data_status_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="WB category/subject scope"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        latest_batch = _latest_batch(session=session, project_id=int(project_id), category_id=int(category_id))
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
        expressive_prior = _latest_expressive_prior(
            session=session,
            project_id=int(project_id),
            category_id=int(category_id),
        )
        expressive_prior_ready = expressive_prior is not None
        latest_batch_ready = latest_batch is not None and str(latest_batch.status) == "completed"
        readiness = SeoCategoryQueryDataReadiness(
            query_data_loaded=query_count > 0 and latest_batch_ready,
            normalized_queries_ready=normalized_query_count > 0,
            clusters_ready=cluster_count > 0,
            expressive_prior_ready=expressive_prior_ready,
            ready=bool(
                query_count > 0
                and latest_batch_ready
                and normalized_query_count > 0
                and cluster_count > 0
                and expressive_prior_ready
            ),
        )
        return SeoCategoryQueryDataStatusResponse(
            project_id=int(project_id),
            category_id=int(category_id),
            query_count=query_count,
            normalized_query_count=normalized_query_count,
            cluster_count=cluster_count,
            latest_batch=SeoCategoryQueryDataLatestBatch(
                batch_id=int(latest_batch.id),
                status=str(latest_batch.status),
                original_filename=latest_batch.original_filename,
                created_at=latest_batch.created_at,
                updated_at=latest_batch.updated_at,
            )
            if latest_batch
            else None,
            expressive_prior=_expressive_prior_from_row(expressive_prior),
            review_archive=_review_archive_counts(
                session=session,
                project_id=int(project_id),
                category_id=int(category_id),
            ),
            readiness=readiness,
        )
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/categories/{category_id}/clusters",
    response_model=SeoCategoryQueryClusterListResponse,
)
async def list_seo_category_query_clusters_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="WB category/subject scope"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        total = int(
            session.scalar(
                select(func.count()).select_from(SeoQueryCluster).where(
                    SeoQueryCluster.project_id == int(project_id),
                    SeoQueryCluster.category_id == int(category_id),
                )
            )
            or 0
        )
        rows = session.scalars(
            select(SeoQueryCluster)
            .where(
                SeoQueryCluster.project_id == int(project_id),
                SeoQueryCluster.category_id == int(category_id),
            )
            .order_by(SeoQueryCluster.query_count.desc(), SeoQueryCluster.cluster_key.asc())
            .offset(offset)
            .limit(limit)
        ).all()
        cluster_ids = [int(row.id) for row in rows]
        frequency_rows = []
        if cluster_ids:
            frequency_rows = session.execute(
                select(
                    SeoQueryClusterMembership.cluster_id,
                    func.max(SeoQueryNormalized.frequency_total),
                )
                .select_from(SeoQueryClusterMembership)
                .outerjoin(
                    SeoQueryNormalized,
                    (SeoQueryNormalized.project_id == SeoQueryClusterMembership.project_id)
                    & (SeoQueryNormalized.category_id == SeoQueryClusterMembership.category_id)
                    & (SeoQueryNormalized.normalized_query == SeoQueryClusterMembership.normalized_query_text),
                )
                .where(
                    SeoQueryClusterMembership.project_id == int(project_id),
                    SeoQueryClusterMembership.category_id == int(category_id),
                    SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
                )
                .group_by(SeoQueryClusterMembership.cluster_id)
            ).all()
        top_frequency_by_cluster_id = {
            int(cluster_id): _decimal_to_response_string(ranking_value)
            for cluster_id, ranking_value in frequency_rows
        }
        return SeoCategoryQueryClusterListResponse(
            project_id=int(project_id),
            category_id=int(category_id),
            total=total,
            limit=int(limit),
            offset=int(offset),
            items=[
                _cluster_item_from_row(row, top_frequency_by_cluster_id=top_frequency_by_cluster_id)
                for row in rows
            ],
        )
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/categories/{category_id}/clusters/{cluster_id}",
    response_model=SeoCategoryQueryClusterDetailResponse,
)
async def get_seo_category_query_cluster_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="WB category/subject scope"),
    cluster_id: int = Path(..., description="SEO query cluster ID"),
    limit: int = Query(100, ge=1, le=500),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        cluster = session.scalar(
            select(SeoQueryCluster).where(
                SeoQueryCluster.id == int(cluster_id),
                SeoQueryCluster.project_id == int(project_id),
                SeoQueryCluster.category_id == int(category_id),
            )
        )
        if not cluster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SEO query cluster not found")
        member_rows = session.execute(
            select(
                SeoQueryClusterMembership.normalized_query_text,
                SeoQueryNormalized.display_query,
                SeoQueryNormalized.frequency_total,
                SeoQueryClusterMembership.ranking_value_used,
                SeoQueryClusterMembership.query_type,
                SeoQueryClusterMembership.membership_reason_code,
            )
            .outerjoin(
                SeoQueryNormalized,
                (SeoQueryNormalized.project_id == SeoQueryClusterMembership.project_id)
                & (SeoQueryNormalized.category_id == SeoQueryClusterMembership.category_id)
                & (SeoQueryNormalized.normalized_query == SeoQueryClusterMembership.normalized_query_text),
            )
            .where(
                SeoQueryClusterMembership.project_id == int(project_id),
                SeoQueryClusterMembership.category_id == int(category_id),
                SeoQueryClusterMembership.cluster_id == int(cluster_id),
            )
            .order_by(
                SeoQueryClusterMembership.ranking_value_used.desc(),
                SeoQueryClusterMembership.normalized_query_text.asc(),
            )
            .limit(limit)
        ).all()
        top_frequency = _decimal_to_response_string(member_rows[0].frequency_total) if member_rows else None
        return SeoCategoryQueryClusterDetailResponse(
            project_id=int(project_id),
            category_id=int(category_id),
            cluster=_cluster_item_from_row(
                cluster,
                top_frequency_by_cluster_id={int(cluster.id): top_frequency} if top_frequency else {},
            ),
            queries=[
                SeoCategoryQueryClusterMemberItem(
                    normalized_query_text=str(normalized_query_text),
                    display_query=display_query,
                    frequency_total=_decimal_to_response_string(frequency_total),
                    ranking_value_used=_decimal_to_response_string(ranking_value_used),
                    query_type=str(query_type),
                    membership_reason_code=str(membership_reason_code),
                )
                for (
                    normalized_query_text,
                    display_query,
                    frequency_total,
                    ranking_value_used,
                    query_type,
                    membership_reason_code,
                ) in member_rows
            ],
        )
    finally:
        session.close()


@router.post(
    "/projects/{project_id}/wildberries/seo/query-import",
    response_model=SeoQueryImportBatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_seo_query_csv_endpoint(
    background_tasks: BackgroundTasks,
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Form(..., description="WB category/subject scope"),
    file: UploadFile = File(...),
    limit: int = Form(100),
    offset: int = Form(0),
    membership: dict = Depends(require_project_admin),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    if limit < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be >= 1")
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset must be >= 0")

    temp_dir = _ensure_temp_dir()
    temp_path: str | None = None
    cleanup_error: OSError | None = None
    response_payload: SeoQueryImportBatchDetailResponse | None = None
    session = SessionLocal()
    try:
        suffix = os.path.splitext(file.filename)[1] or ".csv"
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            suffix=suffix,
            prefix=f"project_{project_id}_category_{category_id}_",
            dir=temp_dir,
        ) as temp_file:
            temp_path = temp_file.name
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                temp_file.write(chunk)
        if not temp_path or not os.path.exists(temp_path) or os.path.getsize(temp_path) <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded CSV file is empty")

        diagnostics = import_queries_from_csv(
            session,
            csv_path=temp_path,
            project_id=project_id,
            category_id=category_id,
            original_filename=file.filename,
        )
        batch = _load_batch_or_404(session=session, project_id=project_id, batch_id=diagnostics.batch_id)
        try:
            clustering_result = run_query_clustering(
                session,
                project_id=project_id,
                category_id=category_id,
                top_limit=20,
                samples_limit=20,
                persist=True,
            )
            pipeline_meta = {
                "annotations_refreshed": True,
                "clusters_created": int(clustering_result.diagnostics.total_clusters_created),
                "clustered_input_queries": int(clustering_result.diagnostics.total_input_queries),
            }
        except Exception as exc:
            pipeline_meta = {
                "annotations_refreshed": False,
                "clusters_created": 0,
                "clustered_input_queries": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        bootstrap_run_id: int | None = None
        readiness_status: str | None = None
        try:
            bootstrap_run = create_category_bootstrap_run(
                session,
                project_id=int(project_id),
                category_id=int(category_id),
                trigger="query_import",
            )
            bootstrap_run_id = int(bootstrap_run.id)
            readiness_status = "building"
        except Exception as exc:
            pipeline_meta["bootstrap_create_error"] = f"{type(exc).__name__}: {exc}"
        batch.meta = {
            **(batch.meta or {}),
            "pipeline_after_import": pipeline_meta,
            "category_bootstrap": {
                "run_id": bootstrap_run_id,
                "readiness_status": readiness_status,
                "triggered": bootstrap_run_id is not None,
            },
        }
        session.commit()
        if bootstrap_run_id is not None:
            background_tasks.add_task(
                run_category_bootstrap_background,
                int(bootstrap_run_id),
                force_refresh=True,
                use_llm=True,
            )
        response_payload = _build_batch_detail_response(session=session, batch=batch, limit=limit, offset=offset, q=None)
    except CsvImportError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import SEO query CSV: {exc!s}",
        ) from exc
    finally:
        session.close()
        await file.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError as exc:
                cleanup_error = exc
    if cleanup_error is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Imported CSV but failed to delete temporary file. "
                "Please contact administrator (check SEO_QUERY_IMPORT_TMP_DIR permissions)."
            ),
        ) from cleanup_error
    if response_payload is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build SEO query import response",
        )
    return response_payload


@router.get(
    "/projects/{project_id}/wildberries/seo/query-import/latest",
    response_model=SeoQueryImportBatchDetailResponse,
)
async def get_latest_seo_query_import_batch_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category/subject scope"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Reserved for future normalized query filtering"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        batch = _load_latest_batch_or_404(session=session, project_id=project_id, category_id=category_id)
        return _build_batch_detail_response(session=session, batch=batch, limit=limit, offset=offset, q=q)
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/wildberries/seo/query-import/corpus",
    response_model=SeoQueryCorpusResponse,
)
async def get_seo_query_import_corpus_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category/subject scope"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        summary = get_query_corpus_summary(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            limit=int(limit),
            offset=int(offset),
            q=q,
        )
        readiness = get_category_bootstrap_status(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
        )
        batches = session.scalars(
            select(SeoQueryBatch)
            .where(SeoQueryBatch.project_id == int(project_id), SeoQueryBatch.category_id == int(category_id))
            .order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc())
        ).all()
        return SeoQueryCorpusResponse(
            summary=SeoQueryCorpusSummary(
                project_id=summary.project_id,
                category_id=summary.category_id,
                active_batches_count=summary.active_batches_count,
                total_batches_count=summary.total_batches_count,
                total_raw_rows=summary.total_raw_rows,
                total_normalized_rows=summary.total_normalized_rows,
                unique_normalized_queries=summary.unique_normalized_queries,
                duplicate_across_batches_count=summary.duplicate_across_batches_count,
                latest_batch_id=summary.latest_batch_id,
                readiness_status=readiness.readiness_status,
                bootstrap_run_id=readiness.latest_run_id,
                bootstrap_run_status=readiness.run_status,
            ),
            batches=[_batch_meta_from_batch(batch) for batch in batches],
            normalized_queries=SeoQueryImportNormalizedQueryList(
                total=summary.total_matching_rows,
                limit=limit,
                offset=offset,
                q=q,
                items=[
                    SeoQueryImportNormalizedQueryItem(
                        id=item.id,
                        normalized_query=item.normalized_query,
                        display_query=item.display_query,
                        raw_query_example=item.raw_query_example,
                        raw_row_count=item.raw_row_count,
                        frequency_total=item.frequency_total,
                        normalization_version=item.normalization_version,
                    )
                    for item in summary.normalized_queries
                ],
            ),
        )
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/wildberries/seo/query-import/batches/{batch_id}",
    response_model=SeoQueryImportBatchDetailResponse,
)
async def get_seo_query_import_batch_endpoint(
    project_id: int = Path(..., description="Project ID"),
    batch_id: int = Path(..., description="SEO import batch ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Reserved for future normalized query filtering"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        batch = _load_batch_or_404(session=session, project_id=project_id, batch_id=batch_id)
        return _build_batch_detail_response(session=session, batch=batch, limit=limit, offset=offset, q=q)
    finally:
        session.close()


@router.delete(
    "/projects/{project_id}/wildberries/seo/query-import/batches/{batch_id}",
    response_model=SeoQueryDeleteResponse,
)
async def delete_seo_query_import_batch_endpoint(
    background_tasks: BackgroundTasks,
    project_id: int = Path(..., description="Project ID"),
    batch_id: int = Path(..., description="SEO import batch ID"),
    membership: dict = Depends(require_project_admin),
):
    del membership
    session = SessionLocal()
    bootstrap_run_id: int | None = None
    try:
        try:
            result = delete_query_batch(session, project_id=int(project_id), batch_id=int(batch_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        if result.remaining_active_batches_count > 0:
            try:
                run_query_clustering(
                    session,
                    project_id=int(project_id),
                    category_id=int(result.category_id),
                    top_limit=20,
                    samples_limit=20,
                    persist=True,
                )
            except Exception:
                # Bootstrap will retry the full query pipeline in background.
                pass
            bootstrap_run = create_category_bootstrap_run(
                session,
                project_id=int(project_id),
                category_id=int(result.category_id),
                trigger="query_import",
            )
            bootstrap_run_id = int(bootstrap_run.id)
            readiness_status = "building"
        else:
            readiness_status = "not_started"

        session.commit()
        if bootstrap_run_id is not None:
            background_tasks.add_task(
                run_category_bootstrap_background,
                int(bootstrap_run_id),
                force_refresh=True,
                use_llm=True,
            )
        return SeoQueryDeleteResponse(
            project_id=result.project_id,
            category_id=result.category_id,
            deleted_batch_id=result.deleted_batch_id,
            action=result.action,
            deleted_counts=result.deleted_counts,
            preserved_judgments_count=result.preserved_judgments_count,
            deleted_judgments_count=result.deleted_judgments_count,
            remaining_active_batches_count=result.remaining_active_batches_count,
            remaining_unique_queries_count=result.remaining_unique_queries_count,
            bootstrap_run_id=bootstrap_run_id,
            readiness_status=readiness_status,
        )
    except HTTPException:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete SEO query import batch: {exc!s}",
        ) from exc
    finally:
        session.close()


@router.delete(
    "/projects/{project_id}/wildberries/seo/query-import/category",
    response_model=SeoQueryDeleteResponse,
)
async def clear_seo_query_import_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category/subject scope"),
    membership: dict = Depends(require_project_admin),
):
    del membership
    session = SessionLocal()
    try:
        result = clear_query_corpus(session, project_id=int(project_id), category_id=int(category_id))
        session.commit()
        return SeoQueryDeleteResponse(
            project_id=result.project_id,
            category_id=result.category_id,
            deleted_batch_id=result.deleted_batch_id,
            action=result.action,
            deleted_counts=result.deleted_counts,
            preserved_judgments_count=result.preserved_judgments_count,
            deleted_judgments_count=result.deleted_judgments_count,
            remaining_active_batches_count=result.remaining_active_batches_count,
            remaining_unique_queries_count=result.remaining_unique_queries_count,
            bootstrap_run_id=None,
            readiness_status="not_started",
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear SEO query corpus: {exc!s}",
        ) from exc
    finally:
        session.close()
