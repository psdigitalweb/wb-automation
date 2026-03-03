"""WB content analytics and reviews read-only endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.deps import get_project_membership
from app.db_products import search_project_products_lookup
from app.db_wb_analytics import get_content_analytics_summary, get_funnel_signals_raw, get_funnel_categories
from app.db_wb_reviews import get_reviews_summary
from app.services.wb_funnel_signals import compute_funnel_signals
from app.schemas.wildberries_analytics import (
    ContentAnalyticsSummaryResponse,
    ContentAnalyticsSummaryItem,
    ReviewsSummaryResponse,
    ReviewsSummaryItem,
    FunnelSignalsResponse,
    FunnelSignalsItem,
    WBProductLookupItem,
    WBProductLookupResponse,
)

router = APIRouter(prefix="/api/v1", tags=["wildberries-analytics"])


@router.get(
    "/projects/{project_id}/wildberries/products/lookup",
    response_model=WBProductLookupResponse,
    summary="Product lookup by nm_id or vendor code",
)
async def get_wb_product_lookup_endpoint(
    project_id: int = Path(..., description="Project ID"),
    q: str = Query(..., min_length=1, description="Search by nm_id or vendor_code"),
    limit: int = Query(8, ge=1, le=20, description="Max suggestions"),
    _member=Depends(get_project_membership),
):
    items = search_project_products_lookup(project_id=project_id, query=q, limit=limit)
    return WBProductLookupResponse(items=[WBProductLookupItem(**row) for row in items])


@router.get(
    "/projects/{project_id}/wildberries/content-analytics/summary",
    response_model=ContentAnalyticsSummaryResponse,
    summary="Content analytics funnel summary",
)
async def get_content_analytics_summary_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    period_to: date = Query(..., description="End date (YYYY-MM-DD)"),
    nm_id: Optional[int] = Query(None, description="Filter by nm_id"),
    _member=Depends(get_project_membership),
):
    """Aggregated funnel by nm_id: opens, add to cart, cart rate, orders, conversion, revenue."""
    rows = get_content_analytics_summary(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        nm_id=nm_id,
    )
    return ContentAnalyticsSummaryResponse(
        items=[ContentAnalyticsSummaryItem(**r) for r in rows]
    )


@router.get(
    "/projects/{project_id}/wildberries/reviews/summary",
    response_model=ReviewsSummaryResponse,
    summary="Reviews summary by nm_id",
)
async def get_reviews_summary_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    period_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    nm_id: Optional[int] = Query(None, description="Filter by nm_id"),
    vendor_code: Optional[str] = Query(None, description="Filter by vendor_code (article)"),
    wb_category: Optional[str] = Query(None, description="Filter by WB category (subject_name)"),
    rating_lte: Optional[float] = Query(None, ge=0, le=5, description="Filter by avg rating <= value"),
    _member=Depends(get_project_membership),
):
    """Avg rating, total reviews count, and new reviews in period by nm_id."""
    if (period_from is None) != (period_to is None):
        raise HTTPException(
            status_code=400,
            detail="Specify both period_from and period_to, or leave both empty",
        )
    rows = get_reviews_summary(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        nm_id=nm_id,
        vendor_code=vendor_code,
        wb_category=wb_category,
        rating_lte=rating_lte,
    )
    return ReviewsSummaryResponse(
        items=[ReviewsSummaryItem(**r) for r in rows]
    )


@router.get(
    "/projects/{project_id}/wildberries/analytics/funnel-signals",
    response_model=FunnelSignalsResponse,
    summary="Funnel signals report",
)
async def get_funnel_signals_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    period_to: date = Query(..., description="End date (YYYY-MM-DD)"),
    min_opens: int = Query(200, description="Min opens for gating and benchmarks"),
    only_cart_gt0: bool = Query(False, description="Only SKU with carts > 0"),
    wb_category: Optional[str] = Query(None, description="Filter by WB category (subject_name)"),
    signal_code: Optional[str] = Query(None, description="Filter by signal code"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    sort: str = Query("potential_rub", description="Sort field: opens, cart_rate, order_rate, revenue, potential_rub"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    _member=Depends(get_project_membership),
):
    """Funnel signals by nm_id. Paginated. Sort by sort param (default potential_rub desc).
    Always loads all project SKUs for period; benchmarks are computed per WB category with project fallback when category has < 10 SKUs.
    """
    raw = get_funnel_signals_raw(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        only_cart_gt0=only_cart_gt0,
        wb_category=None,
    )
    items = compute_funnel_signals(raw, min_opens=min_opens)
    if wb_category is not None:
        items = [r for r in items if r.get("wb_category") == wb_category]
    if signal_code:
        items = [r for r in items if r.get("signal_code") == signal_code]
    # Sort
    sort_key = sort if sort in ("opens", "cart_rate", "order_rate", "revenue", "potential_rub") else "potential_rub"
    reverse = order == "desc"
    if sort_key == "opens":
        items = sorted(items, key=lambda r: r.get("opens") or 0, reverse=reverse)
    elif sort_key == "cart_rate":
        items = sorted(items, key=lambda r: (r.get("cart_rate") is None, r.get("cart_rate") or 0), reverse=reverse)
    elif sort_key == "order_rate":
        items = sorted(items, key=lambda r: (r.get("order_rate") is None, r.get("order_rate") or 0), reverse=reverse)
    elif sort_key == "revenue":
        items = sorted(items, key=lambda r: r.get("revenue") or 0, reverse=reverse)
    else:
        items = sorted(items, key=lambda r: (r.get("potential_rub") or 0), reverse=reverse)
    total = len(items)
    pages = (total + page_size - 1) // page_size if page_size else 1
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    return FunnelSignalsResponse(
        items=[FunnelSignalsItem(**r) for r in page_items],
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get(
    "/projects/{project_id}/wildberries/analytics/funnel-signals/categories",
    response_model=List[str],
    summary="WB categories for funnel-signals filter",
)
async def get_funnel_signals_categories_endpoint(
    project_id: int = Path(..., description="Project ID"),
    _member=Depends(get_project_membership),
):
    """Distinct WB categories (subject_name) from products."""
    return get_funnel_categories(project_id)
