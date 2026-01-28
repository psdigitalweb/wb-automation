"""Admin endpoints for marketplace-level operations (e.g. WB tariffs)."""

from typing import Any, List

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.exc import ProgrammingError

from app.deps import get_current_superuser
from app.db_marketplace_tariffs import get_tariffs_status
from app.db_marketplaces import (
    get_all_marketplaces,
    get_system_marketplace_settings_map,
    upsert_system_marketplace_settings,
)
from app.schemas.marketplaces import (
    WBTariffsIngestRequest,
    WBTariffsIngestResponse,
    WBTariffsStatusResponse,
    SystemMarketplaceSettingsResponse,
    SystemMarketplaceSettingsUpdate,
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


@router.get(
    "/system-marketplaces",
    response_model=List[SystemMarketplaceSettingsResponse],
    summary="Get all system marketplace settings",
    description=(
        "Returns system settings for all marketplaces from the marketplaces table. "
        "If a marketplace has no record in system_marketplace_settings, returns defaults "
        "(enabled=true, visible=true, sort_order=100). Requires superuser permissions."
    ),
)
async def get_system_marketplace_settings_list(
    _: dict = Depends(get_current_superuser),
) -> List[SystemMarketplaceSettingsResponse]:
    """Get system marketplace settings for all marketplaces.
    
    Returns settings for all marketplace codes from the marketplaces table.
    If no record exists in system_marketplace_settings, returns defaults.
    """
    # Get all marketplaces (source of truth for marketplace codes)
    all_marketplaces = get_all_marketplaces(active_only=False)
    
    # Get system settings map
    settings_map = get_system_marketplace_settings_map()
    
    # Build response list
    result = []
    for mp in all_marketplaces:
        mp_code = mp["code"]
        system_settings = settings_map.get(mp_code)
        
        if system_settings:
            # Record exists
            result.append(SystemMarketplaceSettingsResponse(
                marketplace_code=mp_code,
                display_name=mp.get("name"),
                is_globally_enabled=system_settings["is_globally_enabled"],
                is_visible=system_settings["is_visible"],
                sort_order=system_settings["sort_order"],
                settings_json=system_settings["settings_json"] if isinstance(system_settings["settings_json"], dict) 
                            else (system_settings["settings_json"] if isinstance(system_settings["settings_json"], str) 
                                  else {}),
                has_record=True,
                created_at=system_settings.get("created_at"),
                updated_at=system_settings.get("updated_at"),
            ))
        else:
            # No record, return defaults
            result.append(SystemMarketplaceSettingsResponse(
                marketplace_code=mp_code,
                display_name=mp.get("name"),
                is_globally_enabled=True,
                is_visible=True,
                sort_order=100,
                settings_json={},
                has_record=False,
                created_at=None,
                updated_at=None,
            ))
    
    # Sort by sort_order, then by marketplace_code
    result.sort(key=lambda x: (x.sort_order, x.marketplace_code))
    
    return result


@router.put(
    "/system-marketplaces/{marketplace_code}",
    response_model=SystemMarketplaceSettingsResponse,
    summary="Update system marketplace settings",
    description=(
        "Create or update system marketplace settings for a marketplace. "
        "Validates that marketplace_code exists in marketplaces table. "
        "Requires superuser permissions."
    ),
)
async def update_system_marketplace_settings(
    marketplace_code: str = Path(..., description="Marketplace code"),
    update_data: SystemMarketplaceSettingsUpdate = ...,
    _: dict = Depends(get_current_superuser),
) -> SystemMarketplaceSettingsResponse:
    """Update system marketplace settings (UPSERT).
    
    Validates that marketplace_code exists in marketplaces table.
    If not, returns 400 Bad Request.
    """
    # Validate marketplace_code exists
    from app.db_marketplaces import get_marketplace_by_code
    marketplace = get_marketplace_by_code(marketplace_code)
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Marketplace code '{marketplace_code}' not found in marketplaces table"
        )
    
    # Prepare update dict (only include non-None fields)
    update_dict = {}
    if update_data.is_globally_enabled is not None:
        update_dict["is_globally_enabled"] = update_data.is_globally_enabled
    if update_data.is_visible is not None:
        update_dict["is_visible"] = update_data.is_visible
    if update_data.sort_order is not None:
        update_dict["sort_order"] = update_data.sort_order
    if update_data.settings_json is not None:
        update_dict["settings_json"] = update_data.settings_json
    
    # UPSERT
    updated_settings = upsert_system_marketplace_settings(
        marketplace_code=marketplace_code,
        **update_dict
    )
    
    # Parse settings_json if it's a string
    settings_json = updated_settings["settings_json"]
    if isinstance(settings_json, str):
        import json
        settings_json = json.loads(settings_json)
    elif not isinstance(settings_json, dict):
        settings_json = {}
    
    return SystemMarketplaceSettingsResponse(
        marketplace_code=updated_settings["marketplace_code"],
        display_name=marketplace.get("name"),
        is_globally_enabled=updated_settings["is_globally_enabled"],
        is_visible=updated_settings["is_visible"],
        sort_order=updated_settings["sort_order"],
        settings_json=settings_json,
        has_record=True,
        created_at=updated_settings.get("created_at"),
        updated_at=updated_settings.get("updated_at"),
    )

