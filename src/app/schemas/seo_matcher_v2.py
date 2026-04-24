"""Schemas for the candidate matcher (matcher_v2) — iteration 1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherResponse


class MatcherV2RunRequest(BaseModel):
    """Body for ``POST /matcher/v2/run``.

    Mirrors the current matcher preview request so clients can switch by
    changing the URL only.
    """

    category_id: int
    nm_id: int
    limit: int = Field(default=120, ge=1, le=2000)
    include_rejected: bool = True


class MatcherV2RunResponse(BaseModel):
    """Outcome of a matcher_v2 run.

    Contains both the ready-to-render response (``response``) and the stable
    ``run_id`` pointing at the persisted trace in ``seo_matcher_runs``.
    """

    run_id: int
    quality_mode: str
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    response: MeaningAwareMatcherResponse


class MatcherV2ResultItem(BaseModel):
    id: int
    query_meaning_id: int | None = None
    cluster_key: str | None = None
    query_display: str
    normalized_query_text: str
    bucket: str
    eligibility_verdict: str
    score: float
    score_components: dict[str, float] = Field(default_factory=dict)
    matched_atoms: list[str] = Field(default_factory=list)
    missing_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    ranking_value_used: float | None = None
    semantic_similarity: float | None = None
    created_at: datetime


class MatcherV2RunDetailResponse(BaseModel):
    """Full detail for one persisted matcher run + its result rows."""

    run_id: int
    project_id: int
    category_id: int
    nm_id: int
    matcher_version: str
    policy_version: str
    category_profile_version: str
    sku_atoms_id: int | None = None
    vision_atoms_id: int | None = None
    query_atoms_version: str | None = None
    embedding_model: str | None = None
    readiness_snapshot: dict[str, Any] = Field(default_factory=dict)
    quality_mode: str | None = None
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    results: list[MatcherV2ResultItem] = Field(default_factory=list)
