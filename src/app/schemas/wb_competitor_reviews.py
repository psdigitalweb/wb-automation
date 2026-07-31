"""API schemas for competitor review collection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TargetStatus = Literal["queued", "collecting", "ready", "partial", "failed", "not_found"]
RunStatus = Literal["queued", "running", "completed", "failed"]
AnalysisStatus = Literal["queued", "running", "ready", "failed"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetitorTargetResponse(StrictSchema):
    nm_id: int
    title: str | None = None
    brand: str | None = None
    category_name: str | None = None
    text_reviews_count: int = 0
    collected_reviews_count: int = 0
    calculated_avg_rating: float | None = None
    wb_review_rating: float | None = None
    wb_feedback_count: int | None = None
    status: TargetStatus
    last_collected_at: datetime | None = None
    last_error: str | None = None
    analysis_status: AnalysisStatus | None = None
    analysis_is_stale: bool = False
    analysis_reviews_count: int | None = None
    analysis_cost_usd: float | None = None
    analysis_finished_at: datetime | None = None
    analysis_error: str | None = None
    analysis_estimated_cost_usd: float | None = None


class CompetitorTargetsResponse(StrictSchema):
    items: list[CompetitorTargetResponse]


class AddCompetitorTargetsRequest(StrictSchema):
    nm_ids: list[int] = Field(min_length=1, max_length=50)

    @field_validator("nm_ids")
    @classmethod
    def validate_nm_ids(cls, values: list[int]) -> list[int]:
        unique = list(dict.fromkeys(values))
        if any(value <= 0 for value in unique):
            raise ValueError("nm_ids must be positive")
        return unique


class AddCompetitorTargetsResponse(CompetitorTargetsResponse):
    added_count: int
    existing_count: int


class DeleteCompetitorTargetsResponse(StrictSchema):
    deleted_nm_ids: list[int]
    deleted_count: int


class CollectCompetitorReviewsRequest(StrictSchema):
    nm_ids: list[int] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("nm_ids")
    @classmethod
    def validate_nm_ids(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        unique = list(dict.fromkeys(values))
        if any(value <= 0 for value in unique):
            raise ValueError("nm_ids must be positive")
        return unique


class CompetitorRunResponse(StrictSchema):
    id: int
    status: RunStatus
    requested_nm_ids: list[int]
    completed_nm_ids: list[int] = Field(default_factory=list)
    failed_nm_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class CollectCompetitorReviewsResponse(StrictSchema):
    run: CompetitorRunResponse


class GetCompetitorRunResponse(StrictSchema):
    run: CompetitorRunResponse


class CompetitorReviewResponse(StrictSchema):
    id: int
    rating: int | None = None
    text: str | None = None
    pros: str | None = None
    cons: str | None = None
    created_at: datetime | None = None


class CompetitorReviewListResponse(StrictSchema):
    items: list[CompetitorReviewResponse]
    total: int
    has_more: bool


class CompetitorAnalysisEvidenceResponse(StrictSchema):
    review_id: str
    quote: str


class CompetitorAnalysisFindingResponse(StrictSchema):
    label: str
    category: Literal["product", "packaging_delivery", "service"] | None = None
    summary: str
    confidence: Literal["low", "medium", "high"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    support_count: int
    prevalence: Literal["frequent", "occasional", "isolated"]
    evidence: list[CompetitorAnalysisEvidenceResponse] = Field(default_factory=list)


class CompetitorAnalysisConflictResponse(StrictSchema):
    label: str
    summary: str
    support_count: int
    prevalence: Literal["frequent", "occasional", "isolated"]


class CompetitorAnalysisResultResponse(StrictSchema):
    schema_version: str
    overall_conclusion: str
    strengths: list[CompetitorAnalysisFindingResponse] = Field(default_factory=list)
    weaknesses: list[CompetitorAnalysisFindingResponse] = Field(default_factory=list)
    opportunities: list[CompetitorAnalysisFindingResponse] = Field(default_factory=list)
    conflicts: list[CompetitorAnalysisConflictResponse] = Field(default_factory=list)


class CompetitorAnalysisRunResponse(StrictSchema):
    id: int
    status: AnalysisStatus
    reviews_sent: int
    estimated_cost_usd: float
    max_cost_usd: float
    actual_cost_usd: float | None = None
    result: CompetitorAnalysisResultResponse | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CompetitorAnalysisStateResponse(StrictSchema):
    nm_id: int
    reviews_with_text: int
    estimated_cost_usd: float
    can_generate: bool
    is_stale: bool
    latest: CompetitorAnalysisRunResponse | None = None
    latest_ready: CompetitorAnalysisRunResponse | None = None


class GenerateCompetitorAnalysisRequest(StrictSchema):
    refresh: bool = False
    max_cost_usd: float = Field(default=0.2, gt=0, le=0.5)


class GenerateCompetitorAnalysisResponse(StrictSchema):
    run: CompetitorAnalysisRunResponse
    cached: bool = False
