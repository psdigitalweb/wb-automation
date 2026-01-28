"""Router for Packaging Tariffs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_packaging_tariffs import (
    bulk_upsert_packaging_tariffs,
    list_packaging_tariffs,
    delete_packaging_tariff,
    get_packaging_cost_summary,
)
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.packaging import (
    PackagingTariffUpsertRequest,
    PackagingTariffsListResponse,
    PackagingSummaryResponse,
)


router = APIRouter(prefix="/api/v1", tags=["packaging"])


@router.get(
    "/projects/{project_id}/packaging/tariffs",
    response_model=PackagingTariffsListResponse,
)
async def list_packaging_tariffs_endpoint(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by internal_sku (ILIKE)"),
    only_current: bool = Query(True, description="Return only current tariff per SKU (latest valid_from)"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List packaging tariffs for a project."""
    result = list_packaging_tariffs(
        project_id=project_id,
        internal_sku_query=q,
        only_current=only_current,
        limit=limit,
        offset=offset,
    )
    
    from app.schemas.packaging import PackagingTariffItem
    items = [PackagingTariffItem(**row) for row in result["items"]]
    
    return PackagingTariffsListResponse(
        items=items,
        total=result["total"],
    )


@router.post(
    "/projects/{project_id}/packaging/tariffs/bulk-upsert",
    response_model=dict,
)
async def bulk_upsert_packaging_tariffs_endpoint(
    body: PackagingTariffUpsertRequest,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Bulk upsert packaging tariffs for a list of SKUs. Requires project admin."""
    try:
        result = bulk_upsert_packaging_tariffs(
            project_id=project_id,
            valid_from=body.valid_from,
            cost_per_unit=body.cost_per_unit,
            sku_list=body.sku_list,
            notes=body.notes,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/projects/{project_id}/packaging/tariffs/{tariff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_packaging_tariff_endpoint(
    project_id: int = Path(..., description="Project ID"),
    tariff_id: int = Path(..., description="Tariff ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Delete a packaging tariff. Requires project admin."""
    deleted = delete_packaging_tariff(project_id=project_id, tariff_id=tariff_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tariff not found",
        )
    return None


@router.get(
    "/projects/{project_id}/packaging/summary",
    response_model=PackagingSummaryResponse,
)
async def get_packaging_summary_endpoint(
    project_id: int = Path(..., description="Project ID"),
    date_from: date = Query(..., description="Start date for summary period"),
    date_to: date = Query(..., description="End date for summary period"),
    group_by: str = Query("project", description="Aggregation level: project or product"),
    internal_sku: Optional[str] = Query(None, description="Filter by specific internal_sku"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get packaging cost summary for a period based on sold units."""
    # Validate date range
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )
    
    # Validate group_by
    if group_by not in ["project", "product"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_by must be 'project' or 'product'",
        )
    
    try:
        result = get_packaging_cost_summary(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            internal_sku=internal_sku,
        )
        
        from app.schemas.packaging import PackagingSummaryBreakdownItem
        breakdown = [PackagingSummaryBreakdownItem(**item) for item in result["breakdown"]]
        
        return PackagingSummaryResponse(
            total_amount=result["total_amount"],
            breakdown=breakdown,
            missing_tariff=result["missing_tariff"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
