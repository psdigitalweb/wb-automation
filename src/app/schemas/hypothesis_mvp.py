"""Pydantic schemas for hypotheses MVP."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
