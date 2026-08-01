"""Project-scoped read-only Wildberries catalog endpoint."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.db_wb_catalog import (
    get_catalog_default_period,
    get_wb_catalog_product,
    list_wb_catalog,
)
from app.deps import get_project_membership
from app.schemas.wb_catalog import WBCatalogProductResponse, WBCatalogResponse
from app.utils.report_period import enforce_report_period


router = APIRouter(prefix="/api/v1", tags=["wildberries-catalog"])


def _resolve_period(
    project_id: int,
    period_from: Optional[date],
    period_to: Optional[date],
    report_code: str = "catalog",
) -> tuple[date, date]:
    period_was_explicit = period_from is not None and period_to is not None
    if (period_from is None) != (period_to is None):
        raise HTTPException(
            status_code=400,
            detail="Specify both period_from and period_to, or leave both empty",
        )
    if period_from is None or period_to is None:
        period_from, period_to = get_catalog_default_period(project_id)
    if period_from > period_to:
        raise HTTPException(
            status_code=400,
            detail="period_from must be before or equal to period_to",
        )
    if (period_to - period_from).days > 730:
        raise HTTPException(status_code=400, detail="period must not exceed 731 days")
    try:
        enforce_report_period(project_id, report_code, period_from, period_to)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if period_was_explicit or detail.get("reason") != "no_primary_data":
            raise
    return period_from, period_to


@router.get(
    "/projects/{project_id}/wildberries/catalog",
    response_model=WBCatalogResponse,
    summary="Paginated Wildberries product catalog with current commercial and funnel metrics",
)
async def get_wb_catalog(
    project_id: int = Path(..., ge=1),
    q: Optional[str] = Query(None, max_length=200),
    period_from: Optional[date] = Query(None),
    period_to: Optional[date] = Query(None),
    activity: Literal["active", "all"] = Query("all"),
    sort: Literal[
        "title",
        "vendor_code",
        "price",
        "rating",
        "impressions",
        "ctr",
        "opens",
        "carts",
        "orders",
        "order_sum",
        "buyouts",
    ] = Query("order_sum"),
    order: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    ctr_mode: Literal["raw", "quality_filtered"] = Query("quality_filtered"),
    _membership=Depends(get_project_membership),
):
    period_from, period_to = _resolve_period(project_id, period_from, period_to)

    return list_wb_catalog(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        q=q,
        activity=activity,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        ctr_mode=ctr_mode,
    )


@router.get(
    "/projects/{project_id}/wildberries/catalog/{nm_id}",
    response_model=WBCatalogProductResponse,
    summary="Wildberries product detail with current metrics for a selected period",
)
async def get_wb_catalog_product_endpoint(
    project_id: int = Path(..., ge=1),
    nm_id: int = Path(..., ge=1),
    period_from: Optional[date] = Query(None),
    period_to: Optional[date] = Query(None),
    ctr_mode: Literal["raw", "quality_filtered"] = Query("quality_filtered"),
    _membership=Depends(get_project_membership),
):
    resolved_from, resolved_to = _resolve_period(project_id, period_from, period_to, "catalog-product")
    payload = get_wb_catalog_product(
        project_id=project_id,
        nm_id=nm_id,
        period_from=resolved_from,
        period_to=resolved_to,
        ctr_mode=ctr_mode,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return payload
