from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WBSearchReportSnapshotItem(BaseModel):
    id: int
    project_id: int
    period_from: date
    period_to: date
    include_search_texts: bool
    include_substituted_skus: bool
    position_cluster: str
    order_by: Dict[str, Any] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)
    ingest_run_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class WBSearchReportSnapshotListResponse(BaseModel):
    items: List[WBSearchReportSnapshotItem]


class WBSearchReportSnapshotResponse(BaseModel):
    snapshot: WBSearchReportSnapshotItem
    raw_main_page: Optional[Dict[str, Any]] = None
    request_params: Dict[str, Any] = Field(default_factory=dict)


class WBSearchReportProductItem(BaseModel):
    nm_id: int
    vendor_code: Optional[str] = None
    name: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    vendor_code_norm: Optional[str] = None
    brand_name: Optional[str] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    tag_id: Optional[int] = None
    tag_name: Optional[str] = None
    # Funnel signals enrichment (from wb_card_stats_daily aggregated for snapshot period)
    opens: Optional[int] = None
    add_to_cart: Optional[int] = None
    conversion_to_order: Optional[float] = None  # orders / add_to_cart
    orders_sum: Optional[float] = None  # revenue
    # Stocks enrichment
    fbo_stock_qty: Optional[int] = None
    enterprise_stock_qty: Optional[int] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    raw: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class WBSearchReportProductsResponse(BaseModel):
    items: List[WBSearchReportProductItem]
    page: int
    page_size: int
    total: int
    pages: int


class WBSearchReportSubjectItem(BaseModel):
    subject_id: int
    subject_name: Optional[str] = None
    products_cnt: int = 0


class WBSearchReportSubjectsResponse(BaseModel):
    items: List[WBSearchReportSubjectItem] = Field(default_factory=list)


class WBSearchReportSearchTextsResponse(BaseModel):
    items: List[Dict[str, Any]]


class WBSearchReportKeywordsMultiResponse(BaseModel):
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    openCard: List[Dict[str, Any]] = Field(default_factory=list)
    addToCart: List[Dict[str, Any]] = Field(default_factory=list)
    cached: Dict[str, bool] = Field(default_factory=dict)
    errors: Dict[str, Any] = Field(default_factory=dict)
