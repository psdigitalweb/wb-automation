"""Pydantic schemas for category profile derive/self-check/admin flows."""

from __future__ import annotations

from typing import Any, Literal

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


class CategoryProfileSummary(BaseModel):
    id: int
    project_id: int
    category_id: int
    version: str
    is_active: bool
    self_check_status: str | None = None
    created_at: str = ""
    updated_at: str = ""
    source_note: str | None = None


class CategoryProfileDetail(CategoryProfileSummary):
    payload: dict[str, Any] = Field(default_factory=dict)


class CategoryProfileListResponse(BaseModel):
    items: list[CategoryProfileSummary] = Field(default_factory=list)


class CategoryProfileDeriveRunSummary(BaseModel):
    id: int
    run_id: str
    project_id: int
    category_id: int
    status: str
    method: str
    profile_id: int | None = None
    profile_version: str | None = None
    self_check_status: str | None = None
    started_at: str = ""
    finished_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    error_message: str | None = None


class CategoryProfileDeriveRunListResponse(BaseModel):
    items: list[CategoryProfileDeriveRunSummary] = Field(default_factory=list)


class CategoryProfileDeriveRequest(BaseModel):
    category_id: int = Field(..., description="WB category scope.")
    dry_run: bool = Field(default=True)
    activate: bool = Field(
        default=False,
        description="Reserved for later steps. Step 7 keeps activation as an explicit separate action.",
    )


class CategoryProfileDeriveResponse(BaseModel):
    run_id: str
    project_id: int
    category_id: int
    profile_id: int | None = None
    profile_version: str
    snapshot_path: str
    source_note: str
    status: str
    self_check: CategoryProfileSelfCheckReport
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class CategoryProfileActivateResponse(BaseModel):
    profile: CategoryProfileSummary
