"""Project-scoped WB product group comparison endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.db_wb_product_groups import (
    get_group_comparison,
    get_group_members,
    get_group_series,
    get_product_group_memberships,
    list_product_group_categories,
    list_product_groups,
)
from app.deps import get_project_membership
from app.utils.report_period import enforce_report_period


router = APIRouter(prefix="/api/v1/projects", tags=["wb-product-groups"])


def _validate_period(project_id: int, date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")
    if date_to - date_from > timedelta(days=366):
        raise HTTPException(status_code=400, detail="period must not exceed 367 days")
    enforce_report_period(project_id, "product-groups", date_from, date_to)


@router.get("/{project_id}/wildberries/product-groups")
async def list_product_groups_endpoint(
    project_id: int = Path(..., description="Project ID"),
    search: str | None = Query(None, max_length=200),
    category: str | None = Query(None, max_length=200),
    in_stock: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    min_members: int = Query(2, ge=1, le=1000),
    _member=Depends(get_project_membership),
):
    return list_product_groups(
        project_id=project_id,
        search=search,
        category=category,
        in_stock=in_stock,
        page=page,
        page_size=page_size,
        min_members=min_members,
    )


@router.get("/{project_id}/wildberries/product-groups/categories")
async def list_product_group_categories_endpoint(
    project_id: int = Path(..., description="Project ID"),
    _member=Depends(get_project_membership),
):
    return {"items": list_product_group_categories(project_id)}


@router.get("/{project_id}/wildberries/products/{nm_id}/product-groups")
async def get_product_groups_for_product_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., ge=1),
    _member=Depends(get_project_membership),
):
    return {"items": get_product_group_memberships(project_id, nm_id)}


@router.get("/{project_id}/wildberries/product-groups/{wb_group_id}")
async def get_product_group_endpoint(
    project_id: int = Path(..., description="Project ID"),
    wb_group_id: int = Path(..., ge=1),
    _member=Depends(get_project_membership),
):
    members = get_group_members(project_id, wb_group_id)
    if not members:
        raise HTTPException(status_code=404, detail="Product group not found")
    return {
        "wb_group_id": wb_group_id,
        "members_count": len(members),
        "members": members,
    }


@router.get("/{project_id}/wildberries/product-groups/{wb_group_id}/comparison")
async def get_product_group_comparison_endpoint(
    project_id: int = Path(..., description="Project ID"),
    wb_group_id: int = Path(..., ge=1),
    date_from: date = Query(...),
    date_to: date = Query(...),
    _member=Depends(get_project_membership),
):
    _validate_period(project_id, date_from, date_to)
    members = get_group_comparison(
        project_id=project_id,
        wb_group_id=wb_group_id,
        date_from=date_from,
        date_to=date_to,
    )
    if not members:
        raise HTTPException(status_code=404, detail="Product group not found")
    return {
        "wb_group_id": wb_group_id,
        "members_count": len(members),
        "period_from": date_from,
        "period_to": date_to,
        "members": members,
    }


@router.get("/{project_id}/wildberries/product-groups/{wb_group_id}/series")
async def get_product_group_series_endpoint(
    project_id: int = Path(..., description="Project ID"),
    wb_group_id: int = Path(..., ge=1),
    nm_ids: list[int] = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    _member=Depends(get_project_membership),
):
    _validate_period(project_id, date_from, date_to)
    unique_nm_ids = list(dict.fromkeys(int(value) for value in nm_ids))
    if not unique_nm_ids:
        raise HTTPException(status_code=400, detail="At least one nm_id is required")
    if len(unique_nm_ids) > 5:
        raise HTTPException(status_code=400, detail="No more than 5 nm_ids are allowed")

    members = get_group_members(project_id, wb_group_id)
    if not members:
        raise HTTPException(status_code=404, detail="Product group not found")
    allowed_nm_ids = {int(member["nm_id"]) for member in members}
    if any(nm_id not in allowed_nm_ids for nm_id in unique_nm_ids):
        raise HTTPException(status_code=400, detail="Every nm_id must belong to the selected product group")

    return {
        "wb_group_id": wb_group_id,
        "period_from": date_from,
        "period_to": date_to,
        "series": get_group_series(
            project_id=project_id,
            wb_group_id=wb_group_id,
            nm_ids=unique_nm_ids,
            date_from=date_from,
            date_to=date_to,
        ),
    }
