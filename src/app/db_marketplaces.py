"""Database helpers for marketplaces and project-marketplace connections.

This module provides:
- ensure_schema(): idempotently creates the `marketplaces` and `project_marketplaces` tables
- Marketplace CRUD operations
- ProjectMarketplace CRUD operations
- Secret masking utilities
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import json
from sqlalchemy import text

# Import engine from db module
from app.db import engine


# Fields that should be masked (secrets)
SECRET_FIELDS = [
    "token", "api_key", "api_secret", "secret_key", "password",
    "access_token", "refresh_token", "private_key", "client_secret"
]


def mask_secrets(data: Dict[str, Any], secret_fields: List[str] = None) -> Dict[str, Any]:
    """Mask secret fields in a dictionary.
    
    Args:
        data: Dictionary to mask
        secret_fields: List of field names to mask (defaults to SECRET_FIELDS)
    
    Returns:
        Dictionary with masked secrets (values replaced with "***")
    """
    if secret_fields is None:
        secret_fields = SECRET_FIELDS
    
    if not isinstance(data, dict):
        return data
    
    masked = {}
    for key, value in data.items():
        key_lower = key.lower()
        # Check if any secret field matches (case-insensitive)
        if any(secret_field.lower() in key_lower for secret_field in secret_fields):
            masked[key] = "***"
        elif isinstance(value, dict):
            masked[key] = mask_secrets(value, secret_fields)
        elif isinstance(value, list):
            masked[key] = [
                mask_secrets(item, secret_fields) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            masked[key] = value
    
    return masked


def ensure_schema() -> None:
    """Create `marketplaces` and `project_marketplaces` tables and indexes if they do not exist.
    
    WARNING: This function is for development only. In production, use Alembic migrations.
    Only runs if ENABLE_RUNTIME_SCHEMA_CREATION=true in environment.
    
    This function is idempotent and may be safely executed multiple times.
    """
    import os
    # Only run in development mode
    if not os.getenv("ENABLE_RUNTIME_SCHEMA_CREATION", "false").lower() in ("true", "1", "yes"):
        return
    create_marketplaces_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS marketplaces (
            id              SERIAL PRIMARY KEY,
            code            VARCHAR(50) UNIQUE NOT NULL,
            name            VARCHAR(255) NOT NULL,
            description     TEXT,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    
    create_project_marketplaces_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS project_marketplaces (
            id              SERIAL PRIMARY KEY,
            project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            marketplace_id  INTEGER NOT NULL REFERENCES marketplaces(id) ON DELETE CASCADE,
            is_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
            settings_json   JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(project_id, marketplace_id)
        );
        """
    )
    
    create_indexes_sql = [
        text("CREATE INDEX IF NOT EXISTS idx_marketplaces_code ON marketplaces(code);"),
        text("CREATE INDEX IF NOT EXISTS idx_marketplaces_active ON marketplaces(is_active);"),
        text("CREATE INDEX IF NOT EXISTS idx_project_marketplaces_project_id ON project_marketplaces(project_id);"),
        text("CREATE INDEX IF NOT EXISTS idx_project_marketplaces_marketplace_id ON project_marketplaces(marketplace_id);"),
        text("CREATE INDEX IF NOT EXISTS idx_project_marketplaces_enabled ON project_marketplaces(is_enabled);"),
    ]
    
    with engine.begin() as conn:
        conn.execute(create_marketplaces_table_sql)
        conn.execute(create_project_marketplaces_table_sql)
        for idx_sql in create_indexes_sql:
            conn.execute(idx_sql)
    
    print("db_marketplaces: marketplaces and project_marketplaces schema ensured")


def seed_marketplaces() -> None:
    """Seed initial marketplace data."""
    marketplaces_data = [
        {
            "code": "wildberries",
            "name": "Wildberries",
            "description": "Крупнейший маркетплейс в России",
            "is_active": True,
        },
        {
            "code": "ozon",
            "name": "Ozon",
            "description": "Один из крупнейших маркетплейсов в России",
            "is_active": True,
        },
        {
            "code": "yandex_market",
            "name": "Яндекс.Маркет",
            "description": "Маркетплейс от Яндекса",
            "is_active": True,
        },
        {
            "code": "sbermegamarket",
            "name": "СберМегаМаркет",
            "description": "Маркетплейс от Сбера",
            "is_active": True,
        },
    ]
    
    with engine.begin() as conn:
        for mp_data in marketplaces_data:
            conn.execute(
                text("""
                    INSERT INTO marketplaces (code, name, description, is_active)
                    VALUES (:code, :name, :description, :is_active)
                    ON CONFLICT (code) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        is_active = EXCLUDED.is_active,
                        updated_at = now()
                """),
                mp_data
            )
    
    print(f"db_marketplaces: seeded {len(marketplaces_data)} marketplaces")


def get_marketplace_by_id(marketplace_id: int) -> Optional[dict]:
    """Get marketplace by ID."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, code, name, description, is_active, created_at, updated_at
                FROM marketplaces
                WHERE id = :marketplace_id
            """),
            {"marketplace_id": marketplace_id}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "description": row[3],
                "is_active": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
        return None


def get_marketplace_by_code(code: str) -> Optional[dict]:
    """Get marketplace by code."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, code, name, description, is_active, created_at, updated_at
                FROM marketplaces
                WHERE code = :code
            """),
            {"code": code}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "description": row[3],
                "is_active": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
        return None


def get_all_marketplaces(active_only: bool = False) -> List[dict]:
    """Get all marketplaces."""
    with engine.connect() as conn:
        query = "SELECT id, code, name, description, is_active, created_at, updated_at FROM marketplaces"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY name"
        
        result = conn.execute(text(query))
        marketplaces = []
        for row in result:
            marketplaces.append({
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "description": row[3],
                "is_active": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            })
        return marketplaces


def get_project_marketplace(project_id: int, marketplace_id: int) -> Optional[dict]:
    """Get project-marketplace connection."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, project_id, marketplace_id, is_enabled, settings_json, api_token_encrypted, created_at, updated_at
                FROM project_marketplaces
                WHERE project_id = :project_id AND marketplace_id = :marketplace_id
            """),
            {
                "project_id": project_id,
                "marketplace_id": marketplace_id,
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
            }
        return None


def get_project_marketplaces(project_id: int) -> List[dict]:
    """Get all marketplaces for a project."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 
                    pm.id, pm.project_id, pm.marketplace_id, pm.is_enabled, 
                    pm.settings_json, pm.api_token_encrypted, pm.created_at, pm.updated_at,
                    m.code, m.name, m.description, m.is_active as marketplace_active
                FROM project_marketplaces pm
                INNER JOIN marketplaces m ON pm.marketplace_id = m.id
                WHERE pm.project_id = :project_id
                ORDER BY m.name
            """),
            {"project_id": project_id}
        )
        marketplaces = []
        for row in result:
            marketplaces.append({
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
            })
        return marketplaces


def create_or_update_project_marketplace(
    project_id: int,
    marketplace_id: int,
    is_enabled: Optional[bool] = None,
    settings_json: Optional[Dict[str, Any]] = None,
    api_token_encrypted: Optional[str] = None
) -> dict:
    """Create or update project-marketplace connection using UPSERT with ON CONFLICT.
    
    Uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE to ensure atomic UPSERT.
    For UPDATE: merges settings_json (preserves existing keys), only updates provided fields.
    """
    import json as json_module
    
    # Get existing settings for merge (only if settings_json is provided)
    existing = None
    if settings_json is not None:
        existing = get_project_marketplace(project_id, marketplace_id)
    
    existing_settings = None
    if existing and existing.get("settings_json"):
        existing_settings_raw = existing.get("settings_json")
        if isinstance(existing_settings_raw, str):
            existing_settings = json_module.loads(existing_settings_raw)
        elif isinstance(existing_settings_raw, dict):
            existing_settings = existing_settings_raw
    
    # Merge settings_json: {**old, **new} if settings_json is provided
    # Otherwise keep existing or use empty dict for INSERT
    if settings_json is not None:
        merged_settings = existing_settings.copy() if existing_settings else {}
        merged_settings = {**merged_settings, **settings_json}
        settings_json_str = json_module.dumps(merged_settings)
        settings_json_param = settings_json_str
    else:
        # For INSERT, use empty dict. For UPDATE, keep existing (None in param means don't update)
        settings_json_str = "{}"
        settings_json_param = None
    
    with engine.begin() as conn:
        # UPSERT using ON CONFLICT
        # For INSERT: use provided/default values
        # For UPDATE: only update fields where param is not NULL
        result = conn.execute(
            text("""
                INSERT INTO project_marketplaces (project_id, marketplace_id, is_enabled, settings_json, api_token_encrypted)
                VALUES (:project_id, :marketplace_id, :is_enabled, CAST(:settings_json AS jsonb), :api_token_encrypted)
                ON CONFLICT (project_id, marketplace_id) 
                DO UPDATE SET
                    is_enabled = COALESCE(:is_enabled_param, project_marketplaces.is_enabled),
                    settings_json = COALESCE(CAST(:settings_json_param AS jsonb), project_marketplaces.settings_json),
                    api_token_encrypted = COALESCE(:api_token_param, project_marketplaces.api_token_encrypted),
                    updated_at = now()
                RETURNING id, project_id, marketplace_id, is_enabled, settings_json, api_token_encrypted, created_at, updated_at
            """),
            {
                "project_id": project_id,
                "marketplace_id": marketplace_id,
                "is_enabled": is_enabled if is_enabled is not None else False,
                "settings_json": settings_json_str,
                "api_token_encrypted": api_token_encrypted,
                "is_enabled_param": is_enabled,  # NULL if not provided, COALESCE keeps existing
                "settings_json_param": settings_json_param,  # NULL if not provided, COALESCE keeps existing
                "api_token_param": api_token_encrypted,  # NULL if not provided, COALESCE keeps existing
            }
        )
        row = result.fetchone()
        return {
            "id": row[0],
            "project_id": row[1],
            "marketplace_id": row[2],
            "is_enabled": row[3],
            "settings_json": row[4],
            "api_token_encrypted": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }


def update_project_marketplace_settings(
    project_id: int,
    marketplace_id: int,
    settings_json: Dict[str, Any]
) -> Optional[dict]:
    """Update project-marketplace settings (merge with existing)."""
    import json as json_module
    
    existing = get_project_marketplace(project_id, marketplace_id)
    if not existing:
        return None
    
    # Merge with existing settings
    existing_settings = existing.get("settings_json") or {}
    if isinstance(existing_settings, str):
        existing_settings = json_module.loads(existing_settings)
    
    merged_settings = {**existing_settings, **settings_json}
    settings_json_str = json_module.dumps(merged_settings)
    
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE project_marketplaces
                SET settings_json = CAST(:settings_json AS jsonb),
                    updated_at = now()
                WHERE project_id = :project_id AND marketplace_id = :marketplace_id
                RETURNING id, project_id, marketplace_id, is_enabled, settings_json, api_token_encrypted, created_at, updated_at
            """),
            {
                "project_id": project_id,
                "marketplace_id": marketplace_id,
                "settings_json": settings_json_str,
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
            }
        return None


def toggle_project_marketplace(
    project_id: int,
    marketplace_id: int,
    is_enabled: bool
) -> Optional[dict]:
    """Enable or disable marketplace for a project."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE project_marketplaces
                SET is_enabled = :is_enabled, updated_at = now()
                WHERE project_id = :project_id AND marketplace_id = :marketplace_id
                RETURNING id, project_id, marketplace_id, is_enabled, settings_json, api_token_encrypted, created_at, updated_at
            """),
            {
                "project_id": project_id,
                "marketplace_id": marketplace_id,
                "is_enabled": is_enabled,
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
            }
        return None


def delete_project_marketplace(project_id: int, marketplace_id: int) -> bool:
    """Delete project-marketplace connection."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM project_marketplaces
                WHERE project_id = :project_id AND marketplace_id = :marketplace_id
            """),
            {
                "project_id": project_id,
                "marketplace_id": marketplace_id,
            }
        )
        return result.rowcount > 0



