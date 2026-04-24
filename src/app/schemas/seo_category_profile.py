"""Pydantic schemas for category profile derive/self-check flows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CategoryProfileSelfCheckResult = Literal["pass", "fail", "skip"]
CategoryProfileSelfCheckStatus = Literal["passed", "failed"]


class CategoryProfileSelfCheckItem(BaseModel):
    name: str
    result: CategoryProfileSelfCheckResult
    detail: str | None = None


class CategoryProfileSelfCheckReport(BaseModel):
    status: CategoryProfileSelfCheckStatus
    checks: list[CategoryProfileSelfCheckItem] = Field(default_factory=list)
