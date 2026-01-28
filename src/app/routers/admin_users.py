"""Admin endpoints for user management (superuser only)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from app.deps import get_current_superuser
from app.db_users import (
    list_users,
    count_users,
    get_user_by_username,
    get_user_by_id,
    get_user_by_email,
    create_user,
    delete_user,
    count_superusers,
)
from app.core.security import get_password_hash
from app.schemas.admin_users import (
    AdminUserCreate,
    AdminUserResponse,
    AdminUserListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all users",
    description="Get paginated list of users with optional search. Requires superuser permissions.",
)
async def list_users_endpoint(
    limit: int = Query(200, ge=1, le=500, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    q: Optional[str] = Query(None, description="Search query for username or email"),
    _: dict = Depends(get_current_superuser),
) -> AdminUserListResponse:
    """List users with pagination and optional search."""
    users_data = list_users(limit=limit, offset=offset, q=q)
    total = count_users(q=q)
    
    users = [AdminUserResponse(**user) for user in users_data]
    
    return AdminUserListResponse(users=users, total=total)


@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user account. Requires superuser permissions.",
)
async def create_user_endpoint(
    user_data: AdminUserCreate,
    _: dict = Depends(get_current_superuser),
) -> AdminUserResponse:
    """Create a new user.
    
    Validates username and email uniqueness, normalizes input data,
    and hashes the password before storing.
    """
    # Normalize input
    username = user_data.username.strip()
    email = user_data.email.lower().strip() if user_data.email else None
    
    # Validate username uniqueness
    existing_user = get_user_by_username(username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username}' is already taken"
        )
    
    # Validate email uniqueness (if provided)
    if email:
        existing_email = get_user_by_email(email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{email}' is already registered"
            )
    
    # Hash password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user
    try:
        user = create_user(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_superuser=user_data.is_superuser,
            is_active=user_data.is_active,
        )
        logger.info(f"Admin created user: id={user['id']}, username={username}, is_superuser={user_data.is_superuser}")
        return AdminUserResponse(**user)
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        ) from e


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a user",
    description="Delete a user by ID. Cannot delete the last superuser. Requires superuser permissions.",
)
async def delete_user_endpoint(
    user_id: int = Path(..., description="User ID to delete"),
    _: dict = Depends(get_current_superuser),
) -> dict:
    """Delete a user.
    
    Prevents deletion of the last superuser in the system.
    """
    # Check if user exists
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prevent deletion of last superuser
    if user["is_superuser"]:
        superuser_count = count_superusers()
        if superuser_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the last superuser in the system"
            )
    
    # Delete user
    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    logger.info(f"Admin deleted user: id={user_id}, username={user['username']}")
    return {"deleted": True}
