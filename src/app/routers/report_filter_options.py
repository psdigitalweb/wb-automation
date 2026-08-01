from fastapi import APIRouter, Depends, HTTPException, Path

from app.deps import get_project_membership
from app.schemas.report_filter_options import ReportFilterOptionsResponse
from app.services.report_filter_options import get_report_filter_options


router = APIRouter(prefix="/api/v1", tags=["report-filter-options"])


@router.get(
    "/projects/{project_id}/wildberries/report-filter-options/{report_code}",
    response_model=ReportFilterOptionsResponse,
)
async def report_filter_options_endpoint(
    project_id: int = Path(..., ge=1),
    report_code: str = Path(...),
    _membership=Depends(get_project_membership),
):
    try:
        return get_report_filter_options(project_id, report_code)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown report code")
