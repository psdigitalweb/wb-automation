"""Pydantic schemas for projects."""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(None, description="Project description")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectWithRole(ProjectResponse):
    role: str = Field(..., description="User's role in the project")


class ProjectMemberBase(BaseModel):
    role: str = Field(..., description="Member role: owner, admin, member, or viewer")


class ProjectMemberCreate(ProjectMemberBase):
    user_id: int = Field(..., description="User ID to add to project")


class ProjectMemberUpdate(ProjectMemberBase):
    pass


class ProjectMemberResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    created_at: datetime
    updated_at: datetime
    username: Optional[str] = None
    email: Optional[str] = None
    
    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    members: List[ProjectMemberResponse] = Field(default_factory=list)




