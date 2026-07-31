"""Read-only WB card content and main-photo history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse

from app.db_product_content_history import (
    get_content_version,
    get_main_photo_asset,
    list_content_versions,
    list_main_photo_periods,
)
from app.deps import get_project_membership
from app.services.wb_product_content.file_storage import LocalMainPhotoStorage


router = APIRouter(prefix="/api/v1", tags=["wildberries-product-content-history"])


@router.get("/projects/{project_id}/products/{nm_id}/content-history")
async def content_history(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _membership=Depends(get_project_membership),
):
    return {
        "items": list_content_versions(
            project_id=project_id,
            nm_id=nm_id,
            limit=limit,
            offset=offset,
        )
    }


@router.get("/projects/{project_id}/products/{nm_id}/content-history/{version_id}")
async def content_history_version(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    version_id: int = Path(..., ge=1),
    _membership=Depends(get_project_membership),
):
    item = get_content_version(
        project_id=project_id,
        nm_id=nm_id,
        version_id=version_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    return item


@router.get("/projects/{project_id}/products/{nm_id}/main-photo-history")
async def main_photo_history(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    _membership=Depends(get_project_membership),
):
    return {"items": list_main_photo_periods(project_id=project_id, nm_id=nm_id)}


@router.get("/projects/{project_id}/products/{nm_id}/main-photo-assets/{asset_id}")
async def main_photo_asset_file(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    asset_id: int = Path(..., ge=1),
    _membership=Depends(get_project_membership),
):
    asset = get_main_photo_asset(
        project_id=project_id,
        nm_id=nm_id,
        asset_id=asset_id,
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Main photo asset not found")
    storage = LocalMainPhotoStorage()
    try:
        path = storage.resolve_storage_path(asset["storage_path"])
    except ValueError:
        raise HTTPException(status_code=404, detail="Main photo asset not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Archived main photo file not found")
    return FileResponse(
        path=path,
        media_type=asset.get("content_type") or "application/octet-stream",
        filename=path.name,
    )
