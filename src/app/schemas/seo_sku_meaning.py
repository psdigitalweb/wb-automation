"""Schemas for SKU Meaning Preview / Annotation Tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SKU_MEANING_SCHEMA_VERSION = "sku_meaning_v0"
EVAL_DATASET_SCHEMA_VERSION = "eval_dataset_v0"

SkuMeaningStatus = Literal["draft", "verified", "needs_more_data", "rejected"]
QueryJudgmentLabel = Literal[
    "highly_relevant",
    "maybe_relevant",
    "too_broad",
    "irrelevant",
    "conflict",
    "dangerous_claim",
    "manual_rejected",
]


class SkuMeaningPayload(BaseModel):
    schema_version: str = SKU_MEANING_SCHEMA_VERSION
    functional: dict[str, Any] = Field(default_factory=dict)
    expressive: dict[str, Any] = Field(default_factory=dict)
    audience: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    review_status: SkuMeaningStatus = "draft"


class SkuMeaningProductEvidence(BaseModel):
    project_id: int
    nm_id: int
    vendor_code: str | None = None
    title: str | None = None
    brand: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    description: str | None = None
    price_u: int | None = None
    sale_price_u: int | None = None
    rating: float | None = None
    feedbacks: int | None = None
    sizes: Any = None
    colors: Any = None
    pics: Any = None
    dimensions: Any = None
    characteristics: Any = None
    updated_at: str | None = None


class SkuMeaningReviewEvidence(BaseModel):
    ref: str
    nm_id: int
    rating: int | None = None
    text: str
    created_at: str | None = None


class SkuMeaningEvidencePack(BaseModel):
    schema_version: str = "sku_evidence_pack_v0"
    project_id: int
    category_id: int
    nm_id: int
    evidence_hash: str
    product: SkuMeaningProductEvidence
    reviews: list[SkuMeaningReviewEvidence] = Field(default_factory=list)
    category_prior: dict[str, Any] = Field(default_factory=dict)
    product_projection: dict[str, Any] = Field(default_factory=dict)
    product_projection_flags: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SkuMeaningDraftResponse(BaseModel):
    meaning: SkuMeaningPayload
    evidence_hash: str
    cached: bool = False
    model: str | None = None
    prompt_version: str
    artifact_path: str | None = None
    raw_response_preview: str | None = None


class SkuMeaningAnnotationRequest(BaseModel):
    category_id: int | None = None
    meaning: SkuMeaningPayload
    status: SkuMeaningStatus
    evidence_hash: str
    reviewer: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    draft_model: str | None = None
    draft_prompt_version: str | None = None
    draft_artifact_path: str | None = None


class SkuMeaningAnnotationResponse(BaseModel):
    id: int
    project_id: int
    category_id: int
    nm_id: int
    schema_version: str
    status: SkuMeaningStatus
    meaning: SkuMeaningPayload
    reviewer: str | None = None
    evidence_hash: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    draft_model: str | None = None
    draft_prompt_version: str | None = None
    draft_artifact_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SkuMeaningAnnotationEnvelope(BaseModel):
    annotation: SkuMeaningAnnotationResponse | None = None


class SkuMeaningCandidateQuery(BaseModel):
    query_text: str
    normalized_query_text: str
    ranking_value_used: str | None = None
    bucket: str | None = None
    intent_type: str | None = None
    pruning_status: str | None = None
    query_id: int | None = None
    cluster_id: int | None = None
    cluster_key: str | None = None
    cluster_label_candidate: str | None = None
    existing_label: QueryJudgmentLabel | None = None
    existing_rationale: str | None = None


class SkuMeaningCandidateQueriesResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    items: list[SkuMeaningCandidateQuery] = Field(default_factory=list)


class SkuQueryJudgmentInput(BaseModel):
    query_text: str
    normalized_query_text: str | None = None
    query_id: int | None = None
    cluster_id: int | None = None
    cluster_key: str | None = None
    label: QueryJudgmentLabel
    rationale: str | None = None
    reviewer: str | None = None
    matcher_version: str | None = None
    source: str = "manual"


class SkuQueryJudgmentsRequest(BaseModel):
    category_id: int | None = None
    annotation_id: int | None = None
    items: list[SkuQueryJudgmentInput] = Field(default_factory=list)


class SkuQueryJudgmentResponse(BaseModel):
    id: int
    annotation_id: int
    project_id: int
    category_id: int
    nm_id: int
    query_text: str
    normalized_query_text: str
    query_id: int | None = None
    cluster_id: int | None = None
    cluster_key: str | None = None
    label: QueryJudgmentLabel
    rationale: str | None = None
    reviewer: str | None = None
    matcher_version: str | None = None
    source: str
    created_at: str | None = None
    updated_at: str | None = None


class SkuQueryJudgmentsResponse(BaseModel):
    items: list[SkuQueryJudgmentResponse] = Field(default_factory=list)


class SkuMeaningEvalExportRequest(BaseModel):
    category_id: int | None = None
    nm_ids: list[int] | None = None
    include_drafts: bool = False
    format: Literal["jsonl", "csv"] = "jsonl"


class SkuMeaningEvalExportResponse(BaseModel):
    schema_version: str = EVAL_DATASET_SCHEMA_VERSION
    project_id: int
    category_id: int | None = None
    exported_count: int
    format: Literal["jsonl", "csv"]
    content: str
    items: list[dict[str, Any]] = Field(default_factory=list)
