"""Router for project-scoped Warehouse Labor Days."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_warehouse_labor import (
    upsert_warehouse_labor_day,
    list_warehouse_labor_days,
    get_warehouse_labor_day_by_id,
    delete_warehouse_labor_day,
    get_warehouse_labor_summary,
)
from app.db_projects import get_project_member, ProjectRole
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.warehouse_labor import (
    WarehouseLaborDayCreate,
    WarehouseLaborDayResponse,
    WarehouseLaborDaysListResponse,
    WarehouseLaborSummaryResponse,
    WarehouseLaborSummaryBreakdownItem,
)


router = APIRouter(prefix="/api/v1", tags=["warehouse-labor"])


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a database row to JSON-serializable dict.
    
    Handles Decimal -> keep as Decimal (Pydantic will serialize as string),
    datetime/date -> isoformat.
    """
    result = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = value  # Keep as Decimal, Pydantic will serialize as string
        elif hasattr(value, "isoformat"):  # datetime, date objects
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


@router.get(
    "/projects/{project_id}/warehouse-labor/days",
    response_model=WarehouseLaborDaysListResponse,
)
async def list_warehouse_labor_days_endpoint(
    project_id: int = Path(..., description="Project ID"),
    date_from: Optional[date] = Query(None, description="Filter: work_date >= date_from"),
    date_to: Optional[date] = Query(None, description="Filter: work_date <= date_to"),
    marketplace_code: Optional[str] = Query(None, description="Filter by marketplace code (empty string for NULL)"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List warehouse labor days for a project with filters."""
    # Validate date range
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )
    
    # Convert empty string to None for marketplace_code
    marketplace_code_filter = None if marketplace_code == "" else marketplace_code
    
    days = list_warehouse_labor_days(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        marketplace_code=marketplace_code_filter,
    )
    
    # Serialize days
    serialized_days = []
    for day in days:
        serialized_day = _serialize_row(day)
        # Serialize rates
        serialized_day["rates"] = [
            _serialize_row(rate) for rate in day["rates"]
        ]
        serialized_days.append(WarehouseLaborDayResponse(**serialized_day))
    
    return WarehouseLaborDaysListResponse(items=serialized_days)


@router.post(
    "/projects/{project_id}/warehouse-labor/days",
    response_model=WarehouseLaborDayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_warehouse_labor_day_endpoint(
    body: WarehouseLaborDayCreate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Create or update a warehouse labor day. Requires project admin.
    
    Upsert by key (project_id, work_date, marketplace_code).
    Rates are replaced entirely (old rates deleted, new rates inserted).
    """
    # Prepare data dict from body
    # field_validator in schema handles string->Decimal conversion, but ensure it's Decimal for DB layer
    data = body.model_dump()
    for rate in data.get("rates", []):
        if "rate_amount" in rate:
            if isinstance(rate["rate_amount"], str):
                # Normalize string: remove spaces, replace comma with dot
                cleaned = rate["rate_amount"].strip().replace(' ', '').replace(',', '.')
                rate["rate_amount"] = Decimal(cleaned)
            elif isinstance(rate["rate_amount"], (int, float)):
                rate["rate_amount"] = Decimal(str(rate["rate_amount"]))
    
    try:
        day = upsert_warehouse_labor_day(project_id=project_id, data=data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Serialize response
    serialized_day = _serialize_row(day)
    serialized_day["rates"] = [
        _serialize_row(rate) for rate in day["rates"]
    ]
    
    return WarehouseLaborDayResponse(**serialized_day)


@router.delete(
    "/warehouse-labor/days/{day_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_warehouse_labor_day_endpoint(
    day_id: int = Path(..., description="Day ID"),
    current_user: dict = Depends(get_current_active_user),
):
    """Delete a warehouse labor day. Requires project admin.
    
    Note: project_id is obtained from the day itself for permission check.
    """
    # Get day to obtain project_id
    day = get_warehouse_labor_day_by_id(day_id)
    if not day:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Day not found",
        )
    
    project_id = day["project_id"]
    
    # Check membership and role (admin/owner required)
    member = get_project_member(project_id, current_user["id"])
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you are not a member",
        )
    
    if member["role"] not in [ProjectRole.OWNER, ProjectRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required role: owner or admin. Your role: {member['role']}",
        )
    
    deleted = delete_warehouse_labor_day(project_id=project_id, day_id=day_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Day not found",
        )
    
    return None


@router.get(
    "/projects/{project_id}/warehouse-labor/summary",
    response_model=WarehouseLaborSummaryResponse,
)
async def get_warehouse_labor_summary_endpoint(
    project_id: int = Path(..., description="Project ID"),
    date_from: date = Query(..., description="Start date for summary period"),
    date_to: date = Query(..., description="End date for summary period"),
    group_by: str = Query("day", description="Aggregation level: day, marketplace, or project"),
    marketplace_code: Optional[str] = Query(None, description="Filter by marketplace code (empty string for NULL)"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get summary of warehouse labor costs with aggregation.
    
    Costs are summed as SUM(employees_count * rate_amount) per day.
    Grouping:
    - day: by work_date
    - marketplace: by marketplace_code (NULL as "общий")
    - project: total only
    """
    # Validate date range
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )
    
    # Validate group_by
    if group_by not in ["day", "marketplace", "project"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_by must be one of: day, marketplace, project",
        )
    
    # Convert empty string to None for marketplace_code
    marketplace_code_filter = None if marketplace_code == "" else marketplace_code
    
    summary = get_warehouse_labor_summary(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        marketplace_code=marketplace_code_filter,
    )
    
    # Serialize breakdown items
    breakdown_items = [
        WarehouseLaborSummaryBreakdownItem(**_serialize_row(item))
        for item in summary["breakdown"]
    ]
    
    return WarehouseLaborSummaryResponse(
        total_amount=Decimal(str(summary["total_amount"])),
        breakdown=breakdown_items,
    )
