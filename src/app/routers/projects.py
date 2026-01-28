"""Projects router with membership checks."""

import logging
import traceback
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends, Path

from app.db_projects import (
    create_project,
    get_project_by_id,
    get_user_projects,
    get_project_members,
    get_project_member,
    update_project,
    delete_project,
    add_project_member,
    update_project_member_role,
    remove_project_member,
    ProjectRole,
)
from app.schemas.projects import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectWithRole,
    ProjectDetailResponse,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    ProjectMemberResponse,
)
from app.deps import (
    get_current_active_user,
    get_project_membership,
    require_project_owner,
    require_project_admin,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

logger = logging.getLogger(__name__)

# Note: Schema should be created by Alembic migrations, not at runtime.
# ensure_schema() is NOT called here to avoid import-time DB operations.


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(
    project_data: ProjectCreate,
    current_user: dict = Depends(get_current_active_user)
):
    """Create a new project. Creator becomes owner automatically."""
    try:
        project = create_project(
            name=project_data.name,
            description=project_data.description,
            created_by=current_user["id"]
        )
        return ProjectResponse(
            id=project["id"],
            name=project["name"],
            description=project["description"],
            created_by=project["created_by"],
            created_at=project["created_at"],
            updated_at=project["updated_at"],
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in create_project_endpoint: {error_msg}\n{traceback.format_exc()}")
        # Return detailed error to client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {error_msg}"
        )


@router.get("", response_model=List[ProjectWithRole])
async def get_user_projects_endpoint(
    current_user: dict = Depends(get_current_active_user)
):
    """Get all projects where current user is a member."""
    try:
        projects = get_user_projects(current_user["id"])
        result = [
            ProjectWithRole(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                created_by=p["created_by"],
                created_at=p["created_at"],
                updated_at=p["updated_at"],
                role=p["role"],
            )
            for p in projects
        ]
        # #region agent log
        logger.info(f"get_user_projects_endpoint: serialized {len(result)} projects, returning")
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"projects-get","hypothesisId":"H4","location":"routers/projects.py:92","message":"get_user_projects_endpoint exit","data":{"result_count":len(result)},"timestamp":int(time.time()*1000)})+"\n")
        except Exception as log_err:
            logger.error(f"Failed to write debug log: {log_err}")
        # #endregion
        return result
    except Exception as e:
        # #region agent log
        logger.error(f"get_user_projects_endpoint error: {e}\n{traceback.format_exc()}")
        try:
            import json, time, traceback
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"projects-get","hypothesisId":"H4","location":"routers/projects.py:94","message":"get_user_projects_endpoint error","data":{"error":str(e),"traceback":traceback.format_exc()},"timestamp":int(time.time()*1000)})+"\n")
        except Exception as log_err:
            logger.error(f"Failed to write debug log: {log_err}")
        # #endregion
        raise


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)
):
    """Get project details. Requires membership."""
    project = get_project_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    members = get_project_members(project_id)
    
    return ProjectDetailResponse(
        id=project["id"],
        name=project["name"],
        description=project["description"],
        created_by=project["created_by"],
        created_at=project["created_at"],
        updated_at=project["updated_at"],
        members=[
            ProjectMemberResponse(
                id=m["id"],
                project_id=m["project_id"],
                user_id=m["user_id"],
                role=m["role"],
                created_at=m["created_at"],
                updated_at=m["updated_at"],
                username=m.get("username"),
                email=m.get("email"),
            )
            for m in members
        ],
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(
    project_data: ProjectUpdate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can update
):
    """Update project. Requires admin or owner role."""
    project = update_project(
        project_id=project_id,
        name=project_data.name,
        description=project_data.description
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return ProjectResponse(
        id=project["id"],
        name=project["name"],
        description=project["description"],
        created_by=project["created_by"],
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_owner)  # Only owner can delete
):
    """Delete project. Requires owner role."""
    deleted = delete_project(project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    return None


# Project members endpoints

@router.get("/{project_id}/members", response_model=List[ProjectMemberResponse])
async def get_project_members_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)  # Any member can view
):
    """Get project members. Requires membership."""
    members = get_project_members(project_id)
    return [
        ProjectMemberResponse(
            id=m["id"],
            project_id=m["project_id"],
            user_id=m["user_id"],
            role=m["role"],
            created_at=m["created_at"],
            updated_at=m["updated_at"],
            username=m.get("username"),
            email=m.get("email"),
        )
        for m in members
    ]


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member_endpoint(
    member_data: ProjectMemberCreate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can add members
):
    """Add a member to project. Requires admin or owner role."""
    member = add_project_member(
        project_id=project_id,
        user_id=member_data.user_id,
        role=member_data.role
    )
    return ProjectMemberResponse(
        id=member["id"],
        project_id=member["project_id"],
        user_id=member["user_id"],
        role=member["role"],
        created_at=member["created_at"],
        updated_at=member["updated_at"],
    )


@router.put("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse)
async def update_project_member_role_endpoint(
    member_data: ProjectMemberUpdate,
    project_id: int = Path(..., description="Project ID"),
    user_id: int = Path(..., description="User ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can update roles
):
    """Update project member role. Requires admin or owner role."""
    # Prevent changing owner role (only owner can do that)
    if membership["role"] != ProjectRole.OWNER:
        existing_member = get_project_member(project_id, user_id)
        if existing_member and existing_member["role"] == ProjectRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owner can change owner role"
            )
    
    member = update_project_member_role(
        project_id=project_id,
        user_id=user_id,
        role=member_data.role
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found"
        )
    
    return ProjectMemberResponse(
        id=member["id"],
        project_id=member["project_id"],
        user_id=member["user_id"],
        role=member["role"],
        created_at=member["created_at"],
        updated_at=member["updated_at"],
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member_endpoint(
    project_id: int = Path(..., description="Project ID"),
    user_id: int = Path(..., description="User ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Only admin/owner can remove members
):
    """Remove a member from project. Requires admin or owner role."""
    # Prevent removing owner
    if membership["role"] != ProjectRole.OWNER:
        existing_member = get_project_member(project_id, user_id)
        if existing_member and existing_member["role"] == ProjectRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove project owner"
            )
    
    # Prevent removing yourself if you're the only owner
    if user_id == current_user["id"]:
        existing_member = get_project_member(project_id, user_id)
        if existing_member and existing_member["role"] == ProjectRole.OWNER:
            # Check if there are other owners
            members = get_project_members(project_id)
            owners = [m for m in members if m["role"] == ProjectRole.OWNER]
            if len(owners) == 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot remove the only project owner"
                )
    
    removed = remove_project_member(project_id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found"
        )
    return None



