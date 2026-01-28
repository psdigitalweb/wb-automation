"""Pydantic schemas for Packaging Tariffs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer


class PackagingTariffUpsertRequest(BaseModel):
    """Schema for bulk upsert of packaging tariffs."""
    
    valid_from: date = Field(..., description="Date from which tariff is valid")
    cost_per_unit: Decimal = Field(..., gt=0, description="Cost per unit (must be > 0)")
    notes: Optional[str] = Field(None, description="Optional notes")
    sku_list: List[str] = Field(..., min_length=1, description="List of internal_sku (at least one required)")
    
    @field_serializer('cost_per_unit')
    def serialize_cost_per_unit(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class PackagingTariffItem(BaseModel):
    """Schema for a single packaging tariff."""
    
    id: int = Field(..., description="Tariff ID")
    project_id: int = Field(..., description="Project ID")
    internal_sku: str = Field(..., description="Internal SKU")
    valid_from: date = Field(..., description="Date from which tariff is valid")
    cost_per_unit: Decimal = Field(..., description="Cost per unit")
    currency: str = Field(..., description="Currency code")
    notes: Optional[str] = Field(None, description="Optional notes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    @field_serializer('cost_per_unit')
    def serialize_cost_per_unit(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class PackagingTariffsListResponse(BaseModel):
    """Schema for list of packaging tariffs."""
    
    items: List[PackagingTariffItem] = Field(..., description="List of tariffs")
    total: int = Field(..., description="Total count (for pagination)")


class PackagingSummaryBreakdownItem(BaseModel):
    """Schema for a single breakdown item in summary."""
    
    internal_sku: str = Field(..., description="Internal SKU")
    units_sold: int = Field(..., description="Units sold in period")
    amount: Decimal = Field(..., description="Packaging cost for this SKU")
    
    @field_serializer('amount')
    def serialize_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class PackagingSummaryResponse(BaseModel):
    """Schema for packaging cost summary."""
    
    total_amount: Decimal = Field(..., description="Total packaging cost")
    breakdown: List[PackagingSummaryBreakdownItem] = Field(default_factory=list, description="Breakdown by product (if group_by=product)")
    missing_tariff: dict = Field(..., description="Missing tariff info: {count: int, skus: List[str]}")
    
    @field_serializer('total_amount')
    def serialize_total_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)
