"""API endpoints for RRP XML snapshots."""

from fastapi import APIRouter, Query, Path, Depends
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership


router = APIRouter(prefix="/api/v1", tags=["rrp"])


def _serialize_row(row: dict) -> dict:
    result = {}
    for key, value in row.items():
        if value is None:
            result[key] = None
        elif isinstance(value, bool):
            result[key] = value
        elif isinstance(value, int):
            result[key] = value
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        elif hasattr(value, "__float__"):
            result[key] = float(value)
        else:
            result[key] = value
    return result


@router.get("/projects/{project_id}/rrp/latest")
async def get_latest_rrp_snapshots(
    project_id: int = Path(..., description="Project ID"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Return latest RRP snapshots for a project (append-only)."""
    count_sql = text("SELECT COUNT(*) AS total FROM rrp_snapshots WHERE project_id = :project_id")
    data_sql = text(
        """
        SELECT snapshot_at, vendor_code_raw, vendor_code_norm, barcode, rrp_price, rrp_stock
        FROM rrp_snapshots
        WHERE project_id = :project_id
        ORDER BY snapshot_at DESC, vendor_code_norm
        LIMIT :limit OFFSET :offset
        """
    )

    with engine.connect() as conn:
        total = conn.execute(count_sql, {"project_id": project_id}).scalar_one()
        rows = (
            conn.execute(data_sql, {"project_id": project_id, "limit": limit, "offset": offset})
            .mappings()
            .all()
        )
    return {
        "data": [_serialize_row(dict(r)) for r in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "total": int(total or 0),
    }

