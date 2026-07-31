"""Response schemas for the project-scoped Wildberries product catalog."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WBCatalogItem(BaseModel):
    nm_id: int
    vendor_code: Optional[str] = None
    title: Optional[str] = None
    main_photo_url: Optional[str] = None
    is_active: bool = False

    showcase_price: Optional[float] = None
    spp_percent: Optional[float] = None
    seller_discount_percent: Optional[float] = None
    rrp_price: Optional[float] = None

    rating: Optional[float] = None
    reviews_count: int = 0

    impressions: int = 0
    card_clicks: int = 0
    ctr_percent: Optional[float] = None

    opens: int = 0
    cart_count: int = 0
    cart_rate: Optional[float] = None
    order_count: int = 0
    cart_to_order_rate: Optional[float] = None
    order_sum: float = 0

    buyout_count: int = 0
    buyout_sum: float = 0


class WBCatalogMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int
    period_from: str
    period_to: str


class WBCatalogDataFreshness(BaseModel):
    products_at: Optional[str] = None
    showcase_at: Optional[str] = None
    prices_at: Optional[str] = None
    rrp_at: Optional[str] = None
    analytics_through: Optional[str] = None
    ctr_through: Optional[str] = None
    reviews_at: Optional[str] = None


class WBCatalogResponse(BaseModel):
    items: List[WBCatalogItem] = Field(default_factory=list)
    meta: WBCatalogMeta
    data_freshness: WBCatalogDataFreshness


class WBCatalogProductResponse(BaseModel):
    item: WBCatalogItem
    period_from: str
    period_to: str
    data_freshness: WBCatalogDataFreshness
