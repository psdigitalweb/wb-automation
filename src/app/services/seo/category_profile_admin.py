"""Admin helpers for listing, activating, and inspecting category profiles."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from app.models import SeoCategoryProfile, SeoCategoryProfileDeriveRun
from app.services.seo.category_profile import CategoryProfile, CategoryProfileError


class CategoryProfileAdminError(Exception):
    """Base error for category-profile admin actions."""


class CategoryProfileNotFoundError(CategoryProfileAdminError):
    """Raised when the requested profile row does not exist."""


class CategoryProfileActivationError(CategoryProfileAdminError):
    """Raised when activation would violate the profile safety contract."""


def _self_check_status(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    self_check = payload.get("self_check")
    if not isinstance(self_check, dict):
        return None
    status = self_check.get("status")
    return str(status) if isinstance(status, str) else None


def list_category_profiles(
    session: Session,
    project_id: int,
    category_id: int | None = None,
) -> list[SeoCategoryProfile]:
    """Return category-profile rows ordered newest-first within the project."""

    statement = select(SeoCategoryProfile).where(SeoCategoryProfile.project_id == int(project_id))
    if category_id is not None:
        statement = statement.where(SeoCategoryProfile.category_id == int(category_id))
    statement = statement.order_by(
        desc(SeoCategoryProfile.updated_at),
        desc(SeoCategoryProfile.id),
    )
    return list(session.scalars(statement).all())


def get_category_profile(session: Session, profile_id: int) -> SeoCategoryProfile:
    """Load one category-profile row or raise a typed not-found error."""

    row = session.get(SeoCategoryProfile, int(profile_id))
    if row is None:
        raise CategoryProfileNotFoundError(f"Category profile {int(profile_id)} was not found")
    return row


def list_derive_runs(
    session: Session,
    project_id: int,
    category_id: int | None = None,
) -> list[SeoCategoryProfileDeriveRun]:
    """Return derive-run rows ordered newest-first within the project."""

    statement = select(SeoCategoryProfileDeriveRun).where(
        SeoCategoryProfileDeriveRun.project_id == int(project_id)
    )
    if category_id is not None:
        statement = statement.where(SeoCategoryProfileDeriveRun.category_id == int(category_id))
    statement = statement.order_by(
        desc(SeoCategoryProfileDeriveRun.created_at),
        desc(SeoCategoryProfileDeriveRun.id),
    )
    return list(session.scalars(statement).all())


def activate_category_profile(session: Session, profile_id: int) -> SeoCategoryProfile:
    """Activate a passed/self-checked profile and deactivate siblings atomically."""

    row = get_category_profile(session, profile_id)
    try:
        CategoryProfile.from_payload(
            profile_id=int(row.id),
            project_id=int(row.project_id),
            category_id=int(row.category_id),
            version=str(row.version),
            payload=dict(row.payload or {}),
            source_note=row.source_note,
        )
    except CategoryProfileError as exc:
        raise CategoryProfileActivationError(
            f"Cannot activate profile {int(row.id)} with unsupported schema_version"
        ) from exc

    self_check_status = _self_check_status(dict(row.payload or {}))
    if self_check_status != "passed":
        raise CategoryProfileActivationError(
            f"Cannot activate profile {int(row.id)} because self_check.status={self_check_status!r}"
        )

    session.execute(
        update(SeoCategoryProfile)
        .where(
            SeoCategoryProfile.project_id == int(row.project_id),
            SeoCategoryProfile.category_id == int(row.category_id),
            SeoCategoryProfile.id != int(row.id),
        )
        .values(is_active=False)
    )
    row.is_active = True
    session.flush()

    active_count = int(
        session.scalar(
            select(func.count())
            .select_from(SeoCategoryProfile)
            .where(
                SeoCategoryProfile.project_id == int(row.project_id),
                SeoCategoryProfile.category_id == int(row.category_id),
                SeoCategoryProfile.is_active.is_(True),
            )
        )
        or 0
    )
    if active_count != 1:
        raise CategoryProfileActivationError(
            "Activation must leave exactly one active profile per project/category"
        )
    return row


def rollback_to_profile(session: Session, profile_id: int) -> SeoCategoryProfile:
    """Rollback is defined as activating a previous profile version."""

    return activate_category_profile(session, profile_id)

