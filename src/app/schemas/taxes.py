"""Pydantic schemas for Taxes module."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from app.services.taxes.profiles import normalize_tax_profile_params


class TaxProfileResponse(BaseModel):
    project_id: int
    model_code: str = Field(..., description="Tax model code (e.g., 'profit_tax', 'turnover_tax')")
    params_json: Dict[str, Any] = Field(..., description="Tax model parameters (rate, base_key, etc.)")
    updated_at: datetime


class TaxProfileUpdate(BaseModel):
    model_code: str = Field(..., description="Tax model code")
    params_json: Optional[Dict[str, Any]] = Field(
        None,
        description="Tax model parameters. If None, defaults to {}.",
    )

    @model_validator(mode="after")
    def validate_profile_params(self) -> "TaxProfileUpdate":
        self.params_json = normalize_tax_profile_params(
            self.model_code,
            self.params_json or {},
        )
        return self


class TaxProfileModelResponse(BaseModel):
    model_code: str
    title: str
    short_title: str
    description: str
    formula: str
    base_kind: str
    tax_rate_label: str
    default_tax_percent: float
    default_vat_percent: float
    vat_options: list[float] = Field(default_factory=list)
    supported_views: list[str] = Field(default_factory=list)


class TaxStatementResponse(BaseModel):
    id: int
    project_id: int
    period_id: int
    version: int
    status: str = Field(..., description="'success' or 'failed'")
    tax_expense_total: Optional[Decimal] = None
    breakdown_json: Dict[str, Any] = Field(default_factory=dict)
    stats_json: Dict[str, Any] = Field(..., description="Stats/metadata including model_code, params snapshot, etc.")
    error_message: Optional[str] = None
    error_trace: Optional[str] = None
    created_at: datetime


class BuildTaxRequest(BaseModel):
    period_id: Optional[int] = Field(
        None,
        description="Period ID. Either period_id or (date_from + date_to) must be provided.",
    )
    date_from: Optional[date] = Field(
        None,
        description="Start date. Required if period_id is not provided.",
    )
    date_to: Optional[date] = Field(
        None,
        description="End date. Required if period_id is not provided.",
    )
    
    @model_validator(mode="after")
    def validate_period(self) -> "BuildTaxRequest":
        """Ensure exactly one of period_id or (date_from + date_to) is provided."""
        has_period_id = self.period_id is not None
        has_dates = self.date_from is not None and self.date_to is not None
        
        if has_period_id and has_dates:
            raise ValueError("Cannot provide both period_id and date_from/date_to")
        
        if not has_period_id and not has_dates:
            raise ValueError("Must provide either period_id or both date_from and date_to")
        
        if not has_period_id:
            if self.date_from is None or self.date_to is None:
                raise ValueError("Both date_from and date_to are required when period_id is not provided")
        
        return self


class BuildTaxResponse(BaseModel):
    run_id: int
    status: str = Field(..., description="'queued'")
    project_id: int
    period_id: int
