"""Pydantic schemas for marketplaces."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date


class MarketplaceBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Marketplace code (unique)")
    name: str = Field(..., min_length=1, max_length=255, description="Marketplace name")
    description: Optional[str] = Field(None, description="Marketplace description")


class MarketplaceResponse(MarketplaceBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectMarketplaceBase(BaseModel):
    is_enabled: bool = Field(False, description="Whether marketplace is enabled for the project")
    settings_json: Optional[Dict[str, Any]] = Field(None, description="Marketplace settings (secrets will be masked)")


class ProjectMarketplaceCreate(ProjectMarketplaceBase):
    marketplace_id: int = Field(..., description="Marketplace ID")


class ProjectMarketplaceUpdate(BaseModel):
    is_enabled: Optional[bool] = Field(None, description="Enable/disable marketplace")
    settings_json: Optional[Dict[str, Any]] = Field(None, description="Update settings (will be merged with existing)")


class ToggleRequest(BaseModel):
    is_enabled: bool = Field(..., description="Enable or disable marketplace")


class ProjectMarketplaceResponse(BaseModel):
    id: int
    project_id: int
    marketplace_id: int
    is_enabled: bool
    settings_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    marketplace_code: Optional[str] = None
    marketplace_name: Optional[str] = None
    marketplace_description: Optional[str] = None
    marketplace_active: Optional[bool] = None
    
    class Config:
        from_attributes = True


class ProjectMarketplaceWithMaskedSecrets(ProjectMarketplaceResponse):
    """Response with masked secrets in settings_json."""
    settings_json: Optional[Dict[str, Any]] = Field(None, description="Settings with masked secrets")


class WBConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="Wildberries API token")


class WBConnectResponse(BaseModel):
    success: bool
    message: str
    project_marketplace: Optional[ProjectMarketplaceWithMaskedSecrets] = None


class WBMarketplaceStatus(BaseModel):
    """Status response for Wildberries marketplace."""
    is_enabled: bool = Field(..., description="Whether Wildberries is enabled for the project")
    has_token: bool = Field(..., description="Whether API token is set")
    brand_id: Optional[int] = Field(None, description="Brand ID from settings_json")
    connected: bool = Field(..., description="True if enabled, has token, and has brand_id")
    updated_at: datetime = Field(..., description="Last update timestamp")


class WBCredentialsStatus(BaseModel):
    api_token: bool = Field(..., description="True if token exists (stored/encrypted). Does not return token.")


class WBSettingsStatus(BaseModel):
    brand_id: Optional[int] = Field(None, description="Brand ID from settings_json")


class WBMarketplaceStatusV2(BaseModel):
    """Status response for Wildberries marketplace (frontend-friendly, no secrets)."""
    is_enabled: bool
    is_configured: bool = Field(..., description="True if token exists AND brand_id exists")
    credentials: WBCredentialsStatus
    settings: WBSettingsStatus
    updated_at: datetime


class WBMarketplaceUpdate(BaseModel):
    """Update request for Wildberries marketplace."""
    is_enabled: bool = Field(..., description="Enable or disable Wildberries")
    api_token: Optional[str] = Field(None, description="API token (optional, only update if provided)")
    brand_id: Optional[int] = Field(None, description="Brand ID (optional, must be > 0 if provided)")
    
    @field_validator('brand_id')
    @classmethod
    def validate_brand_id(cls, v):
        if v is not None and v <= 0:
            raise ValueError('brand_id must be greater than 0')
        return v


class WBTariffsIngestRequest(BaseModel):
    """Request body for starting WB tariffs ingestion."""

    days_ahead: int = Field(
        14,
        ge=0,
        le=30,
        description="Number of days ahead (including today) for which to fetch tariffs",
    )


class WBTariffsIngestResponse(BaseModel):
    """Response for WB tariffs ingestion start."""

    status: str = Field(..., description="Ingestion start status (e.g. 'started')")
    days_ahead: int = Field(..., description="Requested days ahead")
    task: str = Field(..., description="Celery task name")
    task_id: Optional[str] = Field(
        None, description="Celery task identifier (result.id) if available"
    )


class WBTariffTypeStatus(BaseModel):
    """Status for a single WB tariffs data_type."""

    latest_fetched_at: Optional[datetime] = Field(
        None, description="Timestamp of the latest snapshot for this type"
    )
    latest_as_of_date: Optional[date] = Field(
        None,
        description="Latest as_of_date present for this type (for box/pallet/return)",
    )
    locale: Optional[str] = Field(
        None, description="Locale used for this type (for commission)"
    )


class WBTariffsStatusResponse(BaseModel):
    """Aggregated WB tariffs snapshots status (marketplace-level)."""

    marketplace_code: str = Field(..., description="Marketplace code (e.g. 'wildberries')")
    data_domain: str = Field(..., description="Data domain (e.g. 'tariffs')")
    latest_fetched_at: Optional[datetime] = Field(
        None, description="Latest fetched_at across all tariffs types"
    )
    types: Dict[str, WBTariffTypeStatus] = Field(
        ..., description="Per-type status for tariffs"
    )


# WB Finances schemas
class WBFinancesIngestRequest(BaseModel):
    """Request body for starting WB finances ingestion."""

    date_from: str = Field(..., description="Start date in format YYYY-MM-DD")
    date_to: str = Field(..., description="End date in format YYYY-MM-DD")


class WBFinancesIngestResponse(BaseModel):
    """Response for WB finances ingestion start."""

    status: str = Field(..., description="Ingestion start status (e.g. 'started')")
    task_id: Optional[str] = Field(
        None, description="Celery task identifier if available"
    )
    date_from: str = Field(..., description="Requested start date")
    date_to: str = Field(..., description="Requested end date")


class WBFinanceReportResponse(BaseModel):
    """Response model for a single finance report header."""

    report_id: int = Field(..., description="Report ID from API")
    period_from: Optional[date] = Field(None, description="Start date of report period")
    period_to: Optional[date] = Field(None, description="End date of report period")
    currency: Optional[str] = Field(None, description="Currency code")
    total_amount: Optional[float] = Field(None, description="Total amount if available")
    rows_count: int = Field(..., description="Number of lines in report")
    first_seen_at: datetime = Field(..., description="When report was first seen")
    last_seen_at: datetime = Field(..., description="When report was last seen")


class WBFinancesReportsResponse(BaseModel):
    """Response model for list of finance reports."""

    reports: List[WBFinanceReportResponse] = Field(..., description="List of finance reports")

