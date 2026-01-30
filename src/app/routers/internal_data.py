"""Router for project-scoped Internal Data settings and sync."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.db_internal_data import (
    get_internal_data_settings,
    upsert_internal_data_settings,
    list_internal_data_row_errors,
    list_internal_products,
    create_internal_category,
    get_internal_category,
    get_internal_category_by_key,
    list_internal_categories,
    update_internal_category,
    delete_internal_category,
    set_internal_product_category,
    upsert_internal_categories_tree,
    bulk_set_internal_product_categories,
)
from app.schemas.internal_data import (
    InternalDataSettingsResponse,
    InternalDataSettingsUpdate,
    InternalDataSyncRequest,
    InternalDataSyncResponse,
    InternalDataTestUrlRequest,
    InternalDataTestUrlResponse,
    InternalDataUploadResponse,
    InternalDataIntrospectResponse,
    InternalDataValidateMappingRequest,
    InternalDataValidateMappingResponse,
    InternalDataRowErrorsResponse,
    InternalDataProductsResponse,
    InternalCategoryOut,
    InternalCategoryCreate,
    InternalCategoryUpdate,
    InternalCategoryListOut,
    InternalProductCategorySet,
    ImportXmlMapping,
    ImportXmlMappingCategories,
    ImportXmlMappingProducts,
    CategoryImportResult,
    CategoryImportIntrospectResponse,
)
from app.services.internal_data.service import (
    get_or_create_settings,
    sync_now,
    test_url_for_project,
    introspect_source_for_project,
    validate_mapping_for_project,
)


router = APIRouter(prefix="/api/v1", tags=["internal-data"])
logger = logging.getLogger(__name__)


def _settings_to_response(project_id: int, settings: Optional[dict]) -> InternalDataSettingsResponse:
    if not settings:
        return InternalDataSettingsResponse(
            project_id=project_id,
            is_enabled=False,
            source_mode=None,
            source_url=None,
            file_storage_key=None,
            file_original_name=None,
            file_format=None,
            mapping_json={},
            last_sync_at=None,
            last_sync_status=None,
            last_sync_error=None,
            last_test_at=None,
            last_test_status=None,
        )
    return InternalDataSettingsResponse(
        project_id=project_id,
        is_enabled=bool(settings.get("is_enabled")),
        source_mode=settings.get("source_mode"),
        source_url=settings.get("source_url"),
        file_storage_key=settings.get("file_storage_key"),
        file_original_name=settings.get("file_original_name"),
        file_format=settings.get("file_format"),
        mapping_json=settings.get("mapping_json") or {},
        last_sync_at=settings.get("last_sync_at"),
        last_sync_status=settings.get("last_sync_status"),
        last_sync_error=settings.get("last_sync_error"),
        last_test_at=settings.get("last_test_at"),
        last_test_status=settings.get("last_test_status"),
    )


@router.get(
    "/projects/{project_id}/internal-data/settings",
    response_model=InternalDataSettingsResponse,
)
async def get_internal_data_settings_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get Internal Data settings for a project (never 404)."""
    settings = get_internal_data_settings(project_id)
    if not settings:
        settings = None
    return _settings_to_response(project_id, settings)


@router.put(
    "/projects/{project_id}/internal-data/settings",
    response_model=InternalDataSettingsResponse,
)
async def update_internal_data_settings_endpoint(
    body: InternalDataSettingsUpdate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Update Internal Data settings for a project."""
    # Debug-mode instrumentation: log entry with key fields.
    try:  # pragma: no cover - debug logging
        import json, time

        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "settings-put",
                        "hypothesisId": "B1",
                        "location": "routers.internal_data:update_settings:entry",
                        "message": "Update settings entry",
                        "data": {
                            "project_id": project_id,
                            "is_enabled": body.is_enabled,
                            "source_mode": body.source_mode,
                            "has_source_url": bool(body.source_url),
                            "has_mapping_json": body.mapping_json is not None,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass

    source_mode = body.source_mode
    if source_mode not in (None, "url", "upload"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_mode must be 'url', 'upload', or null",
        )
    if source_mode == "url":
        if not body.source_url or not body.source_url.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_url is required for URL mode",
            )
    settings = upsert_internal_data_settings(
        project_id,
        source_mode=source_mode,
        source_url=body.source_url.strip() if body.source_url else None,
        file_storage_key=None if source_mode == "url" else None,
        file_original_name=None if source_mode == "url" else None,
        file_format=(body.file_format or None),
        is_enabled=body.is_enabled,
        mapping_json=body.mapping_json or {},
    )
    try:  # pragma: no cover - debug logging
        import json, time

        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "settings-put",
                        "hypothesisId": "B2",
                        "location": "routers.internal_data:update_settings:exit",
                        "message": "Update settings exit",
                        "data": {
                            "project_id": project_id,
                            "source_mode": settings.get("source_mode"),
                            "file_format": settings.get("file_format"),
                            "mapping_json_keys": list((settings.get("mapping_json") or {}).keys()),
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    return _settings_to_response(project_id, settings)


@router.post(
    "/projects/{project_id}/internal-data/upload",
    response_model=InternalDataUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_internal_data_file_endpoint(
    project_id: int = Path(..., description="Project ID"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Upload Internal Data file for a project."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    from app.settings import INTERNAL_DATA_DIR
    import os
    import time

    started = time.perf_counter()
    try:
        os.makedirs(INTERNAL_DATA_DIR, exist_ok=True)
    except PermissionError as exc:
        logger.error(
            "[Internal Data upload] cannot create base dir: INTERNAL_DATA_DIR=%s error=%s",
            INTERNAL_DATA_DIR,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload storage is not writable. Please contact administrator (check INTERNAL_DATA_DIR volume/permissions).",
        ) from exc

    from datetime import datetime

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    _, dot, suffix = file.filename.rpartition(".")
    ext = suffix.lower() if dot and suffix else ""
    storage_key = f"project_{project_id}/internal_{ts}"
    if ext:
        storage_key += f".{ext}"

    dest_path = os.path.join(INTERNAL_DATA_DIR, storage_key)
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    except PermissionError as exc:
        logger.error(
            "[Internal Data upload] cannot create dest dir: dest_path=%s error=%s",
            dest_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload storage is not writable. Please contact administrator (check INTERNAL_DATA_DIR volume/permissions).",
        ) from exc

    total_bytes = 0
    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                f.write(chunk)
    except PermissionError as exc:
        logger.error(
            "[Internal Data upload] permission error while writing: dest_path=%s bytes=%s error=%s",
            dest_path,
            total_bytes,
            exc,
            exc_info=True,
        )
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file (permission denied). Please contact administrator.",
        ) from exc
    except OSError as exc:
        logger.error(
            "[Internal Data upload] os error while writing: dest_path=%s bytes=%s error=%s",
            dest_path,
            total_bytes,
            exc,
            exc_info=True,
        )
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file. Please contact administrator.",
        ) from exc

    if total_bytes <= 0:
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    file_format = ext or None
    settings = upsert_internal_data_settings(
        project_id,
        source_mode="upload",
        source_url=None,
        file_storage_key=storage_key,
        file_original_name=file.filename,
        file_format=file_format,
        is_enabled=True,
    )

    uploaded_at = datetime.utcnow()
    duration_s = time.perf_counter() - started
    logger.info(
        "[Internal Data upload] project_id=%s filename=%s bytes=%s storage_key=%s dest_path=%s duration_s=%.3f",
        project_id,
        file.filename,
        total_bytes,
        storage_key,
        dest_path,
        duration_s,
    )
    return InternalDataUploadResponse(
        settings=_settings_to_response(project_id, settings),
        uploaded_at=uploaded_at,
        file_original_name=file.filename,
        file_format=file_format,
    )


@router.post(
    "/projects/{project_id}/internal-data/test-url",
    response_model=InternalDataTestUrlResponse,
)
async def test_internal_data_url_endpoint(
    body: InternalDataTestUrlRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Test reachability of Internal Data URL for a project (no persistence besides last_test_*)."""
    result = test_url_for_project(project_id, body.url)
    return InternalDataTestUrlResponse(
        ok=result.ok,
        http_status=result.http_status,
        error=result.error,
        final_url=result.final_url,
        content_type=result.content_type,
        content_length=result.content_length,
    )


@router.post(
    "/projects/{project_id}/internal-data/sync",
    response_model=InternalDataSyncResponse,
)
async def sync_internal_data_endpoint(
    body: InternalDataSyncRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Synchronously run Internal Data sync for a project."""
    result = sync_now(project_id)
    if isinstance(result, dict) and result.get("status") == "error" and result.get("snapshot_id") is None:
        # Non-HTTP error path already handled inside, return 200 with error summary
        return InternalDataSyncResponse(**result)
    return InternalDataSyncResponse(**result)


@router.post(
    "/projects/{project_id}/internal-data/introspect",
    response_model=InternalDataIntrospectResponse,
)
async def introspect_internal_data_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Inspect the current Internal Data source and return detected fields."""
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H5","location":"routers.internal_data:introspect_endpoint:entry","message":"Introspect endpoint called","data":{"project_id":project_id},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    try:
        result = introspect_source_for_project(project_id)
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H5","location":"routers.internal_data:introspect_endpoint:success","message":"Introspect completed","data":{"project_id":project_id,"sourceFieldsCount":len(result.get("source_fields",[]))},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        return InternalDataIntrospectResponse(**result)
    except Exception as e:
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H5","location":"routers.internal_data:introspect_endpoint:error","message":"Introspect error","data":{"project_id":project_id,"error":str(e),"type":type(e).__name__},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        raise


@router.post(
    "/projects/{project_id}/internal-data/validate-mapping",
    response_model=InternalDataValidateMappingResponse,
)
async def validate_internal_data_mapping_endpoint(
    body: InternalDataValidateMappingRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Validate mapping_json against a small sample of the current Internal Data source."""
    result = validate_mapping_for_project(project_id, body.mapping_json)
    return InternalDataValidateMappingResponse(**result)


@router.get(
    "/projects/{project_id}/internal-data/snapshots/{snapshot_id}/errors",
    response_model=InternalDataRowErrorsResponse,
)
async def list_internal_data_row_errors_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Path(..., description="Snapshot ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of errors to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List row errors for a specific Internal Data snapshot."""
    result = list_internal_data_row_errors(project_id, snapshot_id, limit=limit, offset=offset)
    return InternalDataRowErrorsResponse(**result)


@router.get(
    "/projects/{project_id}/internal-data/products",
    response_model=InternalDataProductsResponse,
)
async def list_internal_data_products_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: Optional[int] = Query(None, description="Snapshot ID (uses latest if not provided)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of products to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    with_stock_only: bool = Query(False, description="Only return products with stock > 0"),
    include_category: bool = Query(False, description="Include internal_category_id in response"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List internal products for a project."""
    result = list_internal_products(
        project_id,
        snapshot_id=snapshot_id,
        limit=limit,
        offset=offset,
        with_stock_only=with_stock_only,
        include_category=include_category,
    )
    return InternalDataProductsResponse(**result)


@router.get(
    "/projects/{project_id}/internal-data/categories",
    response_model=InternalCategoryListOut,
)
async def list_internal_categories_endpoint(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by name or key"),
    parent_id: Optional[int] = Query(None, description="Filter by parent_id (null for root categories, number for children)"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of categories to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List internal categories for a project."""
    # FastAPI passes None if query param is not provided
    # Pass Ellipsis to function to mean "not provided" (all categories)
    parent_id_filter = ... if parent_id is None else parent_id
    result = list_internal_categories(
        project_id,
        q=q,
        parent_id=parent_id_filter,
        limit=limit,
        offset=offset,
    )
    return InternalCategoryListOut(**result)


@router.post(
    "/projects/{project_id}/internal-data/categories",
    response_model=InternalCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_internal_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    body: InternalCategoryCreate = ...,
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Create a new internal category for a project."""
    try:
        category = create_internal_category(
            project_id,
            key=body.key,
            name=body.name,
            parent_id=body.parent_id,
            meta_json=body.meta_json,
        )
        return InternalCategoryOut(**category)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "category_key_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this key already exists in the project",
            ) from e
        if error_msg == "parent_category_not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent category not found in the project",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from e


@router.get(
    "/projects/{project_id}/internal-data/categories/{category_id}",
    response_model=InternalCategoryOut,
)
async def get_internal_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="Category ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get internal category by ID."""
    category = get_internal_category(project_id, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return InternalCategoryOut(**category)


@router.patch(
    "/projects/{project_id}/internal-data/categories/{category_id}",
    response_model=InternalCategoryOut,
)
async def update_internal_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="Category ID"),
    body: InternalCategoryUpdate = ...,
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Update internal category."""
    # Build patch dict from body (only non-None fields)
    patch = {}
    if body.key is not None:
        patch["key"] = body.key
    if body.name is not None:
        patch["name"] = body.name
    if body.parent_id is not None:
        patch["parent_id"] = body.parent_id
    if body.meta_json is not None:
        patch["meta_json"] = body.meta_json
    
    if not patch:
        # No fields to update, just return existing
        category = get_internal_category(project_id, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        return InternalCategoryOut(**category)
    
    try:
        category = update_internal_category(project_id, category_id, patch)
        return InternalCategoryOut(**category)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "category_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            ) from e
        if error_msg == "category_key_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this key already exists in the project",
            ) from e
        if error_msg == "parent_category_not_found":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent category not found in the project",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from e


@router.delete(
    "/projects/{project_id}/internal-data/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_internal_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Path(..., description="Category ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Delete internal category."""
    try:
        delete_internal_category(project_id, category_id)
    except ValueError as e:
        if str(e) == "category_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.patch(
    "/projects/{project_id}/internal-data/products/{internal_sku}/category",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_internal_product_category_endpoint(
    project_id: int = Path(..., description="Project ID"),
    internal_sku: str = Path(..., description="Internal SKU"),
    body: InternalProductCategorySet = ...,
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Set category for an internal product."""
    try:
        set_internal_product_category(
            project_id,
            internal_sku,
            body.category_id,
        )
    except ValueError as e:
        if str(e) == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found in latest snapshot",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

