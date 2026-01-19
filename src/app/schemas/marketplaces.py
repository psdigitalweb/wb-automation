"""Pydantic schemas for marketplaces."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


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
