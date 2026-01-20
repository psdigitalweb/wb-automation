"""Marketplaces router with membership checks and secret masking."""

from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, status, Depends, Path, Query

from app.db_marketplaces import (
    ensure_schema,
    seed_marketplaces,
    get_all_marketplaces,
    get_marketplace_by_id,
    get_marketplace_by_code,
    get_project_marketplaces,
    get_project_marketplace,
    create_or_update_project_marketplace,
    update_project_marketplace_settings,
    toggle_project_marketplace,
    delete_project_marketplace,
    mask_secrets,
)
from app.schemas.marketplaces import (
    MarketplaceResponse,
    ProjectMarketplaceCreate,
    ProjectMarketplaceUpdate,
    ProjectMarketplaceResponse,
    ProjectMarketplaceWithMaskedSecrets,
    ToggleRequest,
    WBConnectRequest,
    WBConnectResponse,
    WBMarketplaceStatus,
    WBMarketplaceStatusV2,
    WBCredentialsStatus,
    WBSettingsStatus,
    WBMarketplaceUpdate,
    WBFinancesIngestRequest,
    WBFinancesIngestResponse,
    WBFinanceReportResponse,
)
from app.utils.wb_token_validator import validate_wb_token
from app.deps import (
    get_current_active_user,
    get_project_membership,
    require_project_admin,
)
from app.db_marketplace_tariffs import get_latest_snapshot

router = APIRouter(prefix="/api/v1", tags=["marketplaces"])

# Note: Schema creation and seeding should happen at startup, not at import time
# This prevents DB queries during module import when tables may not exist yet


@router.get("/marketplaces", response_model=List[MarketplaceResponse])
async def get_marketplaces_endpoint(
    active_only: bool = False,
    current_user: dict = Depends(get_current_active_user)
):
    """Get all available marketplaces (reference data)."""
    marketplaces = get_all_marketplaces(active_only=active_only)
    return [
        MarketplaceResponse(
            id=m["id"],
            code=m["code"],
            name=m["name"],
            description=m["description"],
            is_active=m["is_active"],
            created_at=m["created_at"],
            updated_at=m["updated_at"],
        )
        for m in marketplaces
    ]


@router.get("/marketplaces/{marketplace_id}", response_model=MarketplaceResponse)
async def get_marketplace_endpoint(
    marketplace_id: int = Path(..., description="Marketplace ID"),
    current_user: dict = Depends(get_current_active_user)
):
    """Get marketplace by ID."""
    marketplace = get_marketplace_by_id(marketplace_id)
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace not found"
        )
    return MarketplaceResponse(
        id=marketplace["id"],
        code=marketplace["code"],
        name=marketplace["name"],
        description=marketplace["description"],
        is_active=marketplace["is_active"],
        created_at=marketplace["created_at"],
        updated_at=marketplace["updated_at"],
    )


@router.get("/projects/{project_id}/marketplaces", response_model=List[ProjectMarketplaceWithMaskedSecrets])
async def get_project_marketplaces_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)  # Any member can view
):
    """Get all marketplaces for a project. Secrets in settings_json are masked."""
    project_marketplaces = get_project_marketplaces(project_id)
    
    result = []
    for pm in project_marketplaces:
        settings = pm.get("settings_json")
        if settings:
            # Mask secrets
            if isinstance(settings, str):
                import json
                settings = json.loads(settings)
            settings_masked = mask_secrets(settings)
        else:
            settings_masked = None
        
        result.append(ProjectMarketplaceWithMaskedSecrets(
            id=pm["id"],
            project_id=pm["project_id"],
            marketplace_id=pm["marketplace_id"],
            is_enabled=pm["is_enabled"],
            settings_json=settings_masked,
            created_at=pm["created_at"],
            updated_at=pm["updated_at"],
            marketplace_code=pm.get("marketplace_code"),
            marketplace_name=pm.get("marketplace_name"),
            marketplace_description=pm.get("marketplace_description"),
            marketplace_active=pm.get("marketplace_active"),
        ))
    
    return result


@router.get("/projects/{project_id}/marketplaces/wildberries", response_model=WBMarketplaceStatus)
async def get_wb_marketplace_status_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)  # Any member can view
):
    """Get Wildberries marketplace status for a project.
    
    Returns current status: is_enabled, has_token, brand_id, connected.
    Does not return the actual token for security.
    
    NOTE: This route MUST be declared before `/projects/{project_id}/marketplaces/{marketplace_id}`
    to avoid FastAPI treating 'wildberries' as `{marketplace_id}` and returning 422.
    """
    # Get WB marketplace by code
    wb_marketplace = get_marketplace_by_code("wildberries")
    if not wb_marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wildberries marketplace not found in system"
        )
    
    # Get project marketplace connection
    pm = get_project_marketplace(project_id, wb_marketplace["id"])
    
    is_enabled = False
    has_token = False
    brand_id = None
    updated_at = datetime.now()
    
    if pm:
        is_enabled = pm.get("is_enabled", False)
        has_token = bool(pm.get("api_token_encrypted"))
        
        # Read brand_id from settings_json
        settings = pm.get("settings_json")
        if settings:
            if isinstance(settings, str):
                import json
                settings = json.loads(settings)
            
            brand_id_raw = settings.get("brand_id")
            if brand_id_raw is not None:
                try:
                    brand_id = int(brand_id_raw)
                except (ValueError, TypeError):
                    brand_id = None
        
        pm_updated_at = pm.get("updated_at")
        if isinstance(pm_updated_at, datetime):
            updated_at = pm_updated_at
    
    connected = is_enabled and has_token and brand_id is not None and brand_id > 0
    
    return WBMarketplaceStatus(
        is_enabled=is_enabled,
        has_token=has_token,
        brand_id=brand_id,
        connected=connected,
        updated_at=updated_at,
    )


@router.get("/projects/{project_id}/marketplaces/wb", response_model=WBMarketplaceStatusV2)
async def get_wb_marketplace_status_v2_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),  # Any member can view
):
    """Wildberries status (V2).

    Returns booleans describing whether token/brand_id are configured.
    Does NOT return the token value.
    """
    wb_marketplace = get_marketplace_by_code("wildberries")
    if not wb_marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wildberries marketplace not found in system",
        )

    pm = get_project_marketplace(project_id, wb_marketplace["id"])

    is_enabled = bool(pm.get("is_enabled")) if pm else False
    has_token = bool(pm.get("api_token_encrypted")) if pm else False

    brand_id = None
    updated_at = datetime.now()
    if pm:
        settings = pm.get("settings_json")
        if settings:
            if isinstance(settings, str):
                import json
                settings = json.loads(settings)
            brand_id_raw = settings.get("brand_id") if isinstance(settings, dict) else None
            if brand_id_raw is not None:
                try:
                    brand_id = int(brand_id_raw)
                except (ValueError, TypeError):
                    brand_id = None
        pm_updated_at = pm.get("updated_at")
        if isinstance(pm_updated_at, datetime):
            updated_at = pm_updated_at

    is_configured = bool(has_token and brand_id is not None)

    return WBMarketplaceStatusV2(
        is_enabled=is_enabled,
        is_configured=is_configured,
        credentials=WBCredentialsStatus(api_token=has_token),
        settings=WBSettingsStatus(brand_id=brand_id),
        updated_at=updated_at,
    )


@router.put("/projects/{project_id}/marketplaces/wildberries", response_model=WBMarketplaceStatusV2)
async def update_wb_marketplace_endpoint(
    update_data: WBMarketplaceUpdate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can update
):
    """Update Wildberries marketplace settings for a project.
    
    Rules:
    - Never 404 due to missing project_marketplaces row (UPSERT).
    - If is_enabled=false: disables only, does NOT erase token/brand_id.
    - If api_token not provided: do not change api_token_encrypted.
    - brand_id saved to settings_json.brand_id.
    - connected=true only if is_enabled=true AND token exists AND brand_id exists (>0).
    """
    # Get WB marketplace by code
    wb_marketplace = get_marketplace_by_code("wildberries")
    if not wb_marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wildberries marketplace not found in system"
        )
    
    # Validate token if provided
    if update_data.api_token is not None:
        if not update_data.api_token.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="api_token cannot be empty"
            )
        
        # Optionally validate token via API call
        from app.settings import WB_VALIDATE_TOKEN
        if WB_VALIDATE_TOKEN:
            is_valid, error_message = await validate_wb_token(update_data.api_token.strip())
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Token validation failed: {error_message}"
                )
    
    # Get current project marketplace connection (may not exist - that's OK for UPSERT)
    pm = get_project_marketplace(project_id, wb_marketplace["id"])
    
    # Prepare settings_json (merge with existing if any)
    settings_update = None
    if pm and pm.get("settings_json"):
        existing_settings = pm.get("settings_json")
        if isinstance(existing_settings, str):
            import json
            existing_settings = json.loads(existing_settings)
        if isinstance(existing_settings, dict):
            settings_update = {**existing_settings}
    
    if settings_update is None:
        settings_update = {}
    
    # Update brand_id if provided
    if update_data.brand_id is not None:
        settings_update["brand_id"] = update_data.brand_id
    
    # Update api_token_encrypted if provided
    api_token_encrypted = None
    if update_data.api_token is not None:
        from app.utils.secrets_encryption import encrypt_token
        api_token_encrypted = encrypt_token(update_data.api_token.strip())
    
    # UPSERT
    updated_pm = create_or_update_project_marketplace(
        project_id=project_id,
        marketplace_id=wb_marketplace["id"],
        is_enabled=update_data.is_enabled,
        settings_json=settings_update,
        api_token_encrypted=api_token_encrypted
    )
    
    if not updated_pm:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update marketplace connection"
        )
    
    # Prepare response (V2)
    is_enabled = updated_pm.get("is_enabled", False)
    has_token = bool(updated_pm.get("api_token_encrypted"))

    settings = updated_pm.get("settings_json")
    brand_id = None
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        if isinstance(settings, dict):
            brand_id_raw = settings.get("brand_id")
            if brand_id_raw is not None:
                try:
                    brand_id = int(brand_id_raw)
                except (ValueError, TypeError):
                    brand_id = None

    updated_at = updated_pm.get("updated_at")
    if not isinstance(updated_at, datetime):
        updated_at = datetime.now()

    is_configured = bool(has_token and brand_id is not None)

    return WBMarketplaceStatusV2(
        is_enabled=is_enabled,
        is_configured=is_configured,
        credentials=WBCredentialsStatus(api_token=has_token),
        settings=WBSettingsStatus(brand_id=brand_id),
        updated_at=updated_at,
    )


@router.get("/projects/{project_id}/marketplaces/{marketplace_id}", response_model=ProjectMarketplaceWithMaskedSecrets)
async def get_project_marketplace_endpoint(
    project_id: int = Path(..., description="Project ID"),
    marketplace_id: int = Path(..., description="Marketplace ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)  # Any member can view
):
    """Get project-marketplace connection. Secrets in settings_json are masked."""
    pm = get_project_marketplace(project_id, marketplace_id)
    if not pm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project-marketplace connection not found"
        )
    
    marketplace = get_marketplace_by_id(marketplace_id)
    
    settings = pm.get("settings_json")
    if settings:
        # Mask secrets
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        settings_masked = mask_secrets(settings)
    else:
        settings_masked = None
    
    return ProjectMarketplaceWithMaskedSecrets(
        id=pm["id"],
        project_id=pm["project_id"],
        marketplace_id=pm["marketplace_id"],
        is_enabled=pm["is_enabled"],
        settings_json=settings_masked,
        created_at=pm["created_at"],
        updated_at=pm["updated_at"],
        marketplace_code=marketplace["code"] if marketplace else None,
        marketplace_name=marketplace["name"] if marketplace else None,
        marketplace_description=marketplace["description"] if marketplace else None,
        marketplace_active=marketplace["is_active"] if marketplace else None,
    )


@router.post("/projects/{project_id}/marketplaces", response_model=ProjectMarketplaceWithMaskedSecrets, status_code=status.HTTP_201_CREATED)
async def create_project_marketplace_endpoint(
    marketplace_data: ProjectMarketplaceCreate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can add
):
    """Connect marketplace to project. Requires admin or owner role."""
    # Verify marketplace exists
    marketplace = get_marketplace_by_id(marketplace_data.marketplace_id)
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace not found"
        )
    
    pm = create_or_update_project_marketplace(
        project_id=project_id,
        marketplace_id=marketplace_data.marketplace_id,
        is_enabled=marketplace_data.is_enabled,
        settings_json=marketplace_data.settings_json
    )
    
    settings = pm.get("settings_json")
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        settings_masked = mask_secrets(settings)
    else:
        settings_masked = None
    
    return ProjectMarketplaceWithMaskedSecrets(
        id=pm["id"],
        project_id=pm["project_id"],
        marketplace_id=pm["marketplace_id"],
        is_enabled=pm["is_enabled"],
        settings_json=settings_masked,
        created_at=pm["created_at"],
        updated_at=pm["updated_at"],
        marketplace_code=marketplace["code"],
        marketplace_name=marketplace["name"],
        marketplace_description=marketplace["description"],
        marketplace_active=marketplace["is_active"],
    )


@router.put("/projects/{project_id}/marketplaces/{marketplace_id}", response_model=ProjectMarketplaceWithMaskedSecrets)
async def update_project_marketplace_endpoint(
    marketplace_data: ProjectMarketplaceUpdate,
    project_id: int = Path(..., description="Project ID"),
    marketplace_id: int = Path(..., description="Marketplace ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can update
):
    """Update project-marketplace connection. Settings are merged with existing. Requires admin or owner role."""
    pm = get_project_marketplace(project_id, marketplace_id)
    if not pm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project-marketplace connection not found"
        )
    
    # Update settings if provided
    if marketplace_data.settings_json is not None:
        updated_pm = update_project_marketplace_settings(
            project_id=project_id,
            marketplace_id=marketplace_id,
            settings_json=marketplace_data.settings_json
        )
        if updated_pm:
            pm = updated_pm
    
    # Update is_enabled if provided
    if marketplace_data.is_enabled is not None:
        updated_pm = toggle_project_marketplace(
            project_id=project_id,
            marketplace_id=marketplace_id,
            is_enabled=marketplace_data.is_enabled
        )
        if updated_pm:
            pm = updated_pm
    
    marketplace = get_marketplace_by_id(marketplace_id)
    
    settings = pm.get("settings_json")
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        settings_masked = mask_secrets(settings)
    else:
        settings_masked = None
    
    return ProjectMarketplaceWithMaskedSecrets(
        id=pm["id"],
        project_id=pm["project_id"],
        marketplace_id=pm["marketplace_id"],
        is_enabled=pm["is_enabled"],
        settings_json=settings_masked,
        created_at=pm["created_at"],
        updated_at=pm["updated_at"],
        marketplace_code=marketplace["code"] if marketplace else None,
        marketplace_name=marketplace["name"] if marketplace else None,
        marketplace_description=marketplace["description"] if marketplace else None,
        marketplace_active=marketplace["is_active"] if marketplace else None,
    )


@router.patch("/projects/{project_id}/marketplaces/{marketplace_id}/toggle", response_model=ProjectMarketplaceWithMaskedSecrets)
async def toggle_project_marketplace_endpoint(
    toggle_data: ToggleRequest,
    project_id: int = Path(..., description="Project ID"),
    marketplace_id: int = Path(..., description="Marketplace ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can toggle
):
    """Enable or disable marketplace for a project. Requires admin or owner role.
    
    Uses UPSERT - creates connection if it doesn't exist.
    For Wildberries, prefer using PUT /wildberries endpoint instead.
    """
    # Get marketplace info to check if it's Wildberries
    marketplace = get_marketplace_by_id(marketplace_id)
    if not marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace not found"
        )
    
    # For Wildberries, redirect to UPSERT instead of toggle
    if marketplace.get("code") == "wildberries":
        # Use create_or_update_project_marketplace for UPSERT
        pm = create_or_update_project_marketplace(
            project_id=project_id,
            marketplace_id=marketplace_id,
            is_enabled=toggle_data.is_enabled,
            settings_json=None,  # Don't change settings
            api_token_encrypted=None  # Don't change token
        )
    else:
        # For other marketplaces, use toggle (which now does UPSERT too)
        pm = toggle_project_marketplace(
            project_id=project_id,
            marketplace_id=marketplace_id,
            is_enabled=toggle_data.is_enabled
        )
        if not pm:
            # If toggle returned None, try UPSERT
            pm = create_or_update_project_marketplace(
                project_id=project_id,
                marketplace_id=marketplace_id,
                is_enabled=toggle_data.is_enabled
            )
    
    marketplace = get_marketplace_by_id(marketplace_id)
    
    settings = pm.get("settings_json")
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        settings_masked = mask_secrets(settings)
    else:
        settings_masked = None
    
    return ProjectMarketplaceWithMaskedSecrets(
        id=pm["id"],
        project_id=pm["project_id"],
        marketplace_id=pm["marketplace_id"],
        is_enabled=pm["is_enabled"],
        settings_json=settings_masked,
        created_at=pm["created_at"],
        updated_at=pm["updated_at"],
        marketplace_code=marketplace["code"] if marketplace else None,
        marketplace_name=marketplace["name"] if marketplace else None,
        marketplace_description=marketplace["description"] if marketplace else None,
        marketplace_active=marketplace["is_active"] if marketplace else None,
    )


@router.delete("/projects/{project_id}/marketplaces/{marketplace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_marketplace_endpoint(
    project_id: int = Path(..., description="Project ID"),
    marketplace_id: int = Path(..., description="Marketplace ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can delete
):
    """Remove marketplace from project. Requires admin or owner role."""
    deleted = delete_project_marketplace(project_id, marketplace_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project-marketplace connection not found"
        )
    return None


@router.post("/projects/{project_id}/marketplaces/wb/connect", response_model=WBConnectResponse)
async def connect_wb_marketplace_endpoint(
    connect_data: WBConnectRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can connect
):
    """Connect Wildberries marketplace to project with API token validation.
    
    Validates the token by making a test request to WB API before saving.
    Requires admin or owner role.
    """
    # Get WB marketplace by code
    wb_marketplace = get_marketplace_by_code("wildberries")
    if not wb_marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wildberries marketplace not found in system"
        )
    
    # Validate token
    is_valid, error_message = await validate_wb_token(connect_data.api_key)
    if not is_valid:
        return WBConnectResponse(
            success=False,
            message=f"Token validation failed: {error_message}",
            project_marketplace=None
        )
    
    # Encrypt token
    from app.utils.secrets_encryption import encrypt_token
    encrypted_token = encrypt_token(connect_data.api_key)
    
    # Save connection: token in api_token_encrypted, settings_json without token
    settings_json = {
        "base_url": "https://content-api.wildberries.ru",
        "timeout": 30,
    }
    
    pm = create_or_update_project_marketplace(
        project_id=project_id,
        marketplace_id=wb_marketplace["id"],
        is_enabled=True,  # Enable automatically on successful connect
        settings_json=settings_json,
        api_token_encrypted=encrypted_token
    )
    
    # settings_json doesn't contain token, no need to mask
    settings_masked = settings_json
    
    return WBConnectResponse(
        success=True,
        message="Wildberries marketplace connected successfully",
        project_marketplace=ProjectMarketplaceWithMaskedSecrets(
            id=pm["id"],
            project_id=pm["project_id"],
            marketplace_id=pm["marketplace_id"],
            is_enabled=pm["is_enabled"],
            settings_json=settings_masked,
            created_at=pm["created_at"],
            updated_at=pm["updated_at"],
            marketplace_code=wb_marketplace["code"],
            marketplace_name=wb_marketplace["name"],
            marketplace_description=wb_marketplace["description"],
            marketplace_active=wb_marketplace["is_active"],
        )
    )


@router.post("/projects/{project_id}/marketplaces/wb/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_wb_marketplace_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can disconnect
):
    """Disconnect Wildberries marketplace from project.
    
    Disables the marketplace and clears the API token from settings.
    Requires admin or owner role.
    """
    # Get WB marketplace by code
    wb_marketplace = get_marketplace_by_code("wildberries")
    if not wb_marketplace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wildberries marketplace not found in system"
        )
    
    # Disable marketplace (clear token by setting is_enabled=False and clearing settings)
    pm = toggle_project_marketplace(
        project_id=project_id,
        marketplace_id=wb_marketplace["id"],
        is_enabled=False
    )
    
    if pm:
        # Clear encrypted token and settings
        from sqlalchemy import text
        from app.db import engine
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE project_marketplaces
                    SET api_token_encrypted = NULL, settings_json = '{}'::jsonb, updated_at = now()
                    WHERE project_id = :project_id AND marketplace_id = :marketplace_id
                """),
                {
                    "project_id": project_id,
                    "marketplace_id": wb_marketplace["id"],
                }
            )
    
    return None


@router.get("/marketplaces/wildberries/tariffs/latest")
async def get_wb_tariffs_latest(
    type: str = Query(..., regex="^(commission|box|pallet|return|acceptance_coefficients)$"),
    date_param: Optional[date] = Query(
        None,
        alias="date",
        description="Date for box/pallet/return tariffs (YYYY-MM-DD, UTC)",
    ),
    locale: Optional[str] = Query(
        None,
        description="Locale for commission tariffs (e.g. 'ru')",
    ),
    current_user: dict = Depends(get_current_active_user),
):
    """Return latest WB tariffs snapshot for given type/date/locale.

    This is marketplace-level data (not project-scoped).
    """
    data_type = type

    # Validate parameter combinations
    if data_type in {"box", "pallet", "return"} and date_param is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'date' is required for box/pallet/return tariffs",
        )
    if data_type == "commission":
        if locale is None:
            locale = "ru"
        date_for_query = None
    elif data_type == "acceptance_coefficients":
        date_for_query = None
        locale = None
    else:
        # box / pallet / return
        date_for_query = date_param
        locale = None

    snapshot = get_latest_snapshot(
        marketplace_code="wildberries",
        data_domain="tariffs",
        data_type=data_type,
        as_of_date=date_for_query,
        locale=locale,
    )

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tariffs snapshot not found",
        )

    return {
        "fetched_at": snapshot["fetched_at"],
        "request_params": snapshot.get("request_params"),
        "payload": snapshot.get("payload"),
        "http_status": snapshot.get("http_status"),
        "error": snapshot.get("error"),
    }


# WB Finances endpoints
@router.post(
    "/projects/{project_id}/marketplaces/wildberries/finances/ingest",
    response_model=WBFinancesIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start WB finances ingestion",
    description=(
        "Enqueue Celery task to ingest Wildberries finance reports (project-level). "
        "Requires project membership. WB must be connected with token."
    ),
)
async def start_wb_finances_ingest(
    body: WBFinancesIngestRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),  # Any member can trigger ingestion
):
    """Start WB finances ingestion for a project and date range."""
    from app.tasks.wb_finances import ingest_wb_finance_reports_by_period_task
    from app.utils.get_project_marketplace_token import get_wb_credentials_for_project

    # Check if WB is connected and has token
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if not credentials or not credentials.get("token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WB not connected or token missing. Please configure Wildberries in project marketplaces first.",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Validate date format
    try:
        from datetime import datetime
        datetime.strptime(body.date_from, "%Y-%m-%d")
        datetime.strptime(body.date_to, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    # Start Celery task
    try:
        result = ingest_wb_finance_reports_by_period_task.delay(
            project_id=project_id,
            date_from=body.date_from,
            date_to=body.date_to,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ingestion task: {str(e)}",
        )

    return WBFinancesIngestResponse(
        status="started",
        task_id=getattr(result, "id", None),
        date_from=body.date_from,
        date_to=body.date_to,
    )


@router.get(
    "/projects/{project_id}/marketplaces/wildberries/finances/reports",
    response_model=List[WBFinanceReportResponse],
    summary="List WB finance reports",
    description="Get list of finance reports for a project, sorted by last_seen_at desc.",
)
async def list_wb_finances_reports(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),  # Any member can view
):
    """List all finance reports for a project."""
    from app.db_wb_finances import list_reports

    reports = list_reports(project_id=project_id, marketplace_code="wildberries")
    
    return [
        WBFinanceReportResponse(
            report_id=r["report_id"],
            period_from=r["period_from"],
            period_to=r["period_to"],
            currency=r["currency"],
            total_amount=float(r["total_amount"]) if r["total_amount"] is not None else None,
            rows_count=r["rows_count"],
            first_seen_at=r["first_seen_at"],
            last_seen_at=r["last_seen_at"],
        )
        for r in reports
    ]

