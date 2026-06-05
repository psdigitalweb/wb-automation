"""Schemas for WB SEO text generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


BrandVoice = Literal["экспертный", "тёплый", "минималистичный", "игривый"]
GenerationStrategy = Literal["two_pass", "single_pass_sonnet"]
GenerationStatus = Literal["completed", "needs_review", "failed"]
ValidationSeverity = Literal["error", "warning"]


class SeoGenerationRunRequest(BaseModel):
    category_id: int
    query_set_id: int | None = None
    main_query_text: str | None = None
    brand_voice: BrandVoice = "экспертный"
    strategy: GenerationStrategy = "two_pass"
    force_refresh: bool = False


class GeneratedCharacteristic(BaseModel):
    field: str
    value: str


class GeneratedCard(BaseModel):
    title: str
    characteristics: list[GeneratedCharacteristic] = Field(default_factory=list)
    description: str
    report: dict[str, Any] = Field(default_factory=dict)


class GenerationValidationIssue(BaseModel):
    check_name: str
    severity: ValidationSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SeoRelevanceQueryCoverage(BaseModel):
    query: str
    bucket: str
    weight: float
    found: bool
    zones: list[str] = Field(default_factory=list)
    occurrences: int = 0


class SeoRelevanceReport(BaseModel):
    score: int
    grade: Literal["high", "medium", "low"]
    main_query_text: str | None = None
    main_query_in_title: bool = False
    main_query_in_title_start: bool = False
    weighted_coverage: float = 0.0
    selected_queries_count: int = 0
    covered_queries_count: int = 0
    title_queries_count: int = 0
    description_queries_count: int = 0
    overused_queries: list[str] = Field(default_factory=list)
    missing_primary_queries: list[str] = Field(default_factory=list)
    query_coverage: list[SeoRelevanceQueryCoverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SeoRelevanceV2QueryScore(BaseModel):
    query: str
    bucket: str
    weight: float
    score: int
    intent_score: float = 0.0
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    zone_score: float = 0.0
    naturalness_score: float = 0.0
    supported_atoms: list[str] = Field(default_factory=list)
    unsupported_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SeoRelevanceV2Report(BaseModel):
    version: Literal["seo_relevance_v2"] = "seo_relevance_v2"
    score: int
    grade: Literal["high", "medium", "low"]
    main_query_text: str | None = None
    intent_fit: float = 0.0
    semantic_similarity: float = 0.0
    lexical_relevance: float = 0.0
    zone_placement: float = 0.0
    naturalness: float = 0.0
    product_truthfulness: float = 0.0
    evaluated_queries_count: int = 0
    strong_queries_count: int = 0
    weak_queries: list[str] = Field(default_factory=list)
    unsupported_intents: list[str] = Field(default_factory=list)
    query_scores: list[SeoRelevanceV2QueryScore] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SeoGenerationRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: int
    category_id: int
    nm_id: int
    run_id: int
    query_set_id: int | None = None
    content_version_id: int | None = None
    status: GenerationStatus
    content_status: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    attempts: int = 0
    prompt_version: str
    validator_version: str
    generated_card: GeneratedCard | None = None
    validation_results: list[GenerationValidationIssue] = Field(default_factory=list)
    seo_relevance: SeoRelevanceReport | None = None
    seo_relevance_v2: SeoRelevanceV2Report | None = None
    error_text: str | None = None
    # Iteration 1 additive quality fields.
    quality_mode: str | None = None
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    mode_used: str | None = None
    publishable: bool = False
    matcher_run_id: int | None = None
    strategy: GenerationStrategy = "two_pass"
    single_pass_validation: dict[str, Any] | None = None


class SeoGenerationPromptPreviewResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    query_set_id: int
    query_set_status: str
    provider_name: str
    model_name: str
    prompt_version: str
    system_prompt: str
    user_prompt: str


class SeoGenerationLatestResponse(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    content_version_id: int | None = None
    generation_run_id: int | None = None
    status: str | None = None
    title: str | None = None
    description: str | None = None
    query_snapshot: dict[str, Any] = Field(default_factory=dict)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)
    seo_relevance: SeoRelevanceReport | None = None
    seo_relevance_v2: SeoRelevanceV2Report | None = None
    error_text: str | None = None
    # Iteration 1 additive quality fields.
    quality_mode: str | None = None
    degraded_reasons: list[dict[str, Any]] = Field(default_factory=list)
    mode_used: str | None = None
    publishable: bool = False
    matcher_run_id: int | None = None
