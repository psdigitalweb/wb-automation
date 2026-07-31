"""Project-scoped internal Meaning Extraction MVP debug endpoint.

Intentionally minimal:
- returns 3 meaning objects (CategoryMeaning, ProductProjection, QueryMeaning)
- plus minimal flags only
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.schemas.seo_meaning_extraction_debug import SeoMeaningExtractionDebugResponse
from app.services.seo.meaning_extraction import (
    build_category_meaning,
    build_product_projection,
    formalize_query_meaning,
)
from app.services.seo.query_pipeline import run_query_profile_extraction


router = APIRouter(prefix="/api/v1", tags=["seo-meaning-extraction-debug"])


@router.get(
    "/projects/{project_id}/seo/meaning-extraction/debug",
    response_model=SeoMeaningExtractionDebugResponse,
)
async def get_seo_meaning_extraction_debug_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int = Query(..., description="WB category/subject scope"),
    nm_id: int | None = Query(None, description="Target nm_id for product projection"),
    cluster_key: str | None = Query(None, description="Exact query cluster_key to formalize into QueryMeaning"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    if nm_id is None:
        raise HTTPException(status_code=400, detail="nm_id is required")
    if not cluster_key:
        raise HTTPException(status_code=400, detail="cluster_key is required")

    session = SessionLocal()
    try:
        category_meaning = build_category_meaning(session, project_id=project_id, category_id=category_id)
        product_projection, product_flags = build_product_projection(
            session,
            project_id=project_id,
            category_id=category_id,
            nm_id=int(nm_id),
            category_meaning=category_meaning,
        )

        profile_result = run_query_profile_extraction(
            session,
            project_id=project_id,
            category_id=category_id,
            top_limit=50,
            samples_limit=50,
            refresh_hybrid=True,
            persist=False,
        )
        profile = next((item for item in profile_result.profiles if str(item.cluster_key) == str(cluster_key)), None)
        if profile is None:
            raise HTTPException(status_code=404, detail="query cluster_key not found in this scope")

        query_meaning, query_flags = formalize_query_meaning(
            profile,
            project_id=project_id,
            category_id=category_id,
        )

        return SeoMeaningExtractionDebugResponse(
            category_meaning=category_meaning.to_dict(),
            product_projection=product_projection.to_dict(),
            query_meaning=query_meaning.to_dict(),
            product_projection_flags=product_flags.to_dict(),
            query_meaning_flags=query_flags.to_dict(),
        )
    finally:
        session.close()

