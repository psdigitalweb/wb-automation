"""Project-scoped frontend brand pool for WB frontend prices (by-pool ingestion)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from app.db import engine
from app.deps import get_current_active_user, get_project_membership
from sqlalchemy import text

router = APIRouter(prefix="/api/v1", tags=["frontend-brand-pool"])


class FrontendBrandPoolListResponse(BaseModel):
    brand_ids: list[int]


class AddBrandToPoolRequest(BaseModel):
    brand_id: int


def _get_pool(project_id: int) -> list[int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT brand_id FROM project_frontend_brand_pool
                WHERE project_id = :project_id
                ORDER BY brand_id
                """
            ),
            {"project_id": project_id},
        ).fetchall()
    return [int(r[0]) for r in rows]


@router.get(
    "/projects/{project_id}/frontend-brand-pool",
    response_model=FrontendBrandPoolListResponse,
)
async def get_frontend_brand_pool(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Return list of brand_id in the project's frontend prices brand pool."""
    return FrontendBrandPoolListResponse(brand_ids=_get_pool(project_id))


@router.post(
    "/projects/{project_id}/frontend-brand-pool",
    response_model=FrontendBrandPoolListResponse,
    status_code=status.HTTP_200_OK,
)
async def add_brand_to_frontend_pool(
    body: AddBrandToPoolRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Add a brand_id to the project's frontend prices brand pool (idempotent)."""
    if body.brand_id < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="brand_id must be a positive integer",
        )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO project_frontend_brand_pool (project_id, brand_id)
                VALUES (:project_id, :brand_id)
                ON CONFLICT (project_id, brand_id) DO NOTHING
                """
            ),
            {"project_id": project_id, "brand_id": body.brand_id},
        )
    return FrontendBrandPoolListResponse(brand_ids=_get_pool(project_id))


@router.delete(
    "/projects/{project_id}/frontend-brand-pool/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_brand_from_frontend_pool(
    project_id: int = Path(..., description="Project ID"),
    brand_id: int = Path(..., description="Brand ID to remove"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Remove a brand_id from the project's frontend prices brand pool."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                DELETE FROM project_frontend_brand_pool
                WHERE project_id = :project_id AND brand_id = :brand_id
                """
            ),
            {"project_id": project_id, "brand_id": brand_id},
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Brand ID not in pool",
            )
