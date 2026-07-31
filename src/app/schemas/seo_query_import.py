"""Schemas for internal SEO query import debug endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SeoQueryImportBatchMeta(BaseModel):
    batch_id: int
    project_id: int
    category_id: int
    status: str
    source_type: str
    source_path: str | None = None
    original_filename: str | None = None
    created_at: datetime
    updated_at: datetime
    query_column_resolved: str | None = None
    frequency_column_resolved: str | None = None
    normalization_version: str | None = None


class SeoQueryImportDiagnostics(BaseModel):
    raw_rows_imported: int
    raw_rows_skipped: int
    normalized_rows_created: int
    duplicate_groups_collapsed: int
    duplicate_raw_rows_detected: int


class SeoQueryImportSuspiciousRowPreview(BaseModel):
    row_number: int
    reason: str
    raw_query: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SeoQueryImportNormalizedQueryItem(BaseModel):
    id: int
    normalized_query: str
    display_query: str
    raw_query_example: str
    raw_row_count: int
    frequency_total: str
    normalization_version: str


class SeoQueryImportNormalizedQueryList(BaseModel):
    total: int
    limit: int
    offset: int
    q: str | None = None
    items: list[SeoQueryImportNormalizedQueryItem] = Field(default_factory=list)


class SeoQueryImportBatchDetailResponse(BaseModel):
    batch: SeoQueryImportBatchMeta
    diagnostics: SeoQueryImportDiagnostics
    suspicious_rows_preview: list[SeoQueryImportSuspiciousRowPreview] = Field(default_factory=list)
    normalized_queries: SeoQueryImportNormalizedQueryList
    bootstrap_run_id: int | None = None
    readiness_status: str | None = None


class SeoQueryCorpusSummary(BaseModel):
    project_id: int
    category_id: int
    active_batches_count: int
    total_batches_count: int
    total_raw_rows: int
    total_normalized_rows: int
    unique_normalized_queries: int
    duplicate_across_batches_count: int
    latest_batch_id: int | None = None
    readiness_status: str | None = None
    bootstrap_run_id: int | None = None
    bootstrap_run_status: str | None = None


class SeoQueryCorpusResponse(BaseModel):
    summary: SeoQueryCorpusSummary
    batches: list[SeoQueryImportBatchMeta] = Field(default_factory=list)
    normalized_queries: SeoQueryImportNormalizedQueryList


class SeoCategoryQueryDataLatestBatch(BaseModel):
    batch_id: int
    status: str
    original_filename: str | None = None
    created_at: datetime
    updated_at: datetime


class SeoCategoryQueryDataExpressivePrior(BaseModel):
    ready: bool
    status: str | None = None
    source: str | None = None
    schema_version: str | None = None
    axes_id: int | None = None
    llm_model: str | None = None
    prompt_version: str | None = None
    updated_at: datetime | None = None
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    expressive_axes: list[str] = Field(default_factory=list)
    audience_axes: list[str] = Field(default_factory=list)
    occasion_axes: list[str] = Field(default_factory=list)
    use_case_axes: list[str] = Field(default_factory=list)
    product_type_axes: list[str] = Field(default_factory=list)
    attribute_axes: list[str] = Field(default_factory=list)
    constraint_axes: list[str] = Field(default_factory=list)
    negative_constraint_axes: list[str] = Field(default_factory=list)


class SeoCategoryReviewArchiveCounts(BaseModel):
    source_table: str = "wb_feedback_snapshots"
    category_join: str = "products.subject_id"
    total_review_rows: int = 0
    text_review_rows: int = 0
    sku_with_reviews: int = 0
    sku_with_text_reviews: int = 0
    rating_positive_rows: int = 0


class SeoCategoryQueryDataReadiness(BaseModel):
    query_data_loaded: bool
    normalized_queries_ready: bool
    clusters_ready: bool
    expressive_prior_ready: bool
    ready: bool


class SeoCategoryQueryDataStatusResponse(BaseModel):
    project_id: int
    category_id: int
    query_count: int
    normalized_query_count: int
    cluster_count: int
    latest_batch: SeoCategoryQueryDataLatestBatch | None = None
    expressive_prior: SeoCategoryQueryDataExpressivePrior
    review_archive: SeoCategoryReviewArchiveCounts
    readiness: SeoCategoryQueryDataReadiness


class SeoCategoryQueryClusterItem(BaseModel):
    cluster_id: int
    cluster_key: str
    label: str | None = None
    top_query: str | None = None
    query_count: int
    top_frequency: str | None = None


class SeoCategoryQueryClusterListResponse(BaseModel):
    project_id: int
    category_id: int
    total: int
    limit: int
    offset: int
    items: list[SeoCategoryQueryClusterItem] = Field(default_factory=list)


class SeoCategoryQueryClusterMemberItem(BaseModel):
    normalized_query_text: str
    display_query: str | None = None
    frequency_total: str | None = None
    ranking_value_used: str
    query_type: str
    membership_reason_code: str


class SeoCategoryQueryClusterDetailResponse(BaseModel):
    project_id: int
    category_id: int
    cluster: SeoCategoryQueryClusterItem
    queries: list[SeoCategoryQueryClusterMemberItem] = Field(default_factory=list)


class SeoQueryDeleteResponse(BaseModel):
    project_id: int
    category_id: int
    deleted_batch_id: int | None = None
    action: str
    deleted_counts: dict[str, int] = Field(default_factory=dict)
    preserved_judgments_count: int = 0
    deleted_judgments_count: int = 0
    remaining_active_batches_count: int = 0
    remaining_unique_queries_count: int = 0
    bootstrap_run_id: int | None = None
    readiness_status: str
