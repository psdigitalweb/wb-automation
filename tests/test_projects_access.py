from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app import deps
from app.db_projects import ProjectRole
from app.routers import projects as projects_router


def test_load_projects_for_superuser_falls_back_to_all_projects(monkeypatch):
    monkeypatch.setattr(projects_router, "get_user_projects", lambda user_id: [])
    monkeypatch.setattr(
        projects_router,
        "list_all_projects",
        lambda: [
            {
                "id": 1,
                "name": "Zakka",
                "description": None,
                "created_by": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            }
        ],
    )

    result = projects_router._load_projects_for_user({"id": 3, "is_superuser": True})

    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["role"] == ProjectRole.OWNER


def test_load_projects_for_regular_user_keeps_membership_scope(monkeypatch):
    monkeypatch.setattr(projects_router, "get_user_projects", lambda user_id: [])

    result = projects_router._load_projects_for_user({"id": 2, "is_superuser": False})

    assert result == []


def test_get_project_membership_allows_superuser_without_membership(monkeypatch):
    monkeypatch.setattr(deps, "get_project_member", lambda project_id, user_id: None)

    membership = asyncio.run(
        deps.get_project_membership(project_id=42, current_user={"id": 3, "is_superuser": True})
    )

    assert membership["project_id"] == 42
    assert membership["user_id"] == 3
    assert membership["role"] == ProjectRole.OWNER
    assert membership["is_superuser"] is True


def test_get_project_membership_requires_membership_for_regular_user(monkeypatch):
    monkeypatch.setattr(deps, "get_project_member", lambda project_id, user_id: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(deps.get_project_membership(project_id=42, current_user={"id": 2, "is_superuser": False}))

    assert exc_info.value.status_code == 404
