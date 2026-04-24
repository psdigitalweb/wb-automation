"""Schemas for category bootstrap and meaning-axis readiness."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CATEGORY_MEANING_AXES_SCHEMA_VERSION = "category_meaning_axes_v0"
CATEGORY_MEANING_AXES_PROMPT_VERSION = "category_meaning_axes_v0"

CategoryBootstrapTrigger = Literal["query_import", "manual", "matcher_auto"]
CategoryBootstrapStatus = Literal["queued", "running", "completed", "completed_with_warnings", "failed"]
CategoryReadinessStatus = Literal["not_started", "building", "ready_with_fallback", "ready_for_matching", "failed"]
CategoryAxesSource = Literal["deterministic", "llm_enhanced"]
CategoryAxesStatus = Literal["draft", "ready", "error", "not_started"]


class CategoryMeaningAxesPayload(BaseModel):
    product_type_axes: list[str] = Field(default_factory=list)
    use_case_axes: list[str] = Field(default_factory=list)
    audience_axes: list[str] = Field(default_factory=list)
    attribute_axes: list[str] = Field(default_factory=list)
    expressive_axes: list[str] = Field(default_factory=list)
    occasion_axes: list[str] = Field(default_factory=list)
    constraint_axes: list[str] = Field(default_factory=list)
    negative_constraint_axes: list[str] = Field(default_factory=list)
    conflict_rules: list[dict[str, Any] | str] = Field(default_factory=list)
    synonym_groups: list[dict[str, Any]] = Field(default_factory=list)
    generic_query_patterns: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)


class CategoryBootstrapRunRequest(BaseModel):
    category_id: int
    force_refresh: bool = False
    use_llm: bool = True


class CategoryBootstrapRunResponse(BaseModel):
    run_id: int
    project_id: int
    category_id: int
    status: CategoryBootstrapStatus
    readiness_status: CategoryReadinessStatus


class CategoryBootstrapStatusResponse(BaseModel):
    project_id: int
    category_id: int
    readiness_status: CategoryReadinessStatus
    latest_run_id: int | None = None
    run_status: CategoryBootstrapStatus | None = None
    current_step: str | None = None
    step_statuses: dict[str, Any] = Field(default_factory=dict)
    queries_count: int = 0
    clusters_count: int = 0
    query_meanings_count: int = 0
    query_atoms_count: int = 0
    embeddings_count: int = 0
    category_axes_status: str = "not_started"
    last_error: str | None = None
    updated_at: str | None = None
