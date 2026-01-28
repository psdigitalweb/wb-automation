"""Pydantic schemas for project-scoped Internal Data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InternalDataSettingsResponse(BaseModel):
    project_id: int
    is_enabled: bool = Field(False, description="Whether Internal Data is enabled for the project")
    source_mode: Optional[str] = Field(
        None,
        description="Source mode: 'url' or 'upload'. None means not configured.",
    )
    source_url: Optional[str] = None
    file_storage_key: Optional[str] = None
    file_original_name: Optional[str] = None
    file_format: Optional[str] = None
    mapping_json: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping configuration for interpreting source fields (columns/attributes). Always an object.",
    )
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_test_at: Optional[datetime] = None
    last_test_status: Optional[str] = None


class InternalDataSettingsUpdate(BaseModel):
    is_enabled: bool = Field(..., description="Enable or disable Internal Data for the project")
    source_mode: Optional[str] = Field(
        None,
        description="Source mode: 'url' or 'upload'. None resets configuration.",
    )
    source_url: Optional[str] = Field(
        None,
        description="Source URL (required for URL mode)",
    )
    file_format: Optional[str] = Field(
        None,
        description="Optional format hint (e.g. 'csv', 'xlsx')",
    )
    mapping_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated mapping configuration for interpreting source fields. Null is treated as {}.",
    )


class InternalDataUploadResponse(BaseModel):
    settings: InternalDataSettingsResponse
    uploaded_at: datetime
    file_original_name: str
    file_format: Optional[str]


class InternalDataTestUrlRequest(BaseModel):
    url: Optional[str] = Field(
        None,
        description="URL to test. If not provided, uses settings.source_url.",
    )


class InternalDataTestUrlResponse(BaseModel):
    ok: bool
    http_status: Optional[int] = None
    error: Optional[str] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None


class InternalDataSyncRequest(BaseModel):
    force: Optional[bool] = Field(
        False,
        description="Reserved for future use (currently ignored).",
    )


class InternalDataSyncResponse(BaseModel):
    status: str
    snapshot_id: Optional[int]
    project_id: int
    version: Optional[int]
    row_count: Optional[int]
    rows_total: Optional[int] = Field(
        None,
        description="Total number of rows processed (only for mapping-based sync)",
    )
    rows_imported: Optional[int] = Field(
        None,
        description="Number of rows successfully imported (only for mapping-based sync)",
    )
    rows_updated: Optional[int] = Field(
        None,
        description="Number of rows that were updated (only for mapping-based sync)",
    )
    rows_failed: Optional[int] = Field(
        None,
        description="Number of rows that failed validation (only for mapping-based sync)",
    )
    errors_preview: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="First 10 error examples with row_index, message, source_key (only for mapping-based sync)",
    )
    error: Optional[str]
    started_at: datetime
    finished_at: datetime


class InternalDataRowErrorItem(BaseModel):
    id: int
    project_id: int
    snapshot_id: int
    row_index: int
    source_key: Optional[str]
    raw_row: Optional[Dict[str, Any]]
    error_code: Optional[str]
    message: str
    transforms: Optional[List[str]]
    trace: Optional[Dict[str, Any]]
    created_at: datetime


class InternalDataRowErrorsResponse(BaseModel):
    total: int
    items: List[InternalDataRowErrorItem]


class InternalDataProductItem(BaseModel):
    id: int
    internal_sku: str
    name: Optional[str]
    lifecycle_status: Optional[str]
    attributes: Optional[Dict[str, Any]]
    price_rrp: Optional[float]
    price_currency: Optional[str]
    cost: Optional[float]
    cost_currency: Optional[str]
    internal_category_id: Optional[int] = None


class InternalDataProductsResponse(BaseModel):
    total: int
    items: List[InternalDataProductItem]


class InternalDataSourceField(BaseModel):
    key: str = Field(..., description="Stable key for the field (e.g. header or '@attribute').")
    label: str = Field(..., description="Human-readable label for the field.")
    kind: str = Field(..., description="Source kind: 'column' for CSV/XLSX headers or 'attribute' for XML attributes.")


class InternalDataIntrospectResponse(BaseModel):
    file_format: Optional[str] = Field(
        None,
        description="Detected or configured file format (e.g. 'csv', 'xlsx', 'xml').",
    )
    source_fields: List[InternalDataSourceField] = Field(
        ...,
        description="Detected fields in the source file.",
    )
    sample_rows: List[Dict[str, Any]] = Field(
        ...,
        description="First few raw data rows/items using the same keys as source_fields[].key.",
    )


class InternalDataValidateMappingRequest(BaseModel):
    mapping_json: Dict[str, Any] = Field(
        ...,
        description="Mapping configuration to validate.",
    )


class InternalDataValidateMappingRowError(BaseModel):
    row_index: int = Field(..., description="0-based index of the sample row with an error.")
    message: str = Field(..., description="Human-readable description of the mapping error for this row.")


class InternalDataValidateMappingResponse(BaseModel):
    preview_rows: List[Dict[str, Any]] = Field(
        ...,
        description="Preview of normalized rows as they would be ingested.",
    )
    errors: List[InternalDataValidateMappingRowError] = Field(
        ...,
        description="Row-level mapping errors for the preview sample.",
    )


class InternalCategoryOut(BaseModel):
    id: int
    key: str
    name: str
    parent_id: Optional[int] = None
    meta_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class InternalCategoryCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[int] = None
    meta_json: Optional[Dict[str, Any]] = Field(default=None)


class InternalCategoryUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=255)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_id: Optional[int] = None
    meta_json: Optional[Dict[str, Any]] = None


class InternalCategoryListOut(BaseModel):
    items: List[InternalCategoryOut]
    total: int
    limit: int
    offset: int


class InternalProductCategorySet(BaseModel):
    category_id: Optional[int] = Field(None, description="Internal category ID or None to unset")


# Category XML Import schemas

class ImportXmlMappingCategories(BaseModel):
    node_xpath: str = Field(..., description="XPath to category nodes")
    key_xpath: str = Field(..., description="XPath to category key (relative to node)")
    name_xpath: str = Field(..., description="XPath to category name (relative to node)")
    parent_key_xpath: Optional[str] = Field(None, description="XPath to parent category key (optional, can be inferred from hierarchy)")
    extra_meta_xpaths: Optional[Dict[str, str]] = Field(None, description="Additional metadata XPaths to extract into meta_json")


class ImportXmlMappingProducts(BaseModel):
    node_xpath: str = Field(..., description="XPath to product/offer nodes")
    sku_xpath: str = Field(..., description="XPath to internal SKU (relative to node)")
    category_key_xpath: str = Field(..., description="XPath to category key for product (relative to node)")
    category_name_fallback_xpath: Optional[str] = Field(None, description="Fallback XPath to category name if key not found")
    extra_meta_xpaths: Optional[Dict[str, str]] = Field(None, description="Additional metadata XPaths to extract into meta_json")


class ImportXmlMapping(BaseModel):
    format: str = Field(..., description="Format: 'yml' or '1c'")
    categories: ImportXmlMappingCategories
    products: ImportXmlMappingProducts


class CategoryImportResult(BaseModel):
    categories_total: int = Field(..., description="Total categories found in XML")
    categories_created: int = Field(..., description="New categories created")
    categories_updated: int = Field(..., description="Existing categories updated")
    products_total_rows: int = Field(..., description="Total product-category links found in XML")
    products_updated: int = Field(..., description="Products updated with categories")
    missing_sku: List[str] = Field(default_factory=list, description="SKUs not found in latest snapshot")
    missing_category: List[str] = Field(default_factory=list, description="Category keys not found (if create_missing_categories=False)")
    errors_first_n: List[Dict[str, Any]] = Field(default_factory=list, description="First N errors encountered (limited to 200)")


class CategoryImportIntrospectResponse(BaseModel):
    detected_format: str = Field(..., description="Detected format: 'yml' or '1c'")
    category_candidates: List[Dict[str, Any]] = Field(default_factory=list, description="Suggested category node paths and attributes")
    product_candidates: List[Dict[str, Any]] = Field(default_factory=list, description="Suggested product node paths and attributes")
    category_samples: List[Dict[str, Any]] = Field(default_factory=list, description="Sample category nodes (first 3)")
    product_samples: List[Dict[str, Any]] = Field(default_factory=list, description="Sample product nodes (first 3)")
    default_mapping: Dict[str, Any] = Field(default_factory=dict, description="Default mapping for detected format")

