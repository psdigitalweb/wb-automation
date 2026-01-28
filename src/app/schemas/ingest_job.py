from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class IngestJobResponse(BaseModel):
    job_code: str
    title: str
    source_code: Literal["wildberries", "internal"]
    supports_schedule: bool
    supports_manual: bool

