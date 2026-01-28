"""Router for project-scoped COGS Direct Rules."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_cogs import (
    delete_cogs_direct_rule,
    get_cogs_coverage,
    get_cogs_direct_rules,
    get_cogs_missing_skus,
    get_price_sources_availability,
    upsert_cogs_direct_rules_bulk,
)
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.cogs import (
    CogsCoverageResponse,
    CogsDirectRuleResponse,
    CogsDirectRulesBulkUpsertRequest,
    CogsDirectRulesListResponse,
    MissingSkusResponse,
    PriceSourcesResponse,
)


router = APIRouter(prefix="/api/v1", tags=["cogs"])


def _row_to_response(row: dict) -> CogsDirectRuleResponse:
    return CogsDirectRuleResponse(
        id=row["id"],
        project_id=row["project_id"],
        internal_sku=row["internal_sku"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        applies_to=row.get("applies_to") or "sku",
        mode=row["mode"],
        value=row["value"],
        currency=row["currency"],
        price_source_code=row.get("price_source_code"),
        meta_json=row.get("meta_json") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _parse_date_or_today(s: Optional[str]) -> date:
    if not s or not s.strip():
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="as_of_date must be YYYY-MM-DD",
        ) from None


@router.get(
    "/projects/{project_id}/cogs/price-sources",
    response_model=PriceSourcesResponse,
)
async def get_price_sources(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List available price sources for the project (internal RRP, WB admin)."""
    data = get_price_sources_availability(project_id)
    return PriceSourcesResponse(**data)


@router.get(
    "/projects/{project_id}/cogs/direct-rules",
    response_model=CogsDirectRulesListResponse,
)
async def list_cogs_direct_rules(
    project_id: int = Path(..., description="Project ID"),
    search: Optional[str] = Query(None, description="Filter by internal_sku (ILIKE)"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List COGS direct rules for a project with pagination."""
    rows, total = get_cogs_direct_rules(project_id, search=search, limit=limit, offset=offset)
    items = [_row_to_response(r) for r in rows]
    return CogsDirectRulesListResponse(items=items, limit=limit, offset=offset, total=total)


@router.put(
    "/projects/{project_id}/cogs/direct-rules:bulk-upsert",
)
async def bulk_upsert_cogs_direct_rules(
    body: CogsDirectRulesBulkUpsertRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Bulk upsert COGS direct rules. Requires project admin.
    
    Returns inserted, updated, failed, errors, adjustments.
    
    Business rule: For the FIRST rule per scope (project_id, applies_to, internal_sku),
    automatically adjusts valid_from backward to min_period_start_with_reports if needed.
    Adjustments array contains info about rows where valid_from was auto-adjusted.
    """
    if not body.items:
        return {"inserted": 0, "updated": 0, "failed": 0, "errors": [], "adjustments": []}
    sources = get_price_sources_availability(project_id)
    available_codes = {
        s["code"] for s in sources["available_sources"]
        if s.get("available")
    }
    rows = [item.model_dump() for item in body.items]
    try:
        stats = upsert_cogs_direct_rules_bulk(
            project_id,
            rows,
            allowed_price_source_codes=available_codes,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return stats


@router.delete(
    "/projects/{project_id}/cogs/direct-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cogs_direct_rule_endpoint(
    project_id: int = Path(..., description="Project ID"),
    rule_id: int = Path(..., description="Rule ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Delete a COGS direct rule. Requires project admin."""
    deleted = delete_cogs_direct_rule(project_id, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found or does not belong to this project",
        )
    return None


@router.get(
    "/projects/{project_id}/cogs/coverage",
    response_model=CogsCoverageResponse,
)
async def get_cogs_coverage_endpoint(
    project_id: int = Path(..., description="Project ID"),
    as_of_date: Optional[str] = Query(None, description="Date for coverage (YYYY-MM-DD), default today"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get COGS coverage stats for a project."""
    d = _parse_date_or_today(as_of_date)
    data = get_cogs_coverage(project_id, as_of_date=d)
    return CogsCoverageResponse(**data)


@router.get(
    "/projects/{project_id}/cogs/missing-skus",
    response_model=MissingSkusResponse,
)
async def get_missing_skus(
    project_id: int = Path(..., description="Project ID"),
    as_of_date: Optional[str] = Query(None, description="Date (YYYY-MM-DD), default today"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, description="Filter internal_sku prefix (ILIKE)"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List internal SKUs with no active rule on as_of_date (excludes default-covered)."""
    d = _parse_date_or_today(as_of_date)
    data = get_cogs_missing_skus(project_id, as_of_date=d, limit=limit, offset=offset, q=q)
    return MissingSkusResponse(**data)
