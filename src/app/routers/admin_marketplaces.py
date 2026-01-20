"""Admin endpoints for marketplace-level operations (e.g. WB tariffs)."""

from typing import Any

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import ProgrammingError

from app.deps import get_current_superuser
from app.db_marketplace_tariffs import get_tariffs_status
from app.schemas.marketplaces import (
    WBTariffsIngestRequest,
    WBTariffsIngestResponse,
    WBTariffsStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-marketplaces"])


@router.post(
    "/marketplaces/wildberries/tariffs/ingest",
    response_model=WBTariffsIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start WB tariffs ingestion",
    description=(
        "Enqueue Celery task to ingest Wildberries tariffs (marketplace-level, not project-scoped). "
        "Requires superuser permissions. Does not wait for task completion."
    ),
)
async def start_wb_tariffs_ingest(
    body: WBTariffsIngestRequest,
    current_user: dict = Depends(get_current_superuser),
) -> WBTariffsIngestResponse:
    """Admin-only endpoint to start WB tariffs ingestion asynchronously.

    If the underlying schema (e.g. marketplace_api_snapshots) is missing,
    returns HTTP 503 with a clear instruction instead of propagating a 500.
    """
    from app.tasks.wb_tariffs import ingest_wb_tariffs_all_task

    days_ahead = body.days_ahead

    try:
        result: Any = ingest_wb_tariffs_all_task.delay(days_ahead=days_ahead)
    except ProgrammingError as exc:  # pragma: no cover - defensive, unlikely here
        logger.error("Failed to enqueue WB tariffs ingestion task due to DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Database schema not migrated for WB tariffs. "
                "Required table 'marketplace_api_snapshots' may be missing. "
                "Please run Alembic migrations (e.g. 'alembic upgrade head')."
            ),
        ) from exc

    user_id = current_user.get("id")
    username = current_user.get("username")
    email = current_user.get("email")

    logger.info(
        "WB tariffs ingestion started by user id=%s username=%s email=%s days_ahead=%s task_id=%s",
        user_id,
        username,
        email,
        days_ahead,
        getattr(result, "id", None),
    )

    return WBTariffsIngestResponse(
        status="started",
        days_ahead=days_ahead,
        task="ingest_wb_tariffs_all",
        task_id=getattr(result, "id", None),
    )


@router.get(
    "/marketplaces/wildberries/tariffs/status",
    response_model=WBTariffsStatusResponse,
    summary="Get WB tariffs latest snapshots status",
    description=(
        "Return aggregated status for marketplace-level WB tariffs snapshots "
        "(latest fetched_at overall and per data_type). Requires superuser permissions."
    ),
)
async def get_wb_tariffs_status(
    _: dict = Depends(get_current_superuser),
) -> WBTariffsStatusResponse:
    """Admin-only endpoint returning latest WB tariffs snapshots status.

    If the underlying schema (e.g. marketplace_api_snapshots) is missing,
    returns HTTP 503 with a clear instruction instead of propagating a 500.
    """
    try:
        status_data = get_tariffs_status(marketplace_code="wildberries", data_domain="tariffs")
    except ProgrammingError as exc:
        logger.error("Failed to load WB tariffs status due to DB error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Database schema not migrated for WB tariffs. "
                "Required table 'marketplace_api_snapshots' may be missing. "
                "Please run Alembic migrations (e.g. 'alembic upgrade head')."
            ),
        ) from exc

    return WBTariffsStatusResponse(**status_data)

