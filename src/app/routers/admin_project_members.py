"""Admin endpoints for project member management (superuser only)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Path

from app.deps import get_current_superuser
from app.db_projects import (
    get_project_by_id,
    get_project_member,
    get_project_members,
    add_project_member,
    remove_project_member,
    update_project_member_role,
    ProjectRole,
)
from app.db_users import get_user_by_id
from app.schemas.admin_users import (
    AdminProjectMemberCreate,
    AdminProjectMemberResponse,
    AdminProjectMemberUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-project-members"])


@router.get(
    "/projects/{project_id}/members",
    response_model=list[AdminProjectMemberResponse],
    summary="List project members",
    description="Get all members of a project. Requires superuser permissions.",
)
async def list_project_members_endpoint(
    project_id: int = Path(..., description="Project ID"),
    _: dict = Depends(get_current_superuser),
) -> list[AdminProjectMemberResponse]:
    """List all members of a project."""
    # Validate project exists
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    
    # Get members
    members_data = get_project_members(project_id)
    
    members = [
        AdminProjectMemberResponse(
            id=member["id"],
            project_id=member["project_id"],
            user_id=member["user_id"],
            username=member["username"],
            email=member.get("email"),
            role=member["role"],
            created_at=member["created_at"],
            updated_at=member["updated_at"],
        )
        for member in members_data
    ]
    
    return members


@router.post(
    "/projects/{project_id}/members",
    response_model=AdminProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to project",
    description="Add a user to a project with specified role. Requires superuser permissions.",
)
async def add_project_member_endpoint(
    project_id: int = Path(..., description="Project ID"),
    member_data: AdminProjectMemberCreate = ...,
    _: dict = Depends(get_current_superuser),
) -> AdminProjectMemberResponse:
    """Add a user to a project.
    
    Validates that project and user exist, and that role is valid.
    """
    # Validate project exists
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    
    # Validate user exists
    user = get_user_by_id(member_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {member_data.user_id} not found"
        )
    
    # Validate role
    if not ProjectRole.is_valid(member_data.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {member_data.role}. Must be one of: {', '.join(ProjectRole.all())}"
        )
    
    # Add member (add_project_member handles ON CONFLICT for existing members)
    try:
        member = add_project_member(
            project_id=project_id,
            user_id=member_data.user_id,
            role=member_data.role,
        )
        
        # Get user info for response
        user = get_user_by_id(member_data.user_id)
        
        logger.info(
            f"Admin added member to project: project_id={project_id}, "
            f"user_id={member_data.user_id}, role={member_data.role}"
        )
        
        return AdminProjectMemberResponse(
            id=member["id"],
            project_id=member["project_id"],
            user_id=member["user_id"],
            username=user["username"],
            email=user.get("email"),
            role=member["role"],
            created_at=member["created_at"],
            updated_at=member["updated_at"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove member from project",
    description="Remove a user from a project. Requires superuser permissions.",
)
async def remove_project_member_endpoint(
    project_id: int = Path(..., description="Project ID"),
    user_id: int = Path(..., description="User ID"),
    _: dict = Depends(get_current_superuser),
) -> dict:
    """Remove a user from a project."""
    # Validate project exists
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    
    # Validate membership exists
    member = get_project_member(project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a member of project {project_id}"
        )
    
    # Remove member
    removed = remove_project_member(project_id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a member of project {project_id}"
        )
    
    logger.info(
        f"Admin removed member from project: project_id={project_id}, user_id={user_id}"
    )
    return {"deleted": True}


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    response_model=AdminProjectMemberResponse,
    summary="Update project member role",
    description="Update the role of a project member. Requires superuser permissions.",
)
async def update_project_member_role_endpoint(
    project_id: int = Path(..., description="Project ID"),
    user_id: int = Path(..., description="User ID"),
    update_data: AdminProjectMemberUpdate = ...,
    _: dict = Depends(get_current_superuser),
) -> AdminProjectMemberResponse:
    """Update the role of a project member."""
    # Validate project exists
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    
    # Validate membership exists
    member = get_project_member(project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a member of project {project_id}"
        )
    
    # Validate role
    if not ProjectRole.is_valid(update_data.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {update_data.role}. Must be one of: {', '.join(ProjectRole.all())}"
        )
    
    # Update role
    try:
        updated_member = update_project_member_role(
            project_id=project_id,
            user_id=user_id,
            role=update_data.role,
        )
        
        if not updated_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} is not a member of project {project_id}"
            )
        
        # Get user info for response
        user = get_user_by_id(user_id)
        
        logger.info(
            f"Admin updated member role: project_id={project_id}, "
            f"user_id={user_id}, role={update_data.role}"
        )
        
        return AdminProjectMemberResponse(
            id=updated_member["id"],
            project_id=updated_member["project_id"],
            user_id=updated_member["user_id"],
            username=user["username"],
            email=user.get("email"),
            role=updated_member["role"],
            created_at=updated_member["created_at"],
            updated_at=updated_member["updated_at"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
