"""Pydantic schemas for WB content analytics and reviews endpoints."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ContentAnalyticsSummaryItem(BaseModel):
    nm_id: int
    opens: int
    add_to_cart: int
    cart_rate: Optional[float] = None  # add_to_cart / opens
    orders: int
    conversion: Optional[float] = None  # orders / add_to_cart
    revenue: float
    impressions: int = 0
    card_clicks: int = 0
    funnel_ctr_percent: Optional[float] = None
    active_days_with_impressions: int = 0
    quality_excluded_rows: int = 0
    ctr_sample_tier: str = "insufficient"
    ctr_quality_flags: List[str] = Field(default_factory=list)


class ContentAnalyticsSummaryResponse(BaseModel):
    items: List[ContentAnalyticsSummaryItem]


class ReviewsSummaryItem(BaseModel):
    nm_id: int
    title: Optional[str] = None
    wb_category: Optional[str] = None
    image_url: Optional[str] = None
    vendor_code: Optional[str] = None
    avg_rating: Optional[float] = None
    reviews_count_total: int
    new_reviews: Optional[int] = None


class ReviewsSummaryResponse(BaseModel):
    items: List[ReviewsSummaryItem]


class ReviewDetailItem(BaseModel):
    external_id: str
    nm_id: int
    created_date: Optional[str] = None
    rating: Optional[int] = None
    user_name: Optional[str] = None
    text: Optional[str] = None
    pros: Optional[str] = None
    cons: Optional[str] = None
    answer_text: Optional[str] = None
    photo_urls: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    is_answered: bool = False
    has_media: bool = False
    is_archived: bool = False
    source_endpoint: Optional[str] = None


class ReviewsListResponse(BaseModel):
    items: List[ReviewDetailItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class FunnelSignalSeverity(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class FunnelSignalCode(str, Enum):
    low_traffic = "low_traffic"
    low_add_to_cart = "low_add_to_cart"
    loss_cart_to_order = "loss_cart_to_order"
    low_order_rate = "low_order_rate"
    scale_up = "scale_up"
    insufficient_data = "insufficient_data"


class FunnelSignalsItem(BaseModel):
    nm_id: int
    title: Optional[str] = None
    wb_category: Optional[str] = None
    image_url: Optional[str] = None
    vendor_code: Optional[str] = None
    fbo_stock_qty: Optional[int] = None
    fbo_stock_updated_at: Optional[str] = None
    enterprise_stock_qty: Optional[int] = None
    enterprise_stock_updated_at: Optional[str] = None
    opens: int
    carts: int
    orders: int
    revenue: float
    cart_rate: Optional[float] = None
    order_rate: Optional[float] = None
    cart_to_order: Optional[float] = None
    avg_check: Optional[float] = None
    impressions: int = 0
    card_clicks: int = 0
    funnel_ctr_percent: Optional[float] = None
    active_days_with_impressions: int = 0
    quality_excluded_rows: int = 0
    ctr_sample_tier: str = "insufficient"
    ctr_quality_flags: List[str] = Field(default_factory=list)
    signal_code: str
    signal: str
    signal_label: str
    severity: Optional[str] = None  # low, med, high
    potential_rub: float = 0.0
    bucket: Optional[str] = None  # low, mid, high
    signal_details: Optional[str] = None
    benchmark_scope: Optional[str] = None  # "category" | "project_fallback" for debug/transparency


class FunnelSignalsResponse(BaseModel):
    items: List[FunnelSignalsItem]
    page: int = 1
    page_size: int = 50
    total: int = 0
    pages: int = 0


class FunnelSignalsCategoryItem(BaseModel):
    wb_category: str
    products_cnt: int


class WBProductLookupItem(BaseModel):
    nm_id: int
    vendor_code: Optional[str] = None
    title: Optional[str] = None
    wb_category: Optional[str] = None


class WBProductLookupResponse(BaseModel):
    items: List[WBProductLookupItem] = Field(default_factory=list)


class SalesTrendPoint(BaseModel):
    date: str
    orders: int
    revenue: float
    impressions: int = 0
    card_clicks: int = 0
    ctr_percent: Optional[float] = None
    moving_average_orders: float
    moving_average_revenue: float
    moving_average_impressions: float = 0
    moving_average_card_clicks: float = 0
    moving_average_ctr_percent: Optional[float] = None


class SalesTrendSeries(BaseModel):
    nm_id: int
    vendor_code: Optional[str] = None
    title: Optional[str] = None
    points: List[SalesTrendPoint] = Field(default_factory=list)


class SalesTrendsResponse(BaseModel):
    period_from: str
    period_to: str
    window_days: int
    series: List[SalesTrendSeries] = Field(default_factory=list)



class OrderGeographySummary(BaseModel):
    orders: int
    gross_sales: float
    countries: int
    regions: int
    cities: int
    ppvz_count: int
    top_region: Optional[str] = None


class OrderGeographyItem(BaseModel):
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    ppvz_office_id: Optional[str] = None
    ppvz_office_name: Optional[str] = None
    office_name: Optional[str] = None
    orders: int
    share: float
    gross_sales: float
    unique_nm_ids: int
    top_nm_id: Optional[int] = None
    top_nm_orders: int = 0
    first_order_date: Optional[str] = None
    last_order_date: Optional[str] = None


class OrderGeographyResponse(BaseModel):
    summary: OrderGeographySummary
    items: List[OrderGeographyItem]
    group_by: str
    limit: int
    total_groups: int
