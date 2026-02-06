"""Pydantic schemas for marketplaces."""

from typing import Optional, Dict, Any, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
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


class WBFinancesEventsBuildRequest(BaseModel):
    """Request body for building WB financial events from raw lines."""

    date_from: str = Field(..., description="Start date in format YYYY-MM-DD")
    date_to: str = Field(..., description="End date in format YYYY-MM-DD")


class WBFinancesEventsBuildResponse(BaseModel):
    """Response for WB financial events build start."""

    status: str = Field(..., description="e.g. started")
    task_id: Optional[str] = Field(None, description="Celery task identifier")
    date_from: str = Field(..., description="Requested start date")
    date_to: str = Field(..., description="Requested end date")


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


# WB SKU PnL schemas
class WBSkuPnlBuildRequest(BaseModel):
    """Request body for building WB SKU PnL snapshot."""

    period_from: str = Field(..., description="Start date YYYY-MM-DD")
    period_to: str = Field(..., description="End date YYYY-MM-DD")
    version: int = Field(1, ge=1, description="Snapshot version")
    rebuild: bool = Field(True, description="Delete existing and rebuild")
    ensure_events: bool = Field(
        True,
        description="Build wb_financial_events for the period before building SKU PnL snapshot",
    )


class WBSkuPnlBuildResponse(BaseModel):
    """Response for WB SKU PnL build start."""

    status: str = Field(..., description="e.g. started")
    task_id: Optional[str] = Field(None, description="Celery task identifier")
    period_from: str = Field(..., description="Requested period_from")
    period_to: str = Field(..., description="Requested period_to")
    trace_id: Optional[str] = Field(None, description="Request trace id for diagnostics")


class WBSkuPnlSourceItem(BaseModel):
    """Single source (WB report) contributing to a SKU PnL row."""

    report_id: int = Field(..., description="WB report ID")
    report_period_from: Optional[str] = Field(None, description="Report period start")
    report_period_to: Optional[str] = Field(None, description="Report period end")
    report_type: str = Field(..., description="Report type label (e.g. Реализация)")
    rows_count: int = Field(..., description="Number of events from this report for this SKU")
    amount_total: float = Field(..., description="Sum of event amounts from this report for this SKU")


class WBSkuPnlItem(BaseModel):
    """Single SKU PnL row."""

    model_config = ConfigDict(json_encoders={Decimal: float})

    internal_sku: str = Field(..., description="Internal SKU")
    product_name: Optional[str] = Field(
        default=None,
        description="WB product name/title (for identification in details)",
    )
    product_image_url: Optional[str] = Field(
        default=None,
        description="WB product main image URL (https) (for identification in details)",
    )
    # Backward-compatible alias (deprecated)
    product_image: Optional[str] = Field(
        default=None,
        description="(Deprecated) Use product_image_url",
    )
    wb_category: Optional[str] = Field(
        default=None,
        description="WB product category/subject name (for identification in details)",
    )
    quantity_sold: int = Field(..., description="Quantity sold (from sale_gmv events)")
    gmv: float = Field(..., description="GMV (sale_gmv)")
    avg_price_realization_unit: Optional[Decimal] = Field(
        default=None,
        description="Average price realization per unit (gmv / quantity_sold)",
    )
    wb_commission_total: float = Field(
        ..., description="wb_commission_no_vat + wb_commission_vat"
    )
    wb_commission_pct_unit: Optional[Decimal] = Field(
        default=None,
        description="WB commission per unit as % of avg_price_realization_unit (percent points). NULL if avg_price_realization_unit=0.",
    )
    acquiring_fee: float = Field(..., description="Acquiring fee")
    delivery_fee: float = Field(..., description="Delivery fee")
    rebill_logistics_cost: float = Field(default=0, description="Rebill logistics cost")
    pvz_fee: float = Field(..., description="PVZ fee")
    wb_total_total: float = Field(
        ...,
        description="WB total costs (ABS-sum of commission/logistics/acquiring). Always >= 0.",
    )
    wb_total_unit: Optional[Decimal] = Field(
        default=None,
        description="WB total costs per unit (wb_total_total / quantity_sold). Always >= 0.",
    )
    wb_total_pct_unit: Optional[Decimal] = Field(
        default=None,
        description="WB total costs per unit as % of avg_price_realization_unit (percent points). NULL if avg_price_realization_unit=0.",
    )
    net_before_cogs: float = Field(
        ...,
        description="Income before COGS (gmv - wb_total_total), with normalized WB costs sign",
    )
    net_before_cogs_pct: Optional[Decimal] = Field(
        default=None,
        description="Income before COGS as % of GMV (percent points). NULL if gmv=0.",
    )
    wb_total_pct: Optional[Decimal] = Field(
        default=None,
        description="WB total costs as % of GMV (percent points). NULL if gmv=0.",
    )
    trips_cnt: Optional[int] = Field(
        default=None,
        description=(
            "Operational trips count for period: WB logistics operations "
            "(supplier_oper_name='Логистика' AND bonus_type_name LIKE 'К клиенту%'). "
            "NULL if diagnostics data is not available."
        ),
    )
    returns_cnt: Optional[int] = Field(
        default=None,
        description=(
            "Operational returns count for period: WB logistics return operations "
            "(supplier_oper_name='Логистика' AND bonus_type_name in reverse categories: "
            "'От клиента%' or 'Возврат ... (К продавцу)' including defect/unidentified). "
            "NULL if diagnostics data is not available."
        ),
    )
    buyout_pct: Optional[Decimal] = Field(
        default=None,
        description="Buyout % of trips (percent points): (trips_cnt - returns_cnt) / trips_cnt * 100. NULL if trips_cnt=0.",
    )
    events_count: int = Field(..., description="Number of source events")
    wb_price_admin: Optional[float] = Field(
        default=None,
        description="WB admin price (from price_snapshots) as-of end of the selected period",
    )
    rrp_price: Optional[float] = Field(
        default=None,
        description="RRP (from Internal Data, latest successful snapshot)",
    )
    cogs_per_unit: Optional[Decimal] = Field(
        default=None,
        description="COGS per unit (calculated from cogs_direct_rules as-of period_to)",
    )
    cogs_total: Optional[Decimal] = Field(
        default=None,
        description="COGS total for the period (cogs_per_unit * quantity_sold)",
    )
    income_before_cogs_unit: Optional[Decimal] = Field(
        default=None,
        description="Income before COGS per unit (avg_price_realization_unit - wb_total_unit)",
    )
    income_before_cogs_pct_rrp: Optional[Decimal] = Field(
        default=None,
        description="Income before COGS per unit as % of RRP (percent points). NULL if rrp=0.",
    )
    wb_total_pct_rrp: Optional[Decimal] = Field(
        default=None,
        description="WB total costs per unit as % of RRP (percent points). NULL if rrp=0.",
    )
    product_profit: Optional[Decimal] = Field(
        default=None,
        description="Profit after COGS (net_before_cogs - cogs_total)",
    )
    product_margin_pct: Optional[Decimal] = Field(
        default=None,
        description="Profit margin after COGS as % of GMV (percent points). NULL if gmv=0.",
    )
    gmv_per_unit: Optional[Decimal] = Field(
        default=None,
        description="(Deprecated) Use avg_price_realization_unit",
    )
    profit_per_unit: Optional[Decimal] = Field(
        default=None,
        description="(Deprecated) Use profit_unit",
    )
    profit_unit: Optional[Decimal] = Field(
        default=None,
        description="Profit per unit after COGS (avg_price_realization_unit - wb_total_unit - cogs_per_unit)",
    )
    margin_pct_unit: Optional[Decimal] = Field(
        default=None,
        description="Unit margin % of revenue (percent points). NULL if avg_price_realization_unit=0.",
    )
    profit_pct_of_rrp_unit: Optional[Decimal] = Field(
        default=None,
        description="(Deprecated) Use profit_pct_rrp",
    )
    profit_pct_rrp: Optional[Decimal] = Field(
        default=None,
        description="Profit per unit as % of RRP (percent points). NULL if rrp=0.",
    )
    cogs_missing: bool = Field(
        default=False,
        description="True if COGS cannot be calculated for this SKU (missing rule or missing price input)",
    )
    wb_commission_no_vat: float = Field(default=0)
    wb_commission_vat: float = Field(default=0)
    net_payable_metric: float = Field(default=0)
    wb_sales_commission_metric: float = Field(default=0)
    sources: List[WBSkuPnlSourceItem] = Field(
        default_factory=list,
        description="WB reports that contributed to this SKU total",
    )


class WBSkuPnlListResponse(BaseModel):
    """Response for WB SKU PnL list."""

    items: List[WBSkuPnlItem] = Field(..., description="SKU PnL rows")
    total_count: int = Field(..., description="Total rows matching filters")


class WBProductSubjectItem(BaseModel):
    """Single WB subject (product category) for filtering."""

    subject_id: int = Field(..., description="WB subject ID")
    subject_name: str = Field(..., description="WB subject name")
    skus_count: int = Field(..., description="Number of products (rows in products) in this subject")


# System marketplace settings schemas

class SystemMarketplaceSettingsBase(BaseModel):
    """Base schema for system marketplace settings."""
    is_globally_enabled: bool = Field(True, description="Whether marketplace is globally enabled")
    is_visible: bool = Field(True, description="Whether marketplace is visible in UI")
    sort_order: int = Field(100, description="Sort order for display")
    settings_json: Dict[str, Any] = Field(default_factory=dict, description="System-level settings JSON")


class SystemMarketplaceSettingsUpdate(BaseModel):
    """Update schema for system marketplace settings (partial update)."""
    is_globally_enabled: Optional[bool] = Field(None, description="Whether marketplace is globally enabled")
    is_visible: Optional[bool] = Field(None, description="Whether marketplace is visible in UI")
    sort_order: Optional[int] = Field(None, description="Sort order for display")
    settings_json: Optional[Dict[str, Any]] = Field(None, description="System-level settings JSON (will be merged)")


class SystemMarketplaceSettingsResponse(BaseModel):
    """Response schema for system marketplace settings."""
    marketplace_code: str = Field(..., description="Marketplace code")
    display_name: Optional[str] = Field(None, description="Display name from marketplaces table")
    is_globally_enabled: bool = Field(..., description="Whether marketplace is globally enabled")
    is_visible: bool = Field(..., description="Whether marketplace is visible in UI")
    sort_order: int = Field(..., description="Sort order for display")
    settings_json: Dict[str, Any] = Field(..., description="System-level settings JSON")
    has_record: bool = Field(..., description="Whether a record exists in system_marketplace_settings")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class SystemMarketplacePublicStatus(BaseModel):
    """Public read-only status for system marketplace (minimal fields)."""
    marketplace_code: str = Field(..., description="Marketplace code")
    is_globally_enabled: bool = Field(..., description="Whether marketplace is globally enabled")
    is_visible: bool = Field(..., description="Whether marketplace is visible in UI")
    sort_order: int = Field(..., description="Sort order for display")

