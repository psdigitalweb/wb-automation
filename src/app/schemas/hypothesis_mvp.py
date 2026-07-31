"""Pydantic schemas for hypotheses MVP and project experiments."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class HypothesisLatestVersionOut(BaseModel):
    id: int
    version: int
    primary_metric_key: Optional[str] = None


class HypothesisOut(BaseModel):
    id: int
    key: str
    title: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    hypothesis_type: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    latest_version: Optional[HypothesisLatestVersionOut] = None


class HypothesisCreate(BaseModel):
    key: str
    title: str
    description: Optional[str] = None
    domain: Optional[str] = None
    hypothesis_type: Optional[str] = None
    hypothesis_text: Optional[str] = None
    primary_metric_key: Optional[str] = None


class HypothesisPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    domain: Optional[str] = None
    hypothesis_type: Optional[str] = None


class ExperimentCreate(BaseModel):
    hypothesis_id: int
    nm_id: int
    change_type: str = Field(..., pattern="^(cover|images_set|title|description|seo|other)$")
    change_note: str = Field(..., min_length=1)
    metric: str = Field(..., pattern="^(views|carts|orders|order_sum|cart_rate|order_cr|order_from_cart)$")


class ExperimentListItem(BaseModel):
    id: int
    project_id: int
    hypothesis_id: int
    nm_id: int
    change_type: str
    change_note: str
    metric: str
    control_mode: str
    controls_count: Optional[int] = None
    status: str
    period_start: Optional[Any] = None
    period_end: Optional[Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    hypothesis_title: Optional[str] = None
    product_title: Optional[str] = None


class RunItem(BaseModel):
    id: int
    experiment_id: int
    started_at: Optional[datetime] = None
    change_confirmed_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: str


class ResultItem(BaseModel):
    id: int
    run_id: int
    control_mode: str
    did_effect: Optional[float] = None
    p_value: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    pretrend_pass: Optional[bool] = None
    before_after_delta: Optional[float] = None
    computed_at: Optional[datetime] = None


class ExperimentDetail(ExperimentListItem):
    runs: List[RunItem] = Field(default_factory=list)
    latest_result: Optional[ResultItem] = None
