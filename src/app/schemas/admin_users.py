"""Pydantic schemas for admin user and project member management."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr


class AdminUserCreate(BaseModel):
    """Schema for creating a new user (admin only)."""
    username: str
    email: Optional[EmailStr] = None
    password: str
    is_active: bool = True
    is_superuser: bool = False


class AdminUserResponse(BaseModel):
    """Schema for user response (admin only, no password)."""
    id: int
    username: str
    email: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    """Schema for paginated user list response."""
    users: List[AdminUserResponse]
    total: int


class AdminProjectMemberCreate(BaseModel):
    """Schema for adding a user to a project."""
    user_id: int
    role: str  # validated against ProjectRole in router


class AdminProjectMemberResponse(BaseModel):
    """Schema for project member response."""
    id: int
    project_id: int
    user_id: int
    username: str
    email: Optional[str] = None
    role: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AdminProjectMemberUpdate(BaseModel):
    """Schema for updating project member role."""
    role: str  # validated against ProjectRole in router
