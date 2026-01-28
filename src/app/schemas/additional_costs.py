"""Pydantic schemas for Additional Cost Entries."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_serializer


class AdditionalCostEntryBase(BaseModel):
    """Base schema for additional cost entry."""
    
    scope: Literal['project', 'marketplace', 'product'] = Field('project', description="Scope of the cost entry: project, marketplace, or product")
    marketplace_code: Optional[str] = Field(None, description="Marketplace code (e.g. 'wildberries')")
    period_from: date = Field(..., description="Start date of cost period")
    period_to: date = Field(..., description="End date of cost period (inclusive)")
    date_incurred: Optional[date] = Field(None, description="Date when cost was actually incurred")
    currency: str = Field("RUB", description="Currency code")
    amount: Decimal = Field(..., description="Cost amount")
    category: str = Field(..., description="Cost category (e.g. 'marketing', 'logistics', 'taxes')")
    subcategory: Optional[str] = Field(None, description="Cost subcategory")
    vendor: Optional[str] = Field(None, description="Vendor name")
    description: Optional[str] = Field(None, description="Description of the cost")
    nm_id: Optional[int] = Field(None, description="Product nm_id (for product-level costs, WB-only, optional)")
    internal_sku: Optional[str] = Field(None, description="Internal SKU (for product-level costs, required when scope='product')")
    source: str = Field("manual", description="Source of the entry (e.g. 'manual', 'import', 'api')")
    external_uid: Optional[str] = Field(None, description="External unique identifier (for deduplication)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata as JSON")


class AdditionalCostEntryCreate(AdditionalCostEntryBase):
    """Schema for creating a new additional cost entry."""
    pass


class AdditionalCostEntryUpdate(BaseModel):
    """Schema for updating an additional cost entry (all fields optional)."""
    
    scope: Optional[Literal['project', 'marketplace', 'product']] = None
    marketplace_code: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    date_incurred: Optional[date] = None
    currency: Optional[str] = None
    amount: Optional[Decimal] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    nm_id: Optional[int] = None
    internal_sku: Optional[str] = None
    source: Optional[str] = None
    external_uid: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class AdditionalCostEntryResponse(AdditionalCostEntryBase):
    """Schema for additional cost entry response."""
    
    id: int = Field(..., description="Entry ID")
    project_id: int = Field(..., description="Project ID")
    payload_hash: Optional[str] = Field(None, description="Hash of payload for deduplication")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    @field_serializer('amount')
    def serialize_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class AdditionalCostEntriesListResponse(BaseModel):
    """Schema for list of additional cost entries."""
    
    items: List[AdditionalCostEntryResponse] = Field(..., description="List of entries")
    limit: int = Field(..., description="Limit used")
    offset: int = Field(..., description="Offset used")


class AdditionalCostSummaryBreakdownItem(BaseModel):
    """Schema for a single breakdown item in summary."""
    
    category: str = Field(..., description="Cost category")
    subcategory: Optional[str] = Field(None, description="Cost subcategory")
    marketplace_code: Optional[str] = Field(None, description="Marketplace code (for marketplace level)")
    internal_sku: Optional[str] = Field(None, description="Internal SKU (for product level, primary identifier)")
    nm_id: Optional[int] = Field(None, description="Product nm_id (for product level, optional reference)")
    prorated_amount: Decimal = Field(..., description="Prorated amount for this group")
    
    @field_serializer('prorated_amount')
    def serialize_prorated_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class AdditionalCostSummaryResponse(BaseModel):
    """Schema for additional cost summary."""
    
    total_amount: Decimal = Field(..., description="Total prorated amount")
    breakdown: List[AdditionalCostSummaryBreakdownItem] = Field(..., description="Breakdown by group")
    
    @field_serializer('total_amount')
    def serialize_total_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class AdditionalCostCategoryItem(BaseModel):
    """Schema for a category with subcategories."""
    
    name: str = Field(..., description="Category name")
    subcategories: List[str] = Field(..., description="List of subcategory names")


class AdditionalCostCategoriesResponse(BaseModel):
    """Schema for categories response."""
    
    categories: List[AdditionalCostCategoryItem] = Field(..., description="List of categories with subcategories")
