"""Schemas for query meaning library and meaning-aware matcher preview."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


QUERY_MEANING_SCHEMA_VERSION = "query_meaning_v0"
QUERY_MEANING_PROMPT_VERSION = "query_meaning_library_v0"
MEANING_AWARE_MATCHER_VERSION = "meaning_aware_matcher_v1_atoms_gate"

Genericness = Literal["specific", "broad", "generic"]
QueryMeaningStatus = Literal["draft", "ready", "needs_review", "error"]
MatcherBucket = Literal["primary", "secondary", "broad", "rejected"]


class QueryMeaningPayload(BaseModel):
    functional: dict[str, Any] = Field(default_factory=dict)
    expressive: dict[str, Any] = Field(default_factory=dict)
    audience: list[str] = Field(default_factory=list)
    occasion: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    conflicts_if_missing: list[str] = Field(default_factory=list)
    genericness: Genericness = "specific"
    confidence: dict[str, float] = Field(default_factory=dict)


class QueryMeaningLibraryBuildRequest(BaseModel):
    category_id: int
    limit: int = Field(default=100, ge=1, le=50000)
    force_refresh: bool = False
    use_llm: bool = False


class QueryMeaningLibraryBuildResponse(BaseModel):
    project_id: int
    category_id: int
    total_clusters: int
    processed: int
    created: int
    updated: int
    skipped: int
    errors: int
    error_items: list[dict[str, Any]] = Field(default_factory=list)


class QueryMeaningItem(BaseModel):
    id: int
    project_id: int
    category_id: int
    cluster_id: int | None = None
    cluster_key: str
    schema_version: str = QUERY_MEANING_SCHEMA_VERSION
    source_query_examples: list[str] = Field(default_factory=list)
    meaning_payload: QueryMeaningPayload
    canonical_text: str
    genericness: Genericness
    constraints: list[str] = Field(default_factory=list)
    conflicts_if_missing: list[str] = Field(default_factory=list)
    llm_model: str | None = None
    prompt_version: str = QUERY_MEANING_PROMPT_VERSION
    input_hash: str
    status: QueryMeaningStatus
    created_at: str | None = None
    updated_at: str | None = None


class QueryMeaningLibraryResponse(BaseModel):
    project_id: int
    category_id: int
    total: int
    items: list[QueryMeaningItem] = Field(default_factory=list)


class MeaningAwareMatcherRequest(BaseModel):
    category_id: int
    nm_id: int
    limit: int = Field(default=400, ge=1, le=500)
    include_rejected: bool = True


class MeaningAwareMatcherItem(BaseModel):
    query: str
    cluster_id: int | None = None
    cluster_key: str | None = None
    query_meaning_id: int
    bucket: MatcherBucket
    score: float
    semantic_similarity: float
    ranking_value_used: float | None = None
    genericness: Genericness
    matched_meanings: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    user_bucket_label: str | None = None
    user_reasons: list[str] = Field(default_factory=list)
    matched_atoms: list[str] = Field(default_factory=list)
    missing_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)
    debug_reasons: list[str] = Field(default_factory=list)


class MeaningAwareMatcherDiagnostics(BaseModel):
    matcher_version: str = MEANING_AWARE_MATCHER_VERSION
    query_meanings_total: int
    scored_total: int
    missing_library: bool = False
    embedding_model: str | None = None
    atoms_version: str | None = None
    atoms_gate_enabled: bool = False
    notes: list[str] = Field(default_factory=list)


class MeaningAwareMatcherResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    sku_annotation_id: int
    sku_annotation_status: str
    buckets: dict[MatcherBucket, list[MeaningAwareMatcherItem]]
    diagnostics: MeaningAwareMatcherDiagnostics
