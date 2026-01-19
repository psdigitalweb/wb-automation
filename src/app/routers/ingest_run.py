from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from app.deps import get_current_active_user, get_project_membership
from app.tasks.ingestion import (
    ingest_prices_task,
    ingest_supplier_stocks_task,
    ingest_products_task,
    ingest_stocks_task,
    ingest_warehouses_task,
    ingest_frontend_prices_task,
    ingest_rrp_xml_task,
)


IngestDomain = Literal[
    "products",
    "warehouses",
    "stocks",
    "supplier_stocks",
    "prices",
    "frontend_prices",
    "rrp_xml",
]


class IngestRunRequest(BaseModel):
    domain: IngestDomain = Field(..., description="Ingestion domain to enqueue")


class IngestRunResponse(BaseModel):
    task_id: str
    domain: IngestDomain
    status: Literal["queued"]


router = APIRouter(prefix="/api/v1/projects", tags=["ingest-run"])


@router.post("/{project_id}/ingest/run", response_model=IngestRunResponse)
async def run_ingest(
    body: IngestRunRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    if body.domain == "prices":
        result = ingest_prices_task.delay(project_id)
    elif body.domain == "supplier_stocks":
        result = ingest_supplier_stocks_task.delay(project_id)
    elif body.domain == "products":
        result = ingest_products_task.delay(project_id)
    elif body.domain == "stocks":
        result = ingest_stocks_task.delay(project_id)
    elif body.domain == "warehouses":
        result = ingest_warehouses_task.delay(project_id)
    elif body.domain == "frontend_prices":
        result = ingest_frontend_prices_task.delay(project_id)
    elif body.domain == "rrp_xml":
        result = ingest_rrp_xml_task.delay(project_id)
    else:
        # Literal should prevent this, but keep it safe.
        raise ValueError(f"Unsupported domain: {body.domain}")

    return IngestRunResponse(task_id=result.id, domain=body.domain, status="queued")

