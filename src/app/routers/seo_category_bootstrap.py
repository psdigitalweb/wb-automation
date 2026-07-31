"""Internal category bootstrap endpoints for meaning-aware matching."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.schemas.seo_category_bootstrap import (
    CategoryBootstrapRunRequest,
    CategoryBootstrapRunResponse,
    CategoryBootstrapStatusResponse,
    SeoCategoryListItem,
)
from app.services.seo.category_bootstrap import (
    create_category_bootstrap_run,
    get_category_bootstrap_status,
    run_category_bootstrap_background,
)


router = APIRouter(prefix="/api/v1", tags=["seo-category-bootstrap"])


@router.get(
    "/projects/{project_id}/seo/categories",
    response_model=list[SeoCategoryListItem],
)
async def list_seo_categories_endpoint(
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership
    from sqlalchemy import text

    session = SessionLocal()
    try:
        rows = session.execute(
            text(
                """
                WITH product_subjects AS (
                    SELECT
                        subject_id::int AS category_id,
                        MAX(subject_name) AS category_name,
                        COUNT(*)::int AS skus_count
                    FROM products
                    WHERE project_id = :project_id
                      AND subject_id IS NOT NULL
                      AND subject_name IS NOT NULL
                    GROUP BY subject_id
                ),
                query_categories AS (
                    SELECT category_id::int, TRUE AS has_query_corpus
                    FROM seo_query_batches
                    WHERE project_id = :project_id
                    GROUP BY category_id
                    UNION
                    SELECT category_id::int, TRUE AS has_query_corpus
                    FROM seo_queries_raw
                    WHERE project_id = :project_id
                    GROUP BY category_id
                ),
                profile_categories AS (
                    SELECT category_id::int, TRUE AS has_category_profile
                    FROM seo_category_profiles
                    WHERE project_id = :project_id
                    GROUP BY category_id
                ),
                all_categories AS (
                    SELECT category_id FROM product_subjects
                    UNION
                    SELECT category_id FROM query_categories
                    UNION
                    SELECT category_id FROM seo_category_matching_readiness WHERE project_id = :project_id
                    UNION
                    SELECT category_id FROM profile_categories
                )
                SELECT
                    c.category_id,
                    COALESCE(p.category_name, 'WB subject_id ' || c.category_id::text) AS category_name,
                    COALESCE(p.skus_count, 0)::int AS skus_count,
                    COALESCE(r.status, 'not_started') AS readiness_status,
                    COALESCE(r.queries_count, 0)::int AS queries_count,
                    COALESCE(r.clusters_count, 0)::int AS clusters_count,
                    COALESCE(r.query_meanings_count, 0)::int AS query_meanings_count,
                    COALESCE(r.query_atoms_count, 0)::int AS query_atoms_count,
                    COALESCE(r.embeddings_count, 0)::int AS embeddings_count,
                    COALESCE(r.category_axes_status, 'not_started') AS category_axes_status,
                    r.latest_run_id,
                    COALESCE(q.has_query_corpus, FALSE) AS has_query_corpus,
                    COALESCE(pr.has_category_profile, FALSE) AS has_category_profile
                FROM all_categories c
                LEFT JOIN product_subjects p ON p.category_id = c.category_id
                LEFT JOIN seo_category_matching_readiness r
                  ON r.project_id = :project_id AND r.category_id = c.category_id
                LEFT JOIN query_categories q ON q.category_id = c.category_id
                LEFT JOIN profile_categories pr ON pr.category_id = c.category_id
                ORDER BY
                  CASE
                    WHEN COALESCE(r.status, 'not_started') IN ('ready_for_matching', 'ready_with_fallback', 'building') THEN 0
                    WHEN COALESCE(q.has_query_corpus, FALSE) OR COALESCE(pr.has_category_profile, FALSE) THEN 1
                    ELSE 2
                  END,
                  COALESCE(p.category_name, 'WB subject_id ' || c.category_id::text) ASC
                """
            ),
            {"project_id": int(project_id)},
        ).mappings().all()
        return [SeoCategoryListItem(**dict(row)) for row in rows]
    finally:
        session.close()


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
