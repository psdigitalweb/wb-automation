"""Product-facing SEO module schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherResponse


UserSeoStatus = Literal["ready", "processing", "needs_action", "lower_quality"]
QuerySelectionState = Literal["auto_selected", "pinned", "excluded"]
QuerySetStatus = Literal["draft", "confirmed"]


class SeoProductListItem(BaseModel):
    nm_id: int
    vendor_code: str | None = None
    title: str | None = None
    brand: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    rating: float | None = None
    feedbacks: int | None = None
    analysis_status: str
    category_status: str | None = None
    has_sku_meaning: bool = False
    has_sku_atoms: bool = False
    has_vision_atoms: bool = False


class SeoProductListResponse(BaseModel):
    project_id: int
    total: int
    items: list[SeoProductListItem] = Field(default_factory=list)


class SeoReadableBlock(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list)
    empty_text: str | None = None


class SeoProductSummaryResponse(BaseModel):
    project_id: int
    nm_id: int
    category_id: int
    product: dict[str, Any] = Field(default_factory=dict)
    product_status_label: str
    category_status_label: str
    vision_status_label: str
    blocks: list[SeoReadableBlock] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    # Iteration 1 additive quality surface (mirrors SeoSkuMeaningAnnotation).
    quality_mode: str | None = None
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)


class SeoProductAnalysisRunRequest(BaseModel):
    category_id: int | None = None
    force_refresh: bool = False
    include_vision: bool = True


class SeoProductAnalysisRunResponse(BaseModel):
    project_id: int
    nm_id: int
    category_id: int
    status: str
    product_status_label: str
    vision_status_label: str
    annotation_id: int | None = None
    evidence_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SeoProductAnalysisStatusResponse(BaseModel):
    project_id: int
    nm_id: int
    category_id: int | None = None
    status: str
    product_status_label: str
    has_sku_meaning: bool = False
    has_sku_atoms: bool = False
    has_vision_atoms: bool = False


class SeoQuerySelectionRunRequest(BaseModel):
    category_id: int
    limit: int = Field(default=400, ge=1, le=500)
    include_rejected: bool = True


class SeoQuerySelectionItem(BaseModel):
    id: int | None = None
    normalized_query_text: str
    display_query: str
    cluster_key: str | None = None
    bucket: str
    user_bucket_label: str
    score: float
    ranking_value_used: float | None = None
    selection_state: QuerySelectionState
    user_reasons: list[str] = Field(default_factory=list)
    matched_atoms: list[str] = Field(default_factory=list)
    missing_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)


class SeoQuerySetResponse(BaseModel):
    id: int | None = None
    project_id: int
    category_id: int
    nm_id: int
    status: QuerySetStatus = "draft"
    matcher_version: str | None = None
    atoms_version: str | None = None
    items: list[SeoQuerySelectionItem] = Field(default_factory=list)
    matcher: MeaningAwareMatcherResponse | None = None
    # Iteration 1 additive quality surface (mirrors SeoSkuQuerySet row).
    quality_mode: str | None = None
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    matcher_run_id: int | None = None


class SeoQuerySelectionUpdateItem(BaseModel):
    normalized_query_text: str
    selection_state: QuerySelectionState


class SeoQuerySelectionUpdateRequest(BaseModel):
    category_id: int
    status: QuerySetStatus = "draft"
    items: list[SeoQuerySelectionUpdateItem] = Field(default_factory=list)
