"""Helper to get marketplace API credentials from project_marketplaces for ingestion."""

from typing import Optional, TypedDict

from sqlalchemy import text

from app.db import engine
from app.utils.secrets_encryption import decrypt_token


class WBCredentials(TypedDict):
    token: str
    brand_id: Optional[int]


def get_wb_api_token_for_project(project_id: int) -> Optional[str]:
    """Return the required cabinet API token without storefront settings.

    A missing or disabled marketplace connection returns ``None`` so legacy
    callers may use their existing environment fallback. An enabled connection
    must contain a usable token; storefront configuration is intentionally not
    considered here.
    """
    pm = _get_project_marketplace_by_code(project_id, "wildberries")
    if not pm or not pm.get("is_enabled", False):
        return None

    return _get_required_wb_token(pm)


def get_wb_credentials_for_project(project_id: int) -> Optional[WBCredentials]:
    """Compatibility adapter returning token plus optional legacy brand ID.
    
    Reads token from api_token_encrypted field and brand_id from settings_json.brand_id.
    
    Args:
        project_id: Project ID to get credentials for.
    
    Returns:
        Dict with required ``token`` and optional ``brand_id`` keys if found and
        enabled, None if not enabled or not found.
        
    Raises:
        ValueError: If marketplace is enabled but its token is missing or cannot
        be decrypted.
    """
    pm = _get_project_marketplace_by_code(project_id, "wildberries")
    
    if not pm:
        return None  # No marketplace connection exists - can use env fallback
    
    if not pm.get("is_enabled", False):
        return None  # Marketplace disabled - can use env fallback
    
    token = _get_required_wb_token(pm)
    
    # Read brand_id from settings_json
    settings = pm.get("settings_json")
    brand_id = None
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        
        brand_id = settings.get("brand_id")
        if brand_id is not None:
            try:
                brand_id = int(brand_id)
            except (ValueError, TypeError):
                brand_id = None
    
    return {
        "token": token,
        "brand_id": brand_id
    }


def _get_required_wb_token(pm: dict) -> str:
    encrypted_token = pm.get("api_token_encrypted")
    token = decrypt_token(encrypted_token) if encrypted_token else None
    if token and token.upper() == "MOCK":
        token = None

    if not token:
        settings = pm.get("settings_json")
        if settings:
            if isinstance(settings, str):
                import json

                settings = json.loads(settings)
            token = settings.get("api_token") or settings.get("token")
            if token and (token == "***" or token.upper() == "MOCK"):
                token = None

    if encrypted_token and not token:
        raise ValueError("WB token is saved but cannot be decrypted (check PROJECT_SECRETS_KEY)")
    if not token:
        raise ValueError("WB not connected")
    return str(token)


def get_wb_analytics_token_for_project(project_id: int) -> Optional[str]:
    """Get WB Analytics API token for project.

    Reads settings_json.analytics_token first (Analytics category token).
    Fallback: api_token_encrypted (main WB token).
    Returns None if marketplace disabled or no token.
    """
    pm = _get_project_marketplace_by_code(project_id, "wildberries")
    if not pm or not pm.get("is_enabled", False):
        return None

    # settings_json.analytics_token (Analytics category) first
    settings = pm.get("settings_json")
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        analytics_token = settings.get("analytics_token")
        if analytics_token and analytics_token != "***" and analytics_token.upper() != "MOCK":
            return analytics_token

    # Fallback: api_token_encrypted
    return get_wb_token_for_project(project_id)


def get_wb_token_for_project(project_id: int) -> Optional[str]:
    """Get Wildberries API token for project (no brand_id check).

    For APIs that only need token (e.g. WB Communications).
    Returns token from project_marketplaces for wildberries if enabled.
    """
    pm = _get_project_marketplace_by_code(project_id, "wildberries")
    if not pm or not pm.get("is_enabled", False):
        return None

    # api_token_encrypted first
    encrypted_token = pm.get("api_token_encrypted")
    if encrypted_token:
        try:
            token = decrypt_token(encrypted_token)
            if token and token.upper() != "MOCK":
                return token
        except Exception:
            pass

    # fallback settings_json
    settings = pm.get("settings_json")
    if settings:
        if isinstance(settings, str):
            import json
            settings = json.loads(settings)
        token = settings.get("api_token") or settings.get("token")
        if token and token != "***" and token.upper() != "MOCK":
            return token
    return None


def _get_project_marketplace_by_code(project_id: int, marketplace_code: str) -> Optional[dict]:
    """Get project marketplace connection by project_id and marketplace code.
    
    Args:
        project_id: Project ID.
        marketplace_code: Marketplace code (e.g., "wildberries").
    
    Returns:
        Project marketplace dict or None if not found.
    """
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 
                    pm.id, pm.project_id, pm.marketplace_id, pm.is_enabled, 
                    pm.settings_json, pm.api_token_encrypted, pm.created_at, pm.updated_at,
                    m.code, m.name, m.description, m.is_active as marketplace_active
                FROM project_marketplaces pm
                INNER JOIN marketplaces m ON pm.marketplace_id = m.id
                WHERE pm.project_id = :project_id AND m.code = :marketplace_code
                LIMIT 1
            """),
            {
                "project_id": project_id,
                "marketplace_code": marketplace_code,
            }
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "project_id": row[1],
                "marketplace_id": row[2],
                "is_enabled": row[3],
                "settings_json": row[4],
                "api_token_encrypted": row[5],
                "created_at": row[6],
                "updated_at": row[7],
                "marketplace_code": row[8],
                "marketplace_name": row[9],
                "marketplace_description": row[10],
                "marketplace_active": row[11],
            }
        return None

