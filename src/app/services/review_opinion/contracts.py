"""Strict contracts for review-opinion inputs and model outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReviewOpinionEvidence(StrictModel):
    review_id: str = Field(min_length=1, max_length=32)
    quote: str = Field(min_length=1, max_length=180)


class ReviewOpinionFinding(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    category: Literal["product", "packaging_delivery", "service"]
    summary: str = Field(min_length=2, max_length=400)
    confidence: Literal["low", "medium", "high"]
    supporting_review_ids: list[str] = Field(min_length=1, max_length=300)
    evidence: list[ReviewOpinionEvidence] = Field(min_length=1, max_length=3)


class ReviewOpinionIsolatedFinding(ReviewOpinionFinding):
    sentiment: Literal["positive", "negative", "mixed"]


class ReviewOpinionConflict(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    summary: str = Field(min_length=2, max_length=400)
    positive_review_ids: list[str] = Field(min_length=1, max_length=300)
    negative_review_ids: list[str] = Field(min_length=1, max_length=300)


class ReviewOpinionModelOutput(StrictModel):
    schema_version: Literal["wb_customer_opinion_v1"]
    overall_conclusion: str = Field(min_length=2, max_length=800)
    strengths: list[ReviewOpinionFinding] = Field(max_length=8)
    weaknesses: list[ReviewOpinionFinding] = Field(max_length=8)
    isolated_observations: list[ReviewOpinionIsolatedFinding] = Field(max_length=12)
    conflicts: list[ReviewOpinionConflict] = Field(max_length=8)


def review_opinion_json_schema() -> dict:
    """Return the exact schema sent to OpenRouter Structured Outputs."""

    return ReviewOpinionModelOutput.model_json_schema()
