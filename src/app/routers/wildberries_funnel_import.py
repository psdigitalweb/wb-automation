"""Admin-only upload endpoints for WB sales-funnel XLSX/CSV reports."""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile, status

from app.db_wb_funnel_imports import import_funnel_report, list_funnel_report_imports
from app.deps import get_project_membership, require_project_admin
from app.schemas.wildberries_funnel_import import (
    WBFunnelImportListItem,
    WBFunnelImportListResponse,
    WBFunnelImportResponse,
)
from app.services.wb_funnel_report_parser import WBFunnelReportError, parse_wb_funnel_report
from app.settings import WB_FUNNEL_REPORT_MAX_UPLOAD_BYTES


router = APIRouter(prefix="/api/v1", tags=["wildberries-funnel-import"])


@router.post(
    "/projects/{project_id}/wildberries/funnel-report/import",
    response_model=WBFunnelImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_wb_funnel_report(
    project_id: int = Path(...),
    file: UploadFile = File(...),
    membership: dict = Depends(require_project_admin),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in {".xlsx", ".csv", ".zip"}:
        raise HTTPException(status_code=400, detail="Supported formats: XLSX, CSV, ZIP")
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            total = 0
            while chunk := await file.read(65536):
                total += len(chunk)
                if total > WB_FUNNEL_REPORT_MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Uploaded report is too large")
                temp_file.write(chunk)
        report = parse_wb_funnel_report(temp_path)
        result = import_funnel_report(
            project_id=project_id,
            original_filename=file.filename,
            created_by_user_id=membership.get("user_id"),
            report=report,
        )
        return WBFunnelImportResponse(**result)
    except WBFunnelReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get(
    "/projects/{project_id}/wildberries/funnel-report/imports",
    response_model=WBFunnelImportListResponse,
)
async def get_wb_funnel_report_imports(
    project_id: int = Path(...),
    limit: int = Query(50, ge=1, le=200),
    _membership: dict = Depends(get_project_membership),
):
    rows = list_funnel_report_imports(project_id, limit)
    return WBFunnelImportListResponse(items=[WBFunnelImportListItem(**row) for row in rows])
