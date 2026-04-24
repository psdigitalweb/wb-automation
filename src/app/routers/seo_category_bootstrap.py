"""Internal category bootstrap endpoints for meaning-aware matching."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.schemas.seo_category_bootstrap import (
    CategoryBootstrapRunRequest,
    CategoryBootstrapRunResponse,
    CategoryBootstrapStatusResponse,
)
from app.services.seo.category_bootstrap import (
    create_category_bootstrap_run,
    get_category_bootstrap_status,
    run_category_bootstrap_background,
)


router = APIRouter(prefix="/api/v1", tags=["seo-category-bootstrap"])


@router.post(
    "/projects/{project_id}/seo/category-bootstrap/run",
    response_model=CategoryBootstrapRunResponse,
)
async def post_category_bootstrap_run_endpoint(
    request: CategoryBootstrapRunRequest,
    background_tasks: BackgroundTasks,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        run = create_category_bootstrap_run(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
            trigger="manual",
        )
        status = get_category_bootstrap_status(
            session,
            project_id=int(project_id),
            category_id=int(request.category_id),
        )
        session.commit()
        background_tasks.add_task(
            run_category_bootstrap_background,
            int(run.id),
            force_refresh=bool(request.force_refresh),
            use_llm=bool(request.use_llm),
        )
        return CategoryBootstrapRunResponse(
            run_id=int(run.id),
            project_id=int(project_id),
            category_id=int(request.category_id),
            status=str(run.status),  # type: ignore[arg-type]
            readiness_status=status.readiness_status,
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        session.close()


@router.get(
    "/projects/{project_id}/seo/category-bootstrap/status",
    response_model=CategoryBootstrapStatusResponse,
)
async def get_category_bootstrap_status_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB subject/category ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    session = SessionLocal()
    try:
        response = get_category_bootstrap_status(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
        )
        session.commit()
        return response
    finally:
        session.close()
