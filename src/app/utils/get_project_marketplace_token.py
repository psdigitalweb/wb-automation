"""Helper to get marketplace API credentials from project_marketplaces for ingestion."""

from typing import Optional, Dict
from sqlalchemy import text
from app.db import engine
from app.utils.secrets_encryption import decrypt_token

def get_wb_credentials_for_project(project_id: int) -> Optional[Dict[str, any]]:
    """Get Wildberries API credentials (token + brand_id) from project_marketplaces for a specific project.
    
    Reads token from api_token_encrypted field and brand_id from settings_json.brand_id.
    
    Args:
        project_id: Project ID to get credentials for.
    
    Returns:
        Dict with 'token' and 'brand_id' keys if found and enabled, None if not enabled or not found.
        
    Raises:
        ValueError: If marketplace is enabled but missing token or brand_id (not connected).
    """
    # Get project marketplace connection for wildberries
    pm = _get_project_marketplace_by_code(project_id, "wildberries")
    
    if not pm:
        return None  # No marketplace connection exists - can use env fallback
    
    if not pm.get("is_enabled", False):
        return None  # Marketplace disabled - can use env fallback
    
    # Read token from api_token_encrypted (preferred)
    encrypted_token = pm.get("api_token_encrypted")
    token = None
    if encrypted_token:
        token = decrypt_token(encrypted_token)
        if token and token.upper() == "MOCK":
            token = None
    
    # Fallback: try settings_json for backward compatibility
    if not token:
        settings = pm.get("settings_json")
        if settings:
            if isinstance(settings, str):
                import json
                settings = json.loads(settings)
            
            token = settings.get("api_token") or settings.get("token")
            if token and token == "***":
                token = None
            elif token and token.upper() == "MOCK":
                token = None
    
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
    
    # If enabled but missing credentials, raise error with actionable detail.
    if encrypted_token and not token:
        # Token exists in DB but couldn't be decrypted (usually missing/mismatched PROJECT_SECRETS_KEY).
        raise ValueError("WB token is saved but cannot be decrypted (check PROJECT_SECRETS_KEY)")
    if not token or not brand_id:
        raise ValueError("WB not connected")
    
    return {
        "token": token,
        "brand_id": brand_id
    }


def get_wb_token_for_project(project_id: int) -> Optional[str]:
    """Get Wildberries API token from project_marketplaces for a specific project.
    
    DEPRECATED: Use get_wb_credentials_for_project instead.
    This function is kept for backward compatibility.
    
    Reads from api_token_encrypted field and decrypts it.
    
    Args:
        project_id: Project ID to get token for.
    
    Returns:
        API token string if found and enabled, None otherwise.
    """
    try:
        credentials = get_wb_credentials_for_project(project_id)
        return credentials.get("token")
    except ValueError:
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

