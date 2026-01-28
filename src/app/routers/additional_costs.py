"""Router for project-scoped Additional Cost Entries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_additional_costs import (
    create_additional_cost_entry,
    get_additional_cost_entry,
    get_additional_cost_entry_by_id,
    list_additional_cost_entries,
    update_additional_cost_entry,
    delete_additional_cost_entry,
    get_additional_cost_summary,
)
from app.db_projects import get_project_member, ProjectRole
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.additional_costs import (
    AdditionalCostEntryCreate,
    AdditionalCostEntryUpdate,
    AdditionalCostEntryResponse,
    AdditionalCostEntriesListResponse,
    AdditionalCostSummaryResponse,
    AdditionalCostSummaryBreakdownItem,
    AdditionalCostCategoriesResponse,
    AdditionalCostCategoryItem,
)


router = APIRouter(prefix="/api/v1", tags=["additional-costs"])


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a database row to JSON-serializable dict.
    
    Handles Decimal -> float, datetime/date -> isoformat.
    """
    result = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif hasattr(value, "isoformat"):  # datetime, date objects
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


@router.get(
    "/projects/{project_id}/additional-costs/entries",
    response_model=AdditionalCostEntriesListResponse,
)
async def list_additional_cost_entries_endpoint(
    project_id: int = Path(..., description="Project ID"),
    date_from: Optional[date] = Query(None, description="Filter: period_from <= date_to"),
    date_to: Optional[date] = Query(None, description="Filter: period_to >= date_from"),
    scope: Optional[str] = Query(None, description="Filter by scope: project, marketplace, or product"),
    marketplace_code: Optional[str] = Query(None, description="Filter by marketplace code"),
    category: Optional[str] = Query(None, description="Filter by category"),
    nm_id: Optional[int] = Query(None, description="Filter by nm_id"),
    internal_sku: Optional[str] = Query(None, description="Filter by internal_sku"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """List additional cost entries for a project with filters."""
    # Validate date range
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )
    
    # Validate scope
    if scope is not None and scope not in ["project", "marketplace", "product"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be one of: project, marketplace, product",
        )
    
    items, total = list_additional_cost_entries(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        scope=scope,
        marketplace_code=marketplace_code,
        category=category,
        nm_id=nm_id,
        internal_sku=internal_sku,
        limit=limit,
        offset=offset,
    )
    
    # Serialize items
    serialized_items = [
        AdditionalCostEntryResponse(**_serialize_row(item)) for item in items
    ]
    
    return AdditionalCostEntriesListResponse(
        items=serialized_items,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/additional-costs/entries",
    response_model=AdditionalCostEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_additional_cost_entry_endpoint(
    body: AdditionalCostEntryCreate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    """Create a new additional cost entry. Requires project admin.
    
    Scope and related fields are validated for consistency.
    Currency defaults to 'RUB' if not provided.
    """
    # Prepare data dict from body
    data = body.model_dump()
    
    # Set default currency if not provided
    if "currency" not in data or not data.get("currency"):
        data["currency"] = "RUB"
    
    try:
        entry = create_additional_cost_entry(project_id=project_id, data=data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return AdditionalCostEntryResponse(**_serialize_row(entry))


@router.put(
    "/additional-costs/entries/{entry_id}",
    response_model=AdditionalCostEntryResponse,
)
async def update_additional_cost_entry_endpoint(
    body: AdditionalCostEntryUpdate,
    entry_id: int = Path(..., description="Entry ID"),
    current_user: dict = Depends(get_current_active_user),
):
    """Update an additional cost entry. Requires project admin.
    
    Note: project_id is obtained from the entry itself for permission check.
    Scope and related fields are validated for consistency.
    """
    # Get entry to obtain project_id
    entry = get_additional_cost_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )
    
    project_id = entry["project_id"]
    
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
    
    # Build patch from body (exclude unset fields)
    patch = body.model_dump(exclude_unset=True)
    
    try:
        updated = update_additional_cost_entry(project_id=project_id, entry_id=entry_id, patch=patch)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )
    
    return AdditionalCostEntryResponse(**_serialize_row(updated))


@router.delete(
    "/additional-costs/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_additional_cost_entry_endpoint(
    entry_id: int = Path(..., description="Entry ID"),
    current_user: dict = Depends(get_current_active_user),
):
    """Delete an additional cost entry. Requires project admin.
    
    Note: project_id is obtained from the entry itself for permission check.
    """
    # Get entry to obtain project_id
    entry = get_additional_cost_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )
    
    project_id = entry["project_id"]
    
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
    
    deleted = delete_additional_cost_entry(project_id=project_id, entry_id=entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )
    
    return None


@router.get(
    "/projects/{project_id}/additional-costs/summary",
    response_model=AdditionalCostSummaryResponse,
)
async def get_additional_cost_summary_endpoint(
    project_id: int = Path(..., description="Project ID"),
    date_from: date = Query(..., description="Start date for summary period"),
    date_to: date = Query(..., description="End date for summary period"),
    level: str = Query("project", description="Aggregation level: project, marketplace, or product (filters by scope)"),
    marketplace_code: Optional[str] = Query(None, description="Filter by marketplace code"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get summary of additional costs with prorated amounts.
    
    Costs are prorated based on period overlap with the requested date range.
    Each entry is filtered by its scope: level='project' shows only scope='project' entries,
    level='marketplace' shows only scope='marketplace' entries, level='product' shows only scope='product' entries.
    For product level, grouping is done by internal_sku (not nm_id).
    """
    # Validate date range
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be <= date_to",
        )
    
    # Validate level
    if level not in ["project", "marketplace", "product"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="level must be one of: project, marketplace, product",
        )
    
    summary = get_additional_cost_summary(
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        level=level,
        marketplace_code=marketplace_code,
    )
    
    # Serialize breakdown items
    breakdown_items = [
        AdditionalCostSummaryBreakdownItem(**_serialize_row(item))
        for item in summary["breakdown"]
    ]
    
    return AdditionalCostSummaryResponse(
        total_amount=Decimal(str(summary["total_amount"])),
        breakdown=breakdown_items,
    )


@router.get(
    "/projects/{project_id}/additional-costs/categories",
    response_model=AdditionalCostCategoriesResponse,
)
async def get_additional_cost_categories_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get list of cost categories and subcategories.
    
    Currently returns backend config (no database table).
    """
    # Backend config - can be moved to database later
    categories = [
        AdditionalCostCategoryItem(
            name="Маркетинг",
            subcategories=["Реклама", "Продвижение", "Другое"],
        ),
        AdditionalCostCategoryItem(
            name="Логистика",
            subcategories=["Доставка", "Склад", "Другое"],
        ),
        AdditionalCostCategoryItem(
            name="Налоги",
            subcategories=["НДС", "Налог на прибыль", "Другое"],
        ),
        AdditionalCostCategoryItem(
            name="Комиссии",
            subcategories=["Маркетплейс", "Платежная система", "Другое"],
        ),
        AdditionalCostCategoryItem(
            name="Прочее",
            subcategories=["Другое"],
        ),
    ]
    
    return AdditionalCostCategoriesResponse(categories=categories)
