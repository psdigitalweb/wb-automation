"""Product-facing SEO module schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherResponse


UserSeoStatus = Literal["ready", "processing", "needs_action", "lower_quality"]
QuerySelectionState = Literal["auto_selected", "pinned", "excluded"]
QuerySetStatus = Literal["draft", "confirmed"]


class SeoProductListItem(BaseModel):
    nm_id: int
    vendor_code: str | None = None
    article: str | None = None
    title: str | None = None
    name: str | None = None
    photo_url: str | None = None
    brand: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    rating: float | None = None
    feedbacks: int | None = None
    review_count: int | None = None
    stock_quantity: int | None = None
    in_stock: bool | None = None
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
    selected_image_urls: list[str] | None = Field(default=None, max_length=4)


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


class SeoProductReadinessItem(BaseModel):
    key: str
    label: str
    ready: bool
    details: str | None = None


class SeoProductAiVisionVerdict(BaseModel):
    ready: bool = False
    status: str | None = None
    label: str
    items: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
    input_prompt: str | None = None
    evidence_block: str | None = None


class SeoProductQuerySetSummary(BaseModel):
    query_set_id: int
    status: str
    approval_state: str | None = None
    trust_state: str | None = None
    items_total: int = 0
    selected_items: int = 0
    approved: bool = False
    updated_at: datetime | None = None


class SeoProductReadinessResponse(BaseModel):
    project_id: int
    nm_id: int
    category_id: int | None = None
    product_card_exists: bool = False
    category_id_known: bool = False
    query_count: int = 0
    normalized_query_count: int = 0
    cluster_count: int = 0
    expressive_prior_ready: bool = False
    ai_vision: SeoProductAiVisionVerdict
    existing_query_set: SeoProductQuerySetSummary | None = None
    readiness: list[SeoProductReadinessItem] = Field(default_factory=list)
    can_select_queries: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class SeoQuerySelectionRunRequest(BaseModel):
    category_id: int
    limit: int = Field(default=400, ge=1, le=500)
    include_rejected: bool = True


class SeoProductionProductBlock(BaseModel):
    nm_id: int
    title: str | None = None
    description: str | None = None
    product_type: str | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    characteristics: list[dict[str, Any]] = Field(default_factory=list)


class SeoProductionCategoryBlock(BaseModel):
    category_id: int
    query_count: int = 0
    cluster_count: int = 0
    expressive_prior_axes: dict[str, Any] = Field(default_factory=dict)


class SeoProductionCandidate(BaseModel):
    cluster_id: int | None = None
    cluster_key: str | None = None
    query: str
    frequency: float | None = None
    ranking_value: float | None = None
    meaning_line: str | None = None
    sku_relevance_score: float | None = None


class SeoProductionMeaningLine(BaseModel):
    line: str
    evidence: list[str] = Field(default_factory=list)
    coverage_status: str = "weak"


class SeoProductionCandidatesBlock(BaseModel):
    candidate_count: int = 0
    total_candidate_count: int = 0
    display_candidate_count: int = 0
    sent_candidate_count: int = 0
    preview_limit: int = 0
    items: list[SeoProductionCandidate] = Field(default_factory=list)


class SeoProductionReadinessBlock(BaseModel):
    can_run: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class SeoProductionQuerySelectionPreviewResponse(BaseModel):
    project_id: int
    nm_id: int
    category_id: int
    product: SeoProductionProductBlock
    category: SeoProductionCategoryBlock
    ai_vision: SeoProductAiVisionVerdict
    candidates: SeoProductionCandidatesBlock
    readiness: SeoProductionReadinessBlock
    prompt_version: str | None = None
    input_prompt: str | None = None


class SeoProductionSelectedQuery(BaseModel):
    query: str
    status: str
    risk: str | None = None
    explanation: str
    cluster_id: int | None = None
    meaning_line: str | None = None
    frequency: float | None = None
    confidence: float | None = None


class SeoProductionOperatorCandidate(BaseModel):
    meaning_line: str
    query: str
    status: str
    risk: str | None = None
    explanation: str
    cluster_id: int | None = None
    frequency: float | None = None
    confidence: float | None = None


class SeoProductionQuerySelectionRunResponse(BaseModel):
    run_id: int
    project_id: int
    nm_id: int
    category_id: int
    status: str
    meaning_lines: list[SeoProductionMeaningLine] = Field(default_factory=list)
    selected_queries: list[SeoProductionSelectedQuery] = Field(default_factory=list)
    operator_candidates: dict[str, list[SeoProductionOperatorCandidate]] = Field(default_factory=dict)
    model: str | None = None
    prompt_version: str
    artifact_path: str | None = None
    candidate_count: int = 0
    sent_candidate_count: int = 0
    input_prompt: str | None = None


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
    status: QuerySetStatus = "confirmed"
    items: list[SeoQuerySelectionUpdateItem] = Field(default_factory=list)


class SeoCategorySelectedQueryItem(BaseModel):
    id: int
    query_text: str
    sort_order: int = 0
    source: str = "category_list"
    sku_count: int = 0
    ranking_value_used: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SeoCategorySelectedQueryListResponse(BaseModel):
    project_id: int
    category_id: int
    total: int = 0
    items: list[SeoCategorySelectedQueryItem] = Field(default_factory=list)


class SeoCategorySelectedQuerySaveRequest(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=500)


class SeoCategorySelectedQueryApplyRequest(BaseModel):
    category_id: int
    query_texts: list[str] | None = Field(default=None, max_length=500)


class SeoProductionQuerySelectionSaveItem(BaseModel):
    query: str
    selected: bool = True
    frequency: float | None = None
    meaning_line: str | None = None
    risk: str | None = None
    confidence: float | None = None
    explanation: str | None = None
    source: str = "production"


class SeoProductionQuerySelectionSaveRequest(BaseModel):
    category_id: int
    run_id: int | None = None
    status: QuerySetStatus = "confirmed"
    items: list[SeoProductionQuerySelectionSaveItem] = Field(default_factory=list)
