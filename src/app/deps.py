"""Dependencies for FastAPI endpoints."""

from typing import Optional, List
from fastapi import Depends, HTTPException, status, Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import decode_token
from app.db_users import get_user_by_id, get_user_by_username
from app.db_projects import get_project_member, ProjectRole
from app.schemas.auth import TokenData

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Get current user from JWT access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = decode_token(token, token_type="access")
    
    if payload is None:
        raise credentials_exception
    
    username: Optional[str] = payload.get("sub")
    user_id: Optional[int] = payload.get("user_id")
    
    if username is None and user_id is None:
        raise credentials_exception
    
    # Try to get user by username first, then by ID
    user = None
    if username:
        user = get_user_by_username(username)
    if not user and user_id:
        user = get_user_by_id(user_id)
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current active user."""
    if not current_user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_superuser(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Get current superuser."""
    if not current_user.get("is_superuser"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


async def get_project_membership(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Verify that current user is a member of the project.
    
    Returns project member info with role.
    Raises 404 if project doesn't exist or user is not a member.
    """
    member = get_project_member(project_id, current_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member"
        )
    return member


async def require_project_role(
    required_roles: List[str],
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to have one of the specified roles in the project.
    
    Args:
        required_roles: List of allowed roles (e.g., ['owner', 'admin'])
    
    Returns project member info with role.
    Raises 403 if user doesn't have required role.
    """
    member = get_project_member(project_id, current_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member"
        )
    
    if member["role"] not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required role: {', '.join(required_roles)}. Your role: {member['role']}"
        )
    
    return member


# Convenience dependencies for common role checks
async def require_project_owner(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project owner."""
    return await require_project_role([ProjectRole.OWNER], project_id, current_user)


async def require_project_admin(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project owner or admin."""
    return await require_project_role([ProjectRole.OWNER, ProjectRole.ADMIN], project_id, current_user)


async def require_project_member(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Require user to be project member (any role except viewer)."""
    return await require_project_role(
        [ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER],
        project_id,
        current_user
    )

