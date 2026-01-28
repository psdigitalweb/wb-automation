"""Pydantic schemas for Warehouse Labor Days."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator


class WarehouseLaborRateBase(BaseModel):
    """Base schema for warehouse labor rate."""
    
    rate_name: str = Field(..., min_length=1, description="Rate name (non-empty)")
    employees_count: int = Field(..., gt=0, description="Number of employees")
    rate_amount: Decimal = Field(..., gt=0, description="Rate amount per employee")
    currency: str = Field("RUB", description="Currency code (default RUB)")
    
    @field_validator('rate_amount', mode='before')
    @classmethod
    def validate_rate_amount(cls, v):
        """Convert string to Decimal before validation."""
        if v is None:
            return v
        if isinstance(v, str):
            # Remove whitespace and replace comma with dot
            cleaned = v.strip().replace(' ', '').replace(',', '.')
            if not cleaned:
                raise ValueError("rate_amount cannot be empty")
            try:
                return Decimal(cleaned)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid rate_amount: {v}") from e
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        # If already Decimal, return as is
        if isinstance(v, Decimal):
            return v
        return v
    
    @field_serializer('rate_amount')
    def serialize_rate_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class WarehouseLaborDayCreate(BaseModel):
    """Schema for creating/updating a warehouse labor day."""
    
    work_date: date = Field(..., description="Work date")
    marketplace_code: Optional[str] = Field(None, description="Marketplace code (optional, null for general warehouse)")
    notes: Optional[str] = Field(None, description="Notes")
    rates: List[WarehouseLaborRateBase] = Field(..., min_length=1, description="List of rates (at least one required)")
    # currency is not required in Create - backend sets 'RUB' by default


class WarehouseLaborRateResponse(WarehouseLaborRateBase):
    """Schema for warehouse labor rate response."""
    
    id: int = Field(..., description="Rate ID")
    labor_day_id: int = Field(..., description="Labor day ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class WarehouseLaborDayResponse(BaseModel):
    """Schema for warehouse labor day response."""
    
    id: int = Field(..., description="Day ID")
    project_id: int = Field(..., description="Project ID")
    work_date: date = Field(..., description="Work date")
    marketplace_code: Optional[str] = Field(None, description="Marketplace code")
    notes: Optional[str] = Field(None, description="Notes")
    rates: List[WarehouseLaborRateResponse] = Field(..., description="List of rates")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    total_amount: Decimal = Field(..., description="Total amount (sum of employees_count * rate_amount)")
    
    @field_serializer('total_amount')
    def serialize_total_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class WarehouseLaborDaysListResponse(BaseModel):
    """Schema for list of warehouse labor days."""
    
    items: List[WarehouseLaborDayResponse] = Field(..., description="List of days")


class WarehouseLaborSummaryBreakdownItem(BaseModel):
    """Schema for a single breakdown item in summary."""
    
    work_date: Optional[date] = Field(None, description="Work date (for group_by='day')")
    marketplace_code: Optional[str] = Field(None, description="Marketplace code (for group_by='marketplace')")
    total_amount: Decimal = Field(..., description="Total amount for this group")
    
    @field_serializer('total_amount')
    def serialize_total_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)


class WarehouseLaborSummaryResponse(BaseModel):
    """Schema for warehouse labor summary."""
    
    total_amount: Decimal = Field(..., description="Total amount")
    breakdown: List[WarehouseLaborSummaryBreakdownItem] = Field(..., description="Breakdown by group")
    
    @field_serializer('total_amount')
    def serialize_total_amount(self, value: Decimal) -> str:
        """Serialize Decimal as string."""
        return str(value)
