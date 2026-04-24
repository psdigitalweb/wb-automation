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
