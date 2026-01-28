"""Database helpers for projects and project members.

This module provides:
- ensure_schema(): idempotently creates the `projects` and `project_members` tables
- Project CRUD operations
- ProjectMember CRUD operations
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional, List
from sqlalchemy import text

# Import engine from db module
from app.db import engine

logger = logging.getLogger(__name__)


# Project member roles
class ProjectRole:
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
    
    @classmethod
    def all(cls) -> List[str]:
        return [cls.OWNER, cls.ADMIN, cls.MEMBER, cls.VIEWER]
    
    @classmethod
    def is_valid(cls, role: str) -> bool:
        return role in cls.all()


def ensure_schema() -> None:
    """Create `projects` and `project_members` tables and indexes if they do not exist.
    
    WARNING: This function is for development only. In production, use Alembic migrations.
    Only runs if ENABLE_RUNTIME_SCHEMA_CREATION=true in environment.
    
    This function is idempotent and may be safely executed multiple times.
    """
    import os
    # Only run in development mode
    if not os.getenv("ENABLE_RUNTIME_SCHEMA_CREATION", "false").lower() in ("true", "1", "yes"):
        return
    
    try:
        create_projects_table_sql = text(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR(255) NOT NULL,
                description     TEXT,
                created_by      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        
        create_project_members_table_sql = text(
            """
            CREATE TABLE IF NOT EXISTS project_members (
                id              SERIAL PRIMARY KEY,
                project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role            VARCHAR(20) NOT NULL DEFAULT 'member',
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(project_id, user_id)
            );
            """
        )
        
        create_indexes_sql = [
            text("CREATE INDEX IF NOT EXISTS idx_projects_created_by ON projects(created_by);"),
            text("CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);"),
            text("CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);"),
            text("CREATE INDEX IF NOT EXISTS idx_project_members_role ON project_members(role);"),
        ]
        
        with engine.begin() as conn:
            conn.execute(create_projects_table_sql)
            conn.execute(create_project_members_table_sql)
            for idx_sql in create_indexes_sql:
                conn.execute(idx_sql)
        
        logger.debug("db_projects: projects and project_members schema ensured")
    except Exception as e:
        logger.error(f"Error in ensure_schema(): {e}\n{traceback.format_exc()}")
        # Don't raise - schema should be created by migrations, not runtime


def create_project(name: str, description: Optional[str], created_by: int) -> dict:
    """Create a new project and add creator as owner."""
    # Note: Schema should be created by Alembic migrations, not at runtime
    try:
        with engine.begin() as conn:
            # Create project
            result = conn.execute(
                text("""
                    INSERT INTO projects (name, description, created_by)
                    VALUES (:name, :description, :created_by)
                    RETURNING id, name, description, created_by, created_at, updated_at
                """),
                {
                    "name": name,
                    "description": description,
                    "created_by": created_by,
                }
            )
            project_row = result.fetchone()
            if not project_row:
                error_msg = "Failed to retrieve project after creation (RETURNING returned no rows)"
                logger.error(f"create_project error: {error_msg}")
                raise Exception(error_msg)
            
            project_id = project_row[0]
            
            # Add creator as owner
            conn.execute(
                text("""
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (:project_id, :user_id, 'owner')
                """),
                {
                    "project_id": project_id,
                    "user_id": created_by,
                }
            )
            
            logger.info(f"db_projects: created project id={project_id}, name={name}, created_by={created_by}")
            
            return {
                "id": project_row[0],
                "name": project_row[1],
                "description": project_row[2],
                "created_by": project_row[3],
                "created_at": project_row[4],
                "updated_at": project_row[5],
            }
    except Exception as e:
        logger.error(f"Error creating project (name={name}, created_by={created_by}): {e}\n{traceback.format_exc()}")
        raise


def get_project_by_id(project_id: int) -> Optional[dict]:
    """Get project by ID."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, name, description, created_by, created_at, updated_at
                FROM projects
                WHERE id = :project_id
            """),
            {"project_id": project_id}
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "created_by": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None


def get_user_projects(user_id: int) -> List[dict]:
    """Get all projects where user is a member."""
    # #region agent log
    logger.info(f"get_user_projects entry: user_id={user_id}")
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"db-projects","hypothesisId":"H5","location":"db_projects.py:175","message":"get_user_projects entry","data":{"user_id":user_id},"timestamp":int(time.time()*1000)})+"\n")
    except Exception as log_err:
        logger.error(f"Failed to write debug log: {log_err}")
    # #endregion
    try:
        with engine.connect() as conn:
            # #region agent log
            logger.info(f"get_user_projects: executing SQL query for user_id={user_id}")
            try:
                import json, time
                with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"sessionId":"debug-session","runId":"db-projects","hypothesisId":"H5","location":"db_projects.py:178","message":"Executing SQL query","data":{"user_id":user_id},"timestamp":int(time.time()*1000)})+"\n")
            except Exception as log_err:
                logger.error(f"Failed to write debug log: {log_err}")
            # #endregion
            result = conn.execute(
                text("""
                    SELECT DISTINCT p.id, p.name, p.description, p.created_by, p.created_at, p.updated_at,
                           pm.role
                    FROM projects p
                    INNER JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = :user_id
                    ORDER BY p.updated_at DESC
                """),
                {"user_id": user_id}
            )
            projects = []
            rows = result.mappings().all()
            for row in rows:
                projects.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "role": row["role"],
                })
            # #region agent log
            logger.info(f"get_user_projects: query completed, found {len(projects)} projects")
            try:
                import json, time
                with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"sessionId":"debug-session","runId":"db-projects","hypothesisId":"H5","location":"db_projects.py:200","message":"get_user_projects exit","data":{"projects_count":len(projects)},"timestamp":int(time.time()*1000)})+"\n")
            except Exception as log_err:
                logger.error(f"Failed to write debug log: {log_err}")
            # #endregion
            return projects
    except Exception as e:
        # #region agent log
        logger.error(f"get_user_projects error for user_id={user_id}: {e}\n{traceback.format_exc()}")
        try:
            import json, time, traceback
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"db-projects","hypothesisId":"H5","location":"db_projects.py:202","message":"get_user_projects error","data":{"error":str(e),"traceback":traceback.format_exc()},"timestamp":int(time.time()*1000)})+"\n")
        except Exception as log_err:
            logger.error(f"Failed to write debug log: {log_err}")
        # #endregion
        raise


def get_project_member(project_id: int, user_id: int) -> Optional[dict]:
    """Get project member by project_id and user_id."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, project_id, user_id, role, created_at, updated_at
                FROM project_members
                WHERE project_id = :project_id AND user_id = :user_id
            """),
            {
                "project_id": project_id,
                "user_id": user_id,
            }
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "project_id": row[1],
                "user_id": row[2],
                "role": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None


def add_project_member(project_id: int, user_id: int, role: str = ProjectRole.MEMBER) -> dict:
    """Add a member to a project."""
    if not ProjectRole.is_valid(role):
        raise ValueError(f"Invalid role: {role}. Must be one of {ProjectRole.all()}")
    
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO project_members (project_id, user_id, role)
                VALUES (:project_id, :user_id, :role)
                ON CONFLICT (project_id, user_id) DO UPDATE SET
                    role = EXCLUDED.role,
                    updated_at = now()
                RETURNING id, project_id, user_id, role, created_at, updated_at
            """),
            {
                "project_id": project_id,
                "user_id": user_id,
                "role": role,
            }
        )
        row = result.fetchone()
        return {
            "id": row[0],
            "project_id": row[1],
            "user_id": row[2],
            "role": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }


def update_project_member_role(project_id: int, user_id: int, role: str) -> Optional[dict]:
    """Update project member role."""
    if not ProjectRole.is_valid(role):
        raise ValueError(f"Invalid role: {role}. Must be one of {ProjectRole.all()}")
    
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE project_members
                SET role = :role, updated_at = now()
                WHERE project_id = :project_id AND user_id = :user_id
                RETURNING id, project_id, user_id, role, created_at, updated_at
            """),
            {
                "project_id": project_id,
                "user_id": user_id,
                "role": role,
            }
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "project_id": row[1],
                "user_id": row[2],
                "role": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None


def remove_project_member(project_id: int, user_id: int) -> bool:
    """Remove a member from a project."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM project_members
                WHERE project_id = :project_id AND user_id = :user_id
            """),
            {
                "project_id": project_id,
                "user_id": user_id,
            }
        )
        return result.rowcount > 0


def get_project_members(project_id: int) -> List[dict]:
    """Get all members of a project."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT pm.id, pm.project_id, pm.user_id, pm.role, pm.created_at, pm.updated_at,
                       u.username, u.email
                FROM project_members pm
                INNER JOIN users u ON pm.user_id = u.id
                WHERE pm.project_id = :project_id
                ORDER BY pm.role, u.username
            """),
            {"project_id": project_id}
        )
        members = []
        for row in result:
            members.append({
                "id": row[0],
                "project_id": row[1],
                "user_id": row[2],
                "role": row[3],
                "created_at": row[4],
                "updated_at": row[5],
                "username": row[6],
                "email": row[7],
            })
        return members


def update_project(project_id: int, name: Optional[str] = None, description: Optional[str] = None) -> Optional[dict]:
    """Update project."""
    updates = []
    params = {"project_id": project_id}
    
    if name is not None:
        updates.append("name = :name")
        params["name"] = name
    
    if description is not None:
        updates.append("description = :description")
        params["description"] = description
    
    if not updates:
        return get_project_by_id(project_id)
    
    updates.append("updated_at = now()")
    
    with engine.begin() as conn:
        result = conn.execute(
            text(f"""
                UPDATE projects
                SET {', '.join(updates)}
                WHERE id = :project_id
                RETURNING id, name, description, created_by, created_at, updated_at
            """),
            params
        )
        row = result.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "created_by": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
        return None


def delete_project(project_id: int) -> bool:
    """Delete a project (cascade deletes members)."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM projects WHERE id = :project_id"),
            {"project_id": project_id}
        )
        return result.rowcount > 0



