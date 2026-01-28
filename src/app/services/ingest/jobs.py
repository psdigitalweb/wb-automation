from __future__ import annotations

from typing import List

from app.schemas.ingest_job import IngestJobResponse
from app.services.ingest.registry import list_job_definitions


def list_jobs() -> List[IngestJobResponse]:
    """
    Return all registered ingestion jobs with metadata for UI / validation.
    """
    return [IngestJobResponse(**job_def) for job_def in list_job_definitions()]

