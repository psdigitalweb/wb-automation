from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RunStatus = Literal["queued", "running", "success", "failed", "timeout", "skipped", "canceled"]
RunTrigger = Literal["schedule", "manual", "api"]


class IngestRunResponse(BaseModel):
  id: int
  schedule_id: Optional[int]
  project_id: int
  marketplace_code: str
  job_code: str
  triggered_by: RunTrigger
  status: RunStatus
  started_at: Optional[datetime]
  finished_at: Optional[datetime]
  duration_ms: Optional[int]
  error_message: Optional[str]
  error_trace: Optional[str]
  stats_json: Optional[Dict[str, Any]]
  heartbeat_at: Optional[datetime] = None
  celery_task_id: Optional[str] = None
  meta_json: Optional[Dict[str, Any]] = None
  created_at: datetime
  updated_at: datetime

  class Config:
      from_attributes = True


class IngestRunListFilters(BaseModel):
  marketplace_code: Optional[str] = None
  job_code: Optional[str] = None
  status: Optional[RunStatus] = None
  date_from: Optional[datetime] = None
  date_to: Optional[datetime] = None
  limit: int = Field(100, ge=1, le=500)


class IngestRunListResponse(BaseModel):
  items: List[IngestRunResponse]


class WBIngestStatusResponse(BaseModel):
    job_code: str
    title: str
    has_schedule: bool
    schedule_summary: Optional[str]  # "каждые 4 часа" или None
    last_run_at: Optional[datetime]  # finished_at последнего успешного/неуспешного run
    last_status: Optional[str]  # "success", "failed", "running", "queued" или None
    is_running: bool  # есть ли активный run (running или queued)


class WBIngestRunRequest(BaseModel):
    """Optional parameters for WB ingestion job run."""
    params_json: Optional[Dict[str, Any]] = None  # e.g., {"date_from": "2024-01-01", "date_to": "2024-01-31"}

