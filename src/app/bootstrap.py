"""
Bootstrap application data: admin user, Legacy project, marketplaces.

This module provides idempotent bootstrap functions that ensure:
- Admin user exists (username=admin, password from ADMIN_PASSWORD env or default)
- Legacy project exists (for existing data before project scoping)
- Marketplaces are seeded

Bootstrap runs automatically on application startup (if enabled) or can be run manually.
"""

import os
import logging
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import text

from app.db import engine
from app.db_users import get_user_by_username, create_user as create_user_db
from app.db_projects import get_project_by_id, create_project, get_project_member, add_project_member, ProjectRole
from app.db_marketplaces import seed_marketplaces

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def ensure_admin_user() -> Optional[dict]:
    """Ensure admin user exists (idempotent).
    
    Only creates admin user if ADMIN_PASSWORD is set (security: no default password).
    """
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    # Check if admin user exists
    existing_user = get_user_by_username(admin_username)
    if existing_user:
        logger.info(f"Admin user '{admin_username}' already exists (id={existing_user['id']})")
        return existing_user
    
    # Only create admin if ADMIN_PASSWORD is set
    if not admin_password:
        logger.warning("ADMIN_PASSWORD not set, skipping admin user creation")
        logger.warning("Set ADMIN_PASSWORD environment variable to enable admin user creation")
        return None
    
    # Create admin user
    try:
        hashed_password = hash_password(admin_password)
        admin_user = create_user_db(
            username=admin_username,
            email=os.getenv("ADMIN_EMAIL", f"{admin_username}@example.com"),
            hashed_password=hashed_password,
            is_superuser=True
        )
        logger.info(f"Created admin user '{admin_username}' (id={admin_user['id']})")
        return admin_user
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        return None


def ensure_legacy_project(admin_user_id: int) -> Optional[dict]:
    """Ensure Legacy project exists (idempotent)."""
    legacy_name = "Legacy"
    
    # Check if Legacy project exists
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, name, created_by FROM projects WHERE name = :name LIMIT 1"),
            {"name": legacy_name}
        )
        row = result.fetchone()
        if row:
            legacy_project_id = row[0]
            logger.info(f"Legacy project already exists (id={legacy_project_id})")
            # Ensure admin is member with owner role
            member = get_project_member(legacy_project_id, admin_user_id)
            if not member:
                add_project_member(legacy_project_id, admin_user_id, ProjectRole.OWNER)
                logger.info(f"Added admin as owner to Legacy project")
            elif member["role"] != ProjectRole.OWNER:
                from app.db_projects import update_project_member_role
                update_project_member_role(legacy_project_id, admin_user_id, ProjectRole.OWNER)
                logger.info(f"Updated admin role to owner in Legacy project")
            return get_project_by_id(legacy_project_id)
    
    # Create Legacy project
    try:
        legacy_project = create_project(
            name=legacy_name,
            description="Legacy project for data created before project scoping",
            created_by=admin_user_id
        )
        logger.info(f"Created Legacy project (id={legacy_project['id']})")
        return legacy_project
    except Exception as e:
        logger.error(f"Failed to create Legacy project: {e}")
        return None


def bootstrap() -> dict:
    """Run full bootstrap: admin user, Legacy project, marketplaces (idempotent)."""
    result = {
        "admin_user": None,
        "legacy_project": None,
        "marketplaces_seeded": False,
    }
    
    try:
        # 1. Ensure admin user exists
        admin_user = ensure_admin_user()
        result["admin_user"] = admin_user
        
        if not admin_user:
            logger.error("Bootstrap failed: could not create admin user")
            return result
        
        # 2. Ensure Legacy project exists
        legacy_project = ensure_legacy_project(admin_user["id"])
        result["legacy_project"] = legacy_project
        
        if not legacy_project:
            logger.warning("Bootstrap: could not create Legacy project")
        
        # 3. Seed marketplaces
        try:
            seed_marketplaces()
            result["marketplaces_seeded"] = True
            logger.info("Bootstrap: marketplaces seeded")
        except Exception as e:
            logger.warning(f"Bootstrap: marketplaces seeding failed: {e}")
        
        logger.info("Bootstrap completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        return result


def run_bootstrap_on_startup() -> None:
    """Run bootstrap on application startup (if enabled).
    
    Bootstrap is disabled by default (BOOTSTRAP_ENABLED=false) for security.
    Enable it explicitly in dev/test environments.
    """
    bootstrap_enabled = os.getenv("BOOTSTRAP_ENABLED", "false").lower() in ("true", "1", "yes")
    
    if not bootstrap_enabled:
        logger.info("Bootstrap is disabled (BOOTSTRAP_ENABLED=false or not set)")
        return
    
    try:
        # Check if required tables exist
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM users LIMIT 1"))
            conn.execute(text("SELECT 1 FROM projects LIMIT 1"))
        
        # Tables exist, safe to bootstrap
        result = bootstrap()
        if result["admin_user"] and result["legacy_project"]:
            logger.info("Bootstrap completed on startup")
        else:
            logger.warning(f"Bootstrap completed with issues: {result}")
    except Exception as e:
        logger.warning(f"Bootstrap skipped on startup (tables may not exist yet): {e}")


if __name__ == "__main__":
    # Run bootstrap manually
    logging.basicConfig(level=logging.INFO)
    result = bootstrap()
    print(f"Bootstrap result: {result}")

