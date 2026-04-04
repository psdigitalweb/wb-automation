"""WB content analytics and reviews read-only endpoints."""

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.deps import get_project_membership
from app.db_products import search_project_products_lookup
from app.db_wb_analytics import (
    get_content_analytics_summary,
    get_content_analytics_summary_by_nm_ids,
    get_funnel_signals_raw,
    get_funnel_categories,
)
from app.db_wb_reviews import get_reviews_summary, list_reviews_by_nm_id
from app.db_stocks import (
    get_latest_fbo_stock_totals_by_nm_id,
    get_latest_enterprise_stock_by_vendor_code_norm,
)
from app.db_wb_search_report import (
    get_search_report_snapshot,
    get_keywords_cache_counts_by_nm_id,
    get_keywords_cache,
    get_search_report_product_metrics,
    list_search_report_products,
    list_search_report_products_all,
    list_search_report_subjects,
    list_search_report_snapshots,
    patch_search_report_snapshot_stats,
    upsert_keywords_cache,
)
from app.services.wb_funnel_signals import compute_funnel_signals
from app.schemas.wildberries_analytics import (
    ContentAnalyticsSummaryResponse,
    ContentAnalyticsSummaryItem,
    ReviewsSummaryResponse,
    ReviewsSummaryItem,
    ReviewsListResponse,
    ReviewDetailItem,
    FunnelSignalsResponse,
    FunnelSignalsItem,
    FunnelSignalsCategoryItem,
    WBProductLookupItem,
    WBProductLookupResponse,
)
from app.schemas.wildberries_search_report import (
    WBSearchReportKeywordsMultiResponse,
    WBSearchReportProductsResponse,
    WBSearchReportProductItem,
    WBSearchReportSearchTextsResponse,
    WBSearchReportSnapshotItem,
    WBSearchReportSnapshotListResponse,
    WBSearchReportSnapshotResponse,
    WBSearchReportSubjectItem,
    WBSearchReportSubjectsResponse,
)
from app.utils.get_project_marketplace_token import get_wb_analytics_token_for_project
from app.wb.analytics_client import WBAnalyticsClient, WBAnalyticsBadRequestError, WBAnalyticsUnauthorizedError

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
    only_enterprise_gt0: bool = Query(False, description="Only products with enterprise stock > 0"),
    only_fbo_gt0: bool = Query(False, description="Only products with FBO stock > 0"),
    only_with_reviews_in_period: bool = Query(False, description="Only products with reviews in selected period"),
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
        only_enterprise_gt0=only_enterprise_gt0,
        only_fbo_gt0=only_fbo_gt0,
        only_with_reviews_in_period=only_with_reviews_in_period,
    )
    return ReviewsSummaryResponse(
        items=[ReviewsSummaryItem(**r) for r in rows]
    )


@router.get(
    "/projects/{project_id}/wildberries/reviews/items",
    response_model=ReviewsListResponse,
    summary="Reviews list for one nm_id",
)
async def get_reviews_list_endpoint(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Query(..., description="Filter by nm_id"),
    period_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    period_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset"),
    _member=Depends(get_project_membership),
):
    """Detailed reviews feed for a product, including archive and seller answers."""
    if (period_from is None) != (period_to is None):
        raise HTTPException(
            status_code=400,
            detail="Specify both period_from and period_to, or leave both empty",
        )
    payload = list_reviews_by_nm_id(
        project_id=project_id,
        nm_id=nm_id,
        period_from=period_from,
        period_to=period_to,
        limit=limit,
        offset=offset,
    )
    return ReviewsListResponse(
        items=[ReviewDetailItem(**r) for r in payload["items"]],
        total=payload["total"],
        limit=payload["limit"],
        offset=payload["offset"],
        has_more=payload["has_more"],
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
    only_enterprise_gt0: bool = Query(False, description="Only SKU with enterprise stock > 0"),
    only_fbo_gt0: bool = Query(False, description="Only SKU with FBO stock > 0"),
    signal_code: Optional[str] = Query(None, description="Filter by signal code"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    sort: str = Query(
        "potential_rub",
        description="Sort field: opens, carts, cart_rate, cart_to_order, order_rate, revenue, potential_rub",
    ),
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

    def _chunk_list(seq: List, size: int):
        for i in range(0, len(seq), size):
            yield seq[i : i + size]

    def _enrich_with_stocks(rows: List[dict]) -> None:
        """Best-effort fill stock fields in-place for provided rows."""
        if not rows:
            return
        nm_ids_all = [int(r.get("nm_id")) for r in rows if r.get("nm_id") is not None]
        fbo_map: Dict[int, tuple] = {}
        for chunk in _chunk_list(nm_ids_all, 5000):
            try:
                fbo_map.update(get_latest_fbo_stock_totals_by_nm_id(chunk))
            except Exception:
                pass

        vendor_norms_all = [
            str(r.get("vendor_code_norm")).strip()
            for r in rows
            if r.get("vendor_code_norm") is not None and str(r.get("vendor_code_norm")).strip() != ""
        ]
        enterprise_map: Dict[str, int] = {}
        enterprise_run_at = None
        for chunk in _chunk_list(vendor_norms_all, 5000):
            try:
                m, run_at = get_latest_enterprise_stock_by_vendor_code_norm(project_id, chunk)
                enterprise_map.update(m)
                if enterprise_run_at is None:
                    enterprise_run_at = run_at
            except Exception:
                pass

        for r in rows:
            nm_id = r.get("nm_id")
            if nm_id is not None:
                qty, updated_at = fbo_map.get(int(nm_id), (None, None))
                r["fbo_stock_qty"] = int(qty) if qty is not None else None
                r["fbo_stock_updated_at"] = updated_at.isoformat() if hasattr(updated_at, "isoformat") else None
            else:
                r["fbo_stock_qty"] = None
                r["fbo_stock_updated_at"] = None

            vnorm = r.get("vendor_code_norm")
            vnorm_s = str(vnorm).strip() if vnorm is not None else ""
            r["enterprise_stock_qty"] = enterprise_map.get(vnorm_s) if vnorm_s else None
            r["enterprise_stock_updated_at"] = enterprise_run_at.isoformat() if hasattr(enterprise_run_at, "isoformat") else None

    if only_enterprise_gt0 or only_fbo_gt0:
        _enrich_with_stocks(items)
        if only_enterprise_gt0:
            items = [r for r in items if (r.get("enterprise_stock_qty") or 0) > 0]
        if only_fbo_gt0:
            items = [r for r in items if (r.get("fbo_stock_qty") or 0) > 0]
    # Sort
    sort_key = (
        sort
        if sort in ("opens", "carts", "cart_rate", "cart_to_order", "order_rate", "revenue", "potential_rub")
        else "potential_rub"
    )
    reverse = order == "desc"
    if sort_key == "opens":
        items = sorted(items, key=lambda r: r.get("opens") or 0, reverse=reverse)
    elif sort_key == "carts":
        items = sorted(items, key=lambda r: r.get("carts") or 0, reverse=reverse)
    elif sort_key == "cart_rate":
        items = sorted(items, key=lambda r: (r.get("cart_rate") is None, r.get("cart_rate") or 0), reverse=reverse)
    elif sort_key == "cart_to_order":
        items = sorted(
            items,
            key=lambda r: (r.get("cart_to_order") is None, r.get("cart_to_order") or 0),
            reverse=reverse,
        )
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

    if not (only_enterprise_gt0 or only_fbo_gt0):
        # Enrich page items with stocks (best-effort; do not fail the report if stock tables are empty).
        _enrich_with_stocks(page_items)

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


@router.get(
    "/projects/{project_id}/wildberries/analytics/funnel-signals/categories-stats",
    response_model=List[FunnelSignalsCategoryItem],
    summary="WB categories with product counts for funnel-signals filter (current slice)",
)
async def get_funnel_signals_categories_stats_endpoint(
    project_id: int = Path(..., description="Project ID"),
    period_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    period_to: date = Query(..., description="End date (YYYY-MM-DD)"),
    min_opens: int = Query(200, description="Min opens for gating and benchmarks"),
    only_cart_gt0: bool = Query(False, description="Only SKU with carts > 0"),
    only_enterprise_gt0: bool = Query(False, description="Only SKU with enterprise stock > 0"),
    only_fbo_gt0: bool = Query(False, description="Only SKU with FBO stock > 0"),
    signal_code: Optional[str] = Query(None, description="Filter by signal code"),
    _member=Depends(get_project_membership),
):
    """Return categories list with counts for the same slice as the funnel-signals report.

    Category filter itself is NOT applied here to keep full distribution in dropdown.
    """
    raw = get_funnel_signals_raw(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        only_cart_gt0=only_cart_gt0,
        wb_category=None,
    )
    items = compute_funnel_signals(raw, min_opens=min_opens)
    if signal_code:
        items = [r for r in items if r.get("signal_code") == signal_code]

    if only_enterprise_gt0 or only_fbo_gt0:
        # Apply the same stock filters as the main report (best-effort).
        def _chunk_list(seq: List, size: int):
            for i in range(0, len(seq), size):
                yield seq[i : i + size]

        nm_ids_all = [int(r.get("nm_id")) for r in items if r.get("nm_id") is not None]
        fbo_map: Dict[int, tuple] = {}
        for chunk in _chunk_list(nm_ids_all, 5000):
            try:
                fbo_map.update(get_latest_fbo_stock_totals_by_nm_id(chunk))
            except Exception:
                pass

        vendor_norms_all = [
            str(r.get("vendor_code_norm")).strip()
            for r in items
            if r.get("vendor_code_norm") is not None and str(r.get("vendor_code_norm")).strip() != ""
        ]
        enterprise_map: Dict[str, int] = {}
        for chunk in _chunk_list(vendor_norms_all, 5000):
            try:
                m, _run_at = get_latest_enterprise_stock_by_vendor_code_norm(project_id, chunk)
                enterprise_map.update(m)
            except Exception:
                pass

        if only_enterprise_gt0:
            items = [
                r
                for r in items
                if enterprise_map.get(str(r.get("vendor_code_norm") or "").strip(), 0) > 0
            ]
        if only_fbo_gt0:
            items = [
                r
                for r in items
                if (fbo_map.get(int(r.get("nm_id")), (0, None))[0] if r.get("nm_id") is not None else 0) > 0
            ]

    counts: Dict[str, int] = {}
    for r in items:
        cat = r.get("wb_category")
        if not cat:
            continue
        cat_s = str(cat).strip()
        if not cat_s:
            continue
        counts[cat_s] = counts.get(cat_s, 0) + 1

    return [
        FunnelSignalsCategoryItem(wb_category=k, products_cnt=v)
        for k, v in sorted(counts.items(), key=lambda kv: kv[0].lower())
    ]


@router.get(
    "/projects/{project_id}/wildberries/search-report/snapshots",
    response_model=WBSearchReportSnapshotListResponse,
    summary="List WB Search Report snapshots (tabular)",
)
async def list_wb_search_report_snapshots_endpoint(
    project_id: int = Path(..., description="Project ID"),
    limit: int = Query(20, ge=1, le=200, description="Max snapshots"),
    _member=Depends(get_project_membership),
):
    items = list_search_report_snapshots(project_id=project_id, limit=limit)
    return WBSearchReportSnapshotListResponse(
        items=[WBSearchReportSnapshotItem(**row) for row in items]
    )


@router.get(
    "/projects/{project_id}/wildberries/search-report/snapshots/{snapshot_id}",
    response_model=WBSearchReportSnapshotResponse,
    summary="Get WB Search Report snapshot details",
)
async def get_wb_search_report_snapshot_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Path(..., description="Snapshot ID"),
    _member=Depends(get_project_membership),
):
    snap = get_search_report_snapshot(project_id=project_id, snapshot_id=snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    item = WBSearchReportSnapshotItem(
        id=int(snap["id"]),
        project_id=int(snap["project_id"]),
        period_from=snap["period_from"],
        period_to=snap["period_to"],
        include_search_texts=bool(snap["include_search_texts"]),
        include_substituted_skus=bool(snap["include_substituted_skus"]),
        position_cluster=str(snap.get("position_cluster") or ""),
        order_by=snap.get("order_by") or {},
        stats=snap.get("stats") or {},
        ingest_run_id=snap.get("ingest_run_id"),
        created_at=snap["created_at"],
        updated_at=snap["updated_at"],
    )
    return WBSearchReportSnapshotResponse(
        snapshot=item,
        raw_main_page=snap.get("raw_main_page"),
        request_params=snap.get("request_params") or {},
    )


@router.get(
    "/projects/{project_id}/wildberries/search-report/products",
    response_model=WBSearchReportProductsResponse,
    summary="List WB Search Report products for snapshot",
)
async def list_wb_search_report_products_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Query(..., description="Snapshot ID"),
    q: Optional[str] = Query(None, description="Search by name/vendor_code/nm_id"),
    brand_name: Optional[str] = Query(None, description="Filter by brand_name"),
    subject_id: Optional[int] = Query(None, description="Filter by subject_id"),
    date_from: Optional[date] = Query(None, description="Override period start YYYY-MM-DD (for funnel metrics)"),
    date_to: Optional[date] = Query(None, description="Override period end YYYY-MM-DD (for funnel metrics)"),
    sort: str = Query("nm_id", description="Sort field"),
    order: str = Query("asc", description="Sort order: asc, desc"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    _member=Depends(get_project_membership),
):
    # Load full set to enable correct sorting across pages (same pattern as funnel-signals).
    items = list_search_report_products_all(
        project_id=project_id,
        snapshot_id=snapshot_id,
        q=q,
        brand_name=brand_name,
        subject_id=subject_id,
    )
    total = len(items)

    # Enrich rows with funnel metrics (wb_card_stats_daily) for snapshot period and with stocks.
    try:
        snap = get_search_report_snapshot(project_id=project_id, snapshot_id=snapshot_id)
    except Exception:
        snap = None
    snap_period_from = snap.get("period_from") if isinstance(snap, dict) else None
    snap_period_to = snap.get("period_to") if isinstance(snap, dict) else None

    # Funnel metrics should follow the UI date filters when provided, otherwise fall back to snapshot period.
    period_from = date_from or snap_period_from
    period_to = date_to or snap_period_to

    keywords_cache_counts = {}
    if items:
        try:
            nm_ids_all = [int(r.get("nm_id")) for r in items if r.get("nm_id") is not None]
            keywords_cache_counts = get_keywords_cache_counts_by_nm_id(snapshot_id=snapshot_id, nm_ids=nm_ids_all)
        except Exception:
            keywords_cache_counts = {}

    if period_from is not None and period_to is not None and items:
        nm_ids = [int(r.get("nm_id")) for r in items if r.get("nm_id") is not None]
        funnel_map = {}
        try:
            funnel_map = get_content_analytics_summary_by_nm_ids(
                project_id=int(project_id),
                period_from=period_from,
                period_to=period_to,
                nm_ids=nm_ids,
            )
        except Exception:
            funnel_map = {}

        try:
            fbo_map = get_latest_fbo_stock_totals_by_nm_id(nm_ids)
        except Exception:
            fbo_map = {}

        try:
            vendor_norms = [
                str(r.get("vendor_code_norm")).strip()
                for r in items
                if r.get("vendor_code_norm") is not None and str(r.get("vendor_code_norm")).strip() != ""
            ]
            enterprise_map, _enterprise_run_at = get_latest_enterprise_stock_by_vendor_code_norm(int(project_id), vendor_norms)
        except Exception:
            enterprise_map = {}

        for r in items:
            nm_id_val = r.get("nm_id")
            if nm_id_val is not None:
                fm = funnel_map.get(int(nm_id_val)) or {}
                r["opens"] = fm.get("opens")
                r["add_to_cart"] = fm.get("add_to_cart")
                r["conversion_to_order"] = fm.get("conversion_to_order")
                r["orders_sum"] = fm.get("orders_sum")
                qty, _updated_at = fbo_map.get(int(nm_id_val), (None, None))
                r["fbo_stock_qty"] = int(qty) if qty is not None else None
            else:
                r["opens"] = None
                r["add_to_cart"] = None
                r["conversion_to_order"] = None
                r["orders_sum"] = None
                r["fbo_stock_qty"] = None

            vnorm = r.get("vendor_code_norm")
            vnorm_s = str(vnorm).strip() if vnorm is not None else ""
            r["enterprise_stock_qty"] = enterprise_map.get(vnorm_s) if vnorm_s else None
            r["_keywords_cached_cnt"] = int(keywords_cache_counts.get(int(nm_id_val), 0) if nm_id_val is not None else 0)
    elif items:
        # Ensure sort key exists even without period.
        for r in items:
            nm_id_val = r.get("nm_id")
            r["_keywords_cached_cnt"] = int(keywords_cache_counts.get(int(nm_id_val), 0) if nm_id_val is not None else 0)

    def _metric_current(metrics: object, key: str) -> Optional[float]:
        if not isinstance(metrics, dict):
            return None
        v = metrics.get(key)
        if isinstance(v, dict):
            v = v.get("current", v.get("value", v.get("val")))
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    sort_key = (sort or "nm_id").strip()
    sort_order = (order or "asc").strip().lower()
    reverse = sort_order == "desc"

    def _raw_value(row: dict) -> object:
        if sort_key in ("nm_id",):
            return row.get("nm_id")
        if sort_key in ("vendor_code", "article"):
            return row.get("vendor_code")
        if sort_key in ("name", "title"):
            return row.get("name")
        if sort_key in ("subject", "subject_name", "category"):
            return row.get("subject_name")
        if sort_key in ("keywords",):
            return row.get("_keywords_cached_cnt")
        if sort_key in ("fbo_stock_qty", "fbo"):
            return row.get("fbo_stock_qty")
        if sort_key in ("enterprise_stock_qty", "stock", "warehouse"):
            return row.get("enterprise_stock_qty")
        if sort_key in ("opens",):
            return row.get("opens")
        if sort_key in ("add_to_cart", "carts"):
            return row.get("add_to_cart")
        if sort_key in ("conversion_to_order", "conversion"):
            return row.get("conversion_to_order")
        if sort_key in ("orders_sum", "revenue"):
            return row.get("orders_sum")
        if sort_key in ("avgPos", "avg_position", "avgPosition"):
            return _metric_current(row.get("metrics"), "avgPosition")
        if sort_key in ("visibility",):
            return _metric_current(row.get("metrics"), "visibility")
        if sort_key in ("orders",):
            return _metric_current(row.get("metrics"), "orders")
        # Fallback
        return row.get("nm_id")

    def _norm_value(row: dict) -> object:
        v = _raw_value(row)
        if v is None:
            return 0
        if isinstance(v, (int, float)):
            return v
        # numeric strings
        try:
            if isinstance(v, str) and v.strip() != "" and v.strip().replace(".", "", 1).isdigit():
                return float(v)
        except Exception:
            pass
        return str(v).lower()

    items.sort(key=_norm_value, reverse=reverse)
    items.sort(key=lambda r: _raw_value(r) is None)

    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    pages = (total + page_size - 1) // page_size if page_size else 1
    return WBSearchReportProductsResponse(
        items=[WBSearchReportProductItem(**row) for row in page_items],
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.get(
    "/projects/{project_id}/wildberries/search-report/subjects",
    response_model=WBSearchReportSubjectsResponse,
    summary="List WB Search Report subjects (categories) for snapshot slice",
)
async def list_wb_search_report_subjects_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Query(..., description="Snapshot ID"),
    q: Optional[str] = Query(None, description="Search by name/vendor_code/nm_id"),
    brand_name: Optional[str] = Query(None, description="Filter by brand_name"),
    _member=Depends(get_project_membership),
):
    items = list_search_report_subjects(
        project_id=project_id,
        snapshot_id=snapshot_id,
        q=q,
        brand_name=brand_name,
    )
    return WBSearchReportSubjectsResponse(
        items=[WBSearchReportSubjectItem(**row) for row in items]
    )


@router.get(
    "/projects/{project_id}/wildberries/search-report/search-texts",
    response_model=WBSearchReportSearchTextsResponse,
    summary="Get WB Search Report search texts (keywords) for product",
)
async def get_wb_search_report_search_texts_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Query(..., description="Snapshot ID (to infer period)"),
    nm_id: int = Query(..., description="WB nm_id"),
    limit: int = Query(30, ge=1, le=100, description="Max keywords"),
    _member=Depends(get_project_membership),
):
    snap = get_search_report_snapshot(project_id=project_id, snapshot_id=snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    token = get_wb_analytics_token_for_project(project_id)
    if not token:
        raise HTTPException(status_code=400, detail="WB Analytics token not configured")

    client = WBAnalyticsClient(token=token)
    try:
        items = await client.get_search_texts(
            nm_id=int(nm_id),
            date_from=snap["period_from"].isoformat(),
            date_to=snap["period_to"].isoformat(),
            limit=int(limit),
        )
    except WBAnalyticsUnauthorizedError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except WBAnalyticsBadRequestError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "request": getattr(e, "request_summary", None)})

    return WBSearchReportSearchTextsResponse(items=items or [])


@router.get(
    "/projects/{project_id}/wildberries/search-report/keywords",
    response_model=WBSearchReportKeywordsMultiResponse,
    summary="Get WB Search Report keywords (3 topOrderBy lists) for product",
)
async def get_wb_search_report_keywords_multi_endpoint(
    project_id: int = Path(..., description="Project ID"),
    snapshot_id: int = Query(..., description="Snapshot ID (to infer period)"),
    nm_id: int = Query(..., description="WB nm_id"),
    date_from: Optional[str] = Query(None, description="Override period start YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Override period end YYYY-MM-DD"),
    limit: int = Query(30, ge=1, le=100, description="Max keywords per list"),
    cache_ttl_hours: int = Query(24, ge=0, le=168, description="Cache TTL (hours); 0 disables cache"),
    _member=Depends(get_project_membership),
):
    snap = get_search_report_snapshot(project_id=project_id, snapshot_id=snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    token = get_wb_analytics_token_for_project(project_id)
    if not token:
        raise HTTPException(status_code=400, detail="WB Analytics token not configured")

    client = WBAnalyticsClient(token=token)
    # Default period: snapshot period. UI may override via date_from/date_to to decouple keyword fetch from snapshot selection.
    period_from = snap["period_from"].isoformat()
    period_to = snap["period_to"].isoformat()
    if date_from and date_to:
        try:
            from datetime import date as _date

            df = _date.fromisoformat(str(date_from)[:10])
            dt = _date.fromisoformat(str(date_to)[:10])
            if df <= dt:
                period_from = df.isoformat()
                period_to = dt.isoformat()
            else:
                period_from = dt.isoformat()
                period_to = df.isoformat()
        except Exception:
            pass

    # WB sometimes returns empty keyword lists until the analytics dataset for the period is "warmed up".
    # Warm-up once per (snapshot_id, period_from, period_to) via /search-report/report call that matches
    # the "collect report" behavior closely (limit=1000), otherwise WB may not actually build the dataset.
    try:
        stats = snap.get("stats") if isinstance(snap, dict) else None
        if not isinstance(stats, dict):
            stats = {}
        warm_key = f"keywords_warmup_v2:{period_from}:{period_to}"
        warm_val = stats.get(warm_key)
        if warm_val != "ok":
            try:
                from datetime import date as _date, timedelta as _td

                pf = _date.fromisoformat(period_from)
                pt = _date.fromisoformat(period_to)
                days = (pt - pf).days + 1
                past_to = pf - _td(days=1)
                past_from = past_to - _td(days=days - 1)
                await client.search_report_main_page(
                    current_period={"start": period_from, "end": period_to},
                    past_period={"start": past_from.isoformat(), "end": past_to.isoformat()},
                    order_by={"field": "avgPosition", "mode": "asc"},
                    position_cluster="all",
                    include_substituted_skus=True,
                    include_search_texts=True,
                    limit=1000,
                    offset=0,
                )
                patch_search_report_snapshot_stats(snapshot_id=snapshot_id, patch={warm_key: "ok"})
            except Exception as e:
                patch_search_report_snapshot_stats(snapshot_id=snapshot_id, patch={warm_key: f"error:{type(e).__name__}"})
    except Exception:
        pass

    result: Dict[str, Any] = {"orders": [], "openCard": [], "addToCart": [], "cached": {}, "errors": {}}

    metrics = None
    try:
        metrics = get_search_report_product_metrics(
            project_id=project_id,
            snapshot_id=snapshot_id,
            nm_id=nm_id,
        )
    except Exception:
        metrics = None

    def _metric_current(key: str) -> Optional[int]:
        if not isinstance(metrics, dict):
            return None
        v = metrics.get(key)
        if isinstance(v, dict):
            v = v.get("current")
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    # Reduce WB calls when metric is explicitly zero in snapshot (helps avoid timeouts / proxy resets).
    tops: List[str] = ["openCard", "addToCart", "orders"]
    orders_cur = _metric_current("orders")
    if orders_cur == 0:
        tops = [t for t in tops if t != "orders"]

    def _sanitize_items(items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        out: List[Dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict):
                out.append(it)
            else:
                # WB (or a bad cache row) can contain null/strings; skip to avoid response validation 500s.
                continue
        return out

    for top in tops:
        cached = None
        if cache_ttl_hours > 0:
            try:
                cached = get_keywords_cache(
                    project_id=project_id,
                    snapshot_id=snapshot_id,
                    nm_id=nm_id,
                    top_order_by=top,
                    max_age_hours=cache_ttl_hours,
                )
            except Exception:
                cached = None
        if cached is not None:
            result[top] = _sanitize_items(cached.get("items"))
            result["cached"][top] = True
            continue

        try:
            items = await client.get_search_texts(
                nm_id=int(nm_id),
                date_from=period_from,
                date_to=period_to,
                limit=int(limit),
                top_order_by=top,
            )
            result[top] = _sanitize_items(items)
            result["cached"][top] = False
            # Cache only non-empty results to avoid "sticky empty" due to transient WB issues.
            if result[top]:
                try:
                    upsert_keywords_cache(
                        project_id=project_id,
                        snapshot_id=snapshot_id,
                        nm_id=nm_id,
                        top_order_by=top,
                        limit=int(limit),
                        items=result[top],
                        ingest_run_id=None,
                    )
                except Exception:
                    pass
        except WBAnalyticsUnauthorizedError as e:
            result["errors"][top] = {"status_code": e.status_code, "error": str(e)}
        except WBAnalyticsBadRequestError as e:
            result["errors"][top] = {"status_code": e.status_code, "error": str(e), "request": e.request_summary}
        except Exception as e:
            result["errors"][top] = {"error": f"{type(e).__name__}: {e}"}

    return WBSearchReportKeywordsMultiResponse(**result)
