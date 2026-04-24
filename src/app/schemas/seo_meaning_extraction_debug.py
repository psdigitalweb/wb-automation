"""Schemas for internal Meaning Extraction MVP debug endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SeoMeaningExtractionDebugResponse(BaseModel):
    category_meaning: dict[str, Any] = Field(default_factory=dict)
    product_projection: dict[str, Any] = Field(default_factory=dict)
    query_meaning: dict[str, Any] = Field(default_factory=dict)
    product_projection_flags: dict[str, Any] = Field(default_factory=dict)
    query_meaning_flags: dict[str, Any] = Field(default_factory=dict)

