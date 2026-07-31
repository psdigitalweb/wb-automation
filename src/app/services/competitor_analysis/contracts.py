"""Strict model contracts for the two-stage competitor analysis pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PIPELINE_VERSION = "wb_competitor_analysis_v1"
SCHEMA_VERSION = "wb_competitor_analysis_v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChunkTheme(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    sentiment: Literal["positive", "negative", "mixed"]
    category: Literal["product", "packaging_delivery", "service"]
    summary: str = Field(min_length=2, max_length=400)
    review_ids: list[str] = Field(min_length=1, max_length=75)


class ChunkAnalysis(StrictModel):
    themes: list[ChunkTheme] = Field(max_length=18)


class AnalysisEvidence(StrictModel):
    review_id: str = Field(min_length=1, max_length=32)
    quote: str = Field(min_length=1, max_length=180)


class AnalysisFinding(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    category: Literal["product", "packaging_delivery", "service"]
    summary: str = Field(min_length=2, max_length=400)
    confidence: Literal["low", "medium", "high"]
    source_theme_ids: list[str] = Field(min_length=1, max_length=40)
    evidence: list[AnalysisEvidence] = Field(min_length=1, max_length=3)


class AnalysisOpportunity(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    summary: str = Field(min_length=2, max_length=400)
    priority: Literal["low", "medium", "high"]
    source_theme_ids: list[str] = Field(min_length=1, max_length=40)
    evidence: list[AnalysisEvidence] = Field(min_length=1, max_length=3)


class AnalysisConflict(StrictModel):
    label: str = Field(min_length=2, max_length=100)
    summary: str = Field(min_length=2, max_length=400)
    source_theme_ids: list[str] = Field(min_length=2, max_length=40)


class CompetitorAnalysisModelOutput(StrictModel):
    schema_version: Literal["wb_competitor_analysis_v1"]
    overall_conclusion: str = Field(min_length=2, max_length=800)
    strengths: list[AnalysisFinding] = Field(max_length=8)
    weaknesses: list[AnalysisFinding] = Field(max_length=8)
    opportunities: list[AnalysisOpportunity] = Field(max_length=6)
    conflicts: list[AnalysisConflict] = Field(max_length=6)


def chunk_json_schema() -> dict:
    return ChunkAnalysis.model_json_schema()


def final_json_schema() -> dict:
    return CompetitorAnalysisModelOutput.model_json_schema()
