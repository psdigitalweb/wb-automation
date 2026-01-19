from fastapi import APIRouter, Depends

from app.deps import get_current_superuser
from app.tasks.frontend_prices import sync_frontend_prices_brand

router = APIRouter(prefix="/admin/tasks", tags=["admin-tasks"])


@router.post("/run/frontend-prices-sync")
async def run_frontend_prices_sync(_: dict = Depends(get_current_superuser)):
    """Manually enqueue frontend prices sync task.

    Restricted to superusers.
    """
    result = sync_frontend_prices_brand.delay()
    return {"task_id": result.id}



