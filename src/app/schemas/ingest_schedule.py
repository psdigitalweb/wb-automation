from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.services.scheduling.cron import DEFAULT_TIMEZONE


class IngestScheduleBase(BaseModel):
  marketplace_code: str = Field(..., description="Marketplace code (e.g. 'wildberries')")
  job_code: str = Field(..., description="Job code (e.g. 'warehouses', 'stocks', 'prices')")
  cron_expr: str = Field(..., description="5-field cron expression")
  timezone: str = Field(
      DEFAULT_TIMEZONE,
      description="IANA timezone name used to compute next_run_at",
  )
  is_enabled: bool = Field(True, description="Whether schedule is active")


class IngestScheduleCreate(IngestScheduleBase):
  pass


class IngestScheduleUpdate(BaseModel):
  cron_expr: Optional[str] = Field(None, description="New cron expression")
  timezone: Optional[str] = Field(None, description="New timezone")
  is_enabled: Optional[bool] = Field(None, description="Enable/disable schedule")


class IngestScheduleResponse(IngestScheduleBase):
  id: int
  project_id: int
  next_run_at: Optional[datetime] = None
  created_at: datetime
  updated_at: datetime

  class Config:
      from_attributes = True

