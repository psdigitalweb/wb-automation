"""Admin endpoints for category-profile inspection, derive, and activation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.deps import allow_local_debug_read
from app.models import SeoCategoryProfile, SeoCategoryProfileDeriveRun
from app.schemas.seo_category_profile import (
    CategoryProfileActivateResponse,
    CategoryProfileDeriveRequest,
    CategoryProfileDeriveResponse,
    CategoryProfileDeriveRunListResponse,
    CategoryProfileDeriveRunSummary,
    CategoryProfileDetail,
    CategoryProfileListResponse,
    CategoryProfileSummary,
)
from app.services.seo.category_profile_admin import (
    CategoryProfileActivationError,
    CategoryProfileAdminError,
    CategoryProfileNotFoundError,
    activate_category_profile,
    get_category_profile,
    list_category_profiles,
    list_derive_runs,
    rollback_to_profile,
)
from app.services.seo.category_profile_derive import CategoryProfileDeriveError, derive_category_profile


router = APIRouter(prefix="/api/v1", tags=["seo-category-profile"])


def _iso(dt: object) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else ""


def _self_check_status(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    self_check = payload.get("self_check")
    if not isinstance(self_check, dict):
        return None
    value = self_check.get("status")
    return str(value) if isinstance(value, str) else None


def _summary_from_row(row: SeoCategoryProfile) -> CategoryProfileSummary:
    payload = dict(row.payload or {})
    return CategoryProfileSummary(
        id=int(row.id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        version=str(row.version),
        is_active=bool(row.is_active),
        self_check_status=_self_check_status(payload),
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        source_note=row.source_note,
    )


def _detail_from_row(row: SeoCategoryProfile) -> CategoryProfileDetail:
    summary = _summary_from_row(row)
    return CategoryProfileDetail(**summary.model_dump(), payload=dict(row.payload or {}))


def _derive_run_summary(row: SeoCategoryProfileDeriveRun) -> CategoryProfileDeriveRunSummary:
    self_check = dict(row.self_check_json or {})
    return CategoryProfileDeriveRunSummary(
        id=int(row.id),
        run_id=str(row.run_id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        status=str(row.status),
        method=str(row.method),
        profile_id=int(row.profile_id) if row.profile_id is not None else None,
        profile_version=str(row.profile_version) if row.profile_version is not None else None,
        self_check_status=_self_check_status({"self_check": self_check}),
        started_at=_iso(row.started_at),
        finished_at=_iso(row.finished_at) if row.finished_at is not None else None,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        error_message=row.error_message,
    )


@router.get(
    "/projects/{project_id}/seo/category-profiles",
    response_model=CategoryProfileListResponse,
)
async def get_category_profiles_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int | None = Query(default=None, description="Optional WB category scope"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> CategoryProfileListResponse:
        session = SessionLocal()
        try:
            rows = list_category_profiles(
                session,
                project_id=int(project_id),
                category_id=int(category_id) if category_id is not None else None,
            )
            return CategoryProfileListResponse(items=[_summary_from_row(row) for row in rows])
        finally:
            session.close()

    return await run_in_threadpool(_fetch)


@router.get(
    "/projects/{project_id}/seo/category-profiles/{profile_id}",
    response_model=CategoryProfileDetail,
)
async def get_category_profile_endpoint(
    project_id: int = Path(..., description="Project ID"),
    profile_id: int = Path(..., description="Profile ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> CategoryProfileDetail:
        session = SessionLocal()
        try:
            row = get_category_profile(session, int(profile_id))
            if int(row.project_id) != int(project_id):
                raise CategoryProfileNotFoundError(f"Category profile {int(profile_id)} was not found")
            return _detail_from_row(row)
        finally:
            session.close()

    try:
        return await run_in_threadpool(_fetch)
    except CategoryProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/seo/category-profile-derive-runs",
    response_model=CategoryProfileDeriveRunListResponse,
)
async def get_category_profile_derive_runs_endpoint(
    project_id: int = Path(..., description="Project ID"),
    category_id: int | None = Query(default=None, description="Optional WB category scope"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _fetch() -> CategoryProfileDeriveRunListResponse:
        session = SessionLocal()
        try:
            rows = list_derive_runs(
                session,
                project_id=int(project_id),
                category_id=int(category_id) if category_id is not None else None,
            )
            return CategoryProfileDeriveRunListResponse(
                items=[_derive_run_summary(row) for row in rows]
            )
        finally:
            session.close()

    return await run_in_threadpool(_fetch)


@router.post(
    "/projects/{project_id}/seo/category-profiles/derive",
    response_model=CategoryProfileDeriveResponse,
)
async def post_category_profile_derive_endpoint(
    request: CategoryProfileDeriveRequest,
    project_id: int = Path(..., description="Project ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    if request.activate:
        raise HTTPException(
            status_code=409,
            detail="Activation is a separate Step 7 action. Derive with dry_run=false, then call the activate endpoint.",
        )

    def _run() -> CategoryProfileDeriveResponse:
        session = SessionLocal()
        try:
            result = derive_category_profile(
                project_id=int(project_id),
                category_id=int(request.category_id),
                session=session,
                activate=False,
                dry_run=bool(request.dry_run),
            )
            if request.dry_run:
                session.rollback()
            else:
                session.commit()
            return CategoryProfileDeriveResponse(
                run_id=result.run_id,
                project_id=int(project_id),
                category_id=int(request.category_id),
                profile_id=result.profile_id,
                profile_version=result.profile_version,
                snapshot_path=str(result.snapshot_path),
                source_note=result.source_note,
                status=result.status,
                self_check=result.self_check,
                payload=dict(result.profile_payload),
                is_active=False,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_run)
    except (CategoryProfileDeriveError, NotImplementedError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/seo/category-profiles/{profile_id}/activate",
    response_model=CategoryProfileActivateResponse,
)
async def post_category_profile_activate_endpoint(
    project_id: int = Path(..., description="Project ID"),
    profile_id: int = Path(..., description="Profile ID"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _activate() -> CategoryProfileActivateResponse:
        session = SessionLocal()
        try:
            row = get_category_profile(session, int(profile_id))
            if int(row.project_id) != int(project_id):
                raise CategoryProfileNotFoundError(f"Category profile {int(profile_id)} was not found")
            activated = activate_category_profile(session, int(profile_id))
            session.commit()
            return CategoryProfileActivateResponse(profile=_summary_from_row(activated))
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_activate)
    except CategoryProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CategoryProfileActivationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CategoryProfileAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/seo/category-profiles/{profile_id}/rollback",
    response_model=CategoryProfileActivateResponse,
)
async def post_category_profile_rollback_endpoint(
    project_id: int = Path(..., description="Project ID"),
    profile_id: int = Path(..., description="Profile ID to reactivate"),
    membership: dict = Depends(allow_local_debug_read),
):
    del membership

    def _rollback() -> CategoryProfileActivateResponse:
        session = SessionLocal()
        try:
            row = get_category_profile(session, int(profile_id))
            if int(row.project_id) != int(project_id):
                raise CategoryProfileNotFoundError(f"Category profile {int(profile_id)} was not found")
            activated = rollback_to_profile(session, int(profile_id))
            session.commit()
            return CategoryProfileActivateResponse(profile=_summary_from_row(activated))
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        return await run_in_threadpool(_rollback)
    except CategoryProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CategoryProfileActivationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CategoryProfileAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

