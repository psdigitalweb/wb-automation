"""Project-scoped internal SEO query import debug endpoints."""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import func, select

from app.db import SessionLocal
from app.deps import allow_local_debug_read, require_project_admin
from app.models import SeoQueryBatch, SeoQueryNormalized
from app.schemas.seo_query_import import (
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
