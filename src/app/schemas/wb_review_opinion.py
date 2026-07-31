"""API contracts for manually requested customer-opinion analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

class ReviewOpinionEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    quote: str


class ReviewOpinionFindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    category: Literal["product", "packaging_delivery", "service"]
    summary: str
    confidence: Literal["low", "medium", "high"]
    supporting_review_ids: list[str]
    support_count: int = Field(ge=1)
    evidence: list[ReviewOpinionEvidenceResponse]


class ReviewOpinionIsolatedResponse(ReviewOpinionFindingResponse):
    sentiment: Literal["positive", "negative", "mixed"]


class ReviewOpinionConflictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    summary: str
    positive_review_ids: list[str]
    negative_review_ids: list[str]


class ReviewOpinionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wb_customer_opinion_v1"]
    overall_conclusion: str
    strengths: list[ReviewOpinionFindingResponse]
    weaknesses: list[ReviewOpinionFindingResponse]
    isolated_observations: list[ReviewOpinionIsolatedResponse]
    conflicts: list[ReviewOpinionConflictResponse]


class ReviewOpinionGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh: bool = False


class ReviewOpinionRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    status: Literal["queued", "running", "ready", "failed"]
    reviews_total: int
    reviews_with_text: int
    reviews_sent: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReviewOpinionStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_enabled: bool
    nm_id: int
    scope_type: Literal["all_time"] = "all_time"
    reviews_total: int
    reviews_with_text: int
    reviews_sent: int
    max_reviews_sent: int
    can_analyze: bool
    can_generate: bool
    stale: bool = False
    latest_run: ReviewOpinionRunSummary | None = None
    result_run_id: int | None = None
    result_created_at: datetime | None = None
    result: ReviewOpinionResultResponse | None = None


class ReviewOpinionGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: ReviewOpinionRunSummary
    reused: bool = False
    message: str
