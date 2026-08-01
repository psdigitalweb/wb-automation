from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.data_availability import CoverageSegment


class ReportDatasetCoverage(BaseModel):
    code: str
    title: str
    role: Literal["primary", "supplementary"]
    min_date: Optional[date] = None
    max_date: Optional[date] = None
    present_count: int = Field(0, ge=0)
    segments: List[CoverageSegment] = Field(default_factory=list)


class ReportDateFilterOptions(BaseModel):
    enabled: bool
    min_date: Optional[date] = None
    max_date: Optional[date] = None
    default_from: Optional[date] = None
    default_to: Optional[date] = None
    segments: List[CoverageSegment] = Field(default_factory=list)


class ReportFilterOptionsResponse(BaseModel):
    project_id: int
    report_code: str
    primary_dataset: str
    date_filter: ReportDateFilterOptions
    datasets: List[ReportDatasetCoverage]
