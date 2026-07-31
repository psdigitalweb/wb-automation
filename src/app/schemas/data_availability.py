"""Schemas for project data availability (coverage) page."""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


Grain = Literal["day", "week"]
AvailabilityStatus = Literal["OK", "WARN", "EMPTY", "NOT_CONFIGURED", "ERROR"]


class CoverageSegment(BaseModel):
    start: date
    end: date
    count: int = Field(..., ge=1)


class DatasetAvailability(BaseModel):
    code: str
    title: str
    grain: Grain
    status: AvailabilityStatus

    window_from: date
    window_to: date
    expected_count: int = Field(..., ge=0)
    present_count: int = Field(..., ge=0)
    missing_count: int = Field(..., ge=0)

    min_present: Optional[date] = None
    max_present: Optional[date] = None

    present_segments: List[CoverageSegment] = Field(default_factory=list)
    missing_segments: List[CoverageSegment] = Field(default_factory=list)

    note: Optional[str] = None


class DataAvailabilityResponse(BaseModel):
    project_id: int
    window_days: int = Field(..., ge=1)
    window_from: date
    window_to: date
    items: List[DatasetAvailability]

