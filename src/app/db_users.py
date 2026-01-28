"""Database helpers for the `users` table.

This module provides:
- ensure_schema(): idempotently creates the `users` table and indexes
- User CRUD operations
"""

from __future__ import annotations

from typing import Optional, List
from sqlalchemy import text
from sqlalchemy.orm import Session

# Import engine from db module
from app.db import engine, SessionLocal


def ensure_schema() -> None:
    """Create `users` table and indexes if they do not exist.
    
    This function is idempotent and may be safely executed multiple times.
    """
    create_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            username        VARCHAR(64) UNIQUE NOT NULL,
            email           VARCHAR(255) UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            is_superuser    BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    
    create_indexes_sql = [
        text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);"),
        text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);"),
    ]
    
    with engine.begin() as conn:
        conn.execute(create_table_sql)
        for idx_sql in create_indexes_sql:
            conn.execute(idx_sql)
    
    print("db_users: users schema ensured")


def get_user_by_username(username: str) -> Optional[dict]:
    """Get user by username."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, username, email, hashed_password, is_active, is_superuser, created_at, updated_at FROM users WHERE username = :username"),
            {"username": username}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "hashed_password": row[3],
                "is_active": row[4],
                "is_superuser": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
        return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, username, email, hashed_password, is_active, is_superuser, created_at, updated_at FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "hashed_password": row[3],
                "is_active": row[4],
                "is_superuser": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, username, email, hashed_password, is_active, is_superuser, created_at, updated_at FROM users WHERE email = :email"),
            {"email": email}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "hashed_password": row[3],
                "is_active": row[4],
                "is_superuser": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
        return None


def list_users(limit: int = 200, offset: int = 0, q: Optional[str] = None) -> List[dict]:
    """List users with pagination and optional search.
    
    Args:
        limit: Maximum number of users to return (default: 200)
        offset: Number of users to skip (default: 0)
        q: Optional search query for username or email (case-insensitive)
    
    Returns:
        List of user dicts (without hashed_password)
    """
    with engine.connect() as conn:
        if q:
            search_pattern = f"%{q}%"
            result = conn.execute(
                text("""
                    SELECT id, username, email, is_active, is_superuser, created_at, updated_at
                    FROM users
                    WHERE username ILIKE :q OR email ILIKE :q
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"q": search_pattern, "limit": limit, "offset": offset}
            )
        else:
            result = conn.execute(
                text("""
                    SELECT id, username, email, is_active, is_superuser, created_at, updated_at
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset}
            )
        
        users = []
        for row in result:
            users.append({
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "is_active": row[3],
                "is_superuser": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            })
        return users


def count_users(q: Optional[str] = None) -> int:
    """Count total number of users, optionally filtered by search query.
    
    Args:
        q: Optional search query for username or email (case-insensitive)
    
    Returns:
        Total count of users matching the query
    """
    with engine.connect() as conn:
        if q:
            search_pattern = f"%{q}%"
            result = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username ILIKE :q OR email ILIKE :q"),
                {"q": search_pattern}
            )
        else:
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
        return result.scalar_one()


def count_superusers() -> int:
    """Count total number of superusers.
    
    Returns:
        Total count of users with is_superuser = TRUE
    """
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM users WHERE is_superuser = TRUE")
        )
        return result.scalar_one()


def create_user(
    username: str,
    email: Optional[str],
    hashed_password: str,
    is_superuser: bool = False,
    is_active: bool = True
) -> dict:
    """Create a new user."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO users (username, email, hashed_password, is_superuser, is_active)
                VALUES (:username, :email, :hashed_password, :is_superuser, :is_active)
                RETURNING id, username, email, is_active, is_superuser, created_at, updated_at
            """),
            {
                "username": username,
                "email": email,
                "hashed_password": hashed_password,
                "is_superuser": is_superuser,
                "is_active": is_active,
            }
        )
        row = result.fetchone()
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "is_active": row[3],
            "is_superuser": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }


def delete_user(user_id: int) -> bool:
    """Delete a user by ID.
    
    Args:
        user_id: ID of the user to delete
    
    Returns:
        True if user was deleted, False if user was not found
    
    Note:
        This will cascade delete related records in project_members
        due to FK ON DELETE CASCADE constraint.
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        return result.rowcount > 0


def update_user_last_login(user_id: int) -> None:
    """Update user's updated_at timestamp."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET updated_at = now() WHERE id = :user_id"),
            {"user_id": user_id}
        )

