"""API schemas for WB funnel report imports."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class WBFunnelImportResponse(BaseModel):
    id: int
    original_filename: str
    source_type: str
    period_from: date
    period_to: date
    rows_total: int
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    duplicate: bool = False


class WBFunnelImportListItem(BaseModel):
    id: int
    original_filename: str
    source_type: str
    status: str
    period_from: date | None = None
    period_to: date | None = None
    rows_total: int
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None


class WBFunnelImportListResponse(BaseModel):
    items: list[WBFunnelImportListItem]
