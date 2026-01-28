"""Pydantic schemas for COGS Direct Rules."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CogsDirectRuleBase(BaseModel):
    internal_sku: str = Field(..., description="Internal SKU or __ALL__ for default rules")
    valid_from: date = Field(..., description="Rule valid from date")
    valid_to: date | None = Field(None, description="Rule valid to date (inclusive)")
    applies_to: Literal["sku", "all"] = Field("sku", description="sku = per-SKU rule, all = default for all SKUs")
    mode: Literal["fixed", "percent_of_price", "percent_of_rrp", "percent_of_selling_price"] = Field(
        ...,
        description="Cost mode: fixed amount, or percent of price (0..100)",
    )
    value: Decimal = Field(..., description="Fixed amount or percent 0..100 for percent modes")
    currency: str | None = Field(None, description="Currency code (required for fixed mode)")
    price_source_code: Optional[str] = Field(None, description="Required for percent_of_price (e.g. internal_catalog_rrp)")
    meta_json: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class CogsDirectRuleResponse(CogsDirectRuleBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime


class CogsDirectRulesListResponse(BaseModel):
    items: List[CogsDirectRuleResponse]
    limit: int
    offset: int
    total: int


class CogsDirectRulesBulkUpsertRequest(BaseModel):
    items: List[CogsDirectRuleBase]


class CogsCoverageResponse(BaseModel):
    internal_data_available: bool = Field(..., description="Latest internal snapshot exists")
    internal_skus_total: int = Field(..., description="Distinct internal_sku in latest snapshot")
    covered_total: int = Field(..., description="SKUs with active rule or default")
    missing_total: int = Field(..., description="internal_skus_total - covered_total")
    coverage_pct: float = Field(..., description="Coverage percentage (0.0 if no internal SKUs)")


class PriceSourceAvailability(BaseModel):
    code: str
    title: str
    description: str
    available: bool
    stats: Dict[str, Any] = Field(default_factory=dict)


class PriceSourcesResponse(BaseModel):
    available_sources: List[PriceSourceAvailability]


class MissingSkusResponse(BaseModel):
    internal_data_available: bool
    total: int
    items: List[Dict[str, Any]] = Field(default_factory=list)
