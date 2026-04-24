"""Category profile loader service — Iteration 2 (WS-C).

Loads the active :class:`SeoCategoryProfile` for a given category and exposes a
small frozen dataclass shape that ``matcher_v2`` (and any future profile-aware
caller) can consume without knowing about ORM types.

Design constraints (see
``docs/seo-module/implementation-plan/05_backend_contract_changes.md``):

* The loader is the single read entrypoint. Writers are the seed scripts under
  ``scripts/seed_seo_category_profile_*``; runtime code never mutates this row.
* When no active profile exists for a category, ``load_active_profile`` returns
  ``None``. Callers fall back to the legacy in-code dictionaries (which are the
  source from which the 812 profile was seeded), preserving the current path.
  This keeps the change additive: introducing the profile system does not
  break the existing matcher behavior on any not-yet-seeded category.
* Profile *contents* are intentionally frozen objects — the matcher must not
  rely on mutability or in-place updates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SeoCategoryProfile


class CategoryProfileError(Exception):
    """Base error for category profile lookup."""


@dataclass(frozen=True)
class CategoryProfile:
    """Frozen view of one active ``SeoCategoryProfile`` row.

    The shape mirrors the JSON contract documented in
    ``config/seo/category_profiles/<category>.json``.
    """

    profile_id: int
    project_id: int
    category_id: int
    version: str
    payload: Mapping[str, Any]
    source_note: str | None = None

    @property
    def term_groups(self) -> Mapping[str, Mapping[str, list[str]]]:
        groups = self.payload.get("term_groups") if isinstance(self.payload, Mapping) else None
        return groups if isinstance(groups, Mapping) else {}

    @property
    def conflict_rules(self) -> Mapping[str, Any]:
        rules = self.payload.get("conflict_rules") if isinstance(self.payload, Mapping) else None
        return rules if isinstance(rules, Mapping) else {}

    @property
    def bucket_cutoffs(self) -> Mapping[str, float]:
        cutoffs = self.payload.get("bucket_cutoffs") if isinstance(self.payload, Mapping) else None
        return cutoffs if isinstance(cutoffs, Mapping) else {}

    @property
    def user_bucket_labels(self) -> Mapping[str, str]:
        labels = self.payload.get("user_bucket_labels") if isinstance(self.payload, Mapping) else None
        return labels if isinstance(labels, Mapping) else {}


def load_active_profile(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> CategoryProfile | None:
    """Return the active profile row for ``(project_id, category_id)``, if any.

    Returns ``None`` when no active profile is seeded — callers MUST keep their
    legacy fallback path active in that case so the candidate matcher does not
    silently change behavior on uncovered categories.
    """

    row = session.scalars(
        select(SeoCategoryProfile)
        .where(
            SeoCategoryProfile.project_id == int(project_id),
            SeoCategoryProfile.category_id == int(category_id),
            SeoCategoryProfile.is_active.is_(True),
        )
        .order_by(desc(SeoCategoryProfile.updated_at), desc(SeoCategoryProfile.id))
    ).first()
    if row is None:
        return None
    return CategoryProfile(
        profile_id=int(row.id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        version=str(row.version),
        payload=dict(row.payload or {}),
        source_note=row.source_note,
    )


def get_active_profile_version(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    fallback: str = "default_iter1",
) -> str:
    """Return ``profile.version`` if active, else the iteration-1 sentinel.

    Useful for matcher trace columns where we want a stable, queryable string
    in every row regardless of seed status.
    """

    profile = load_active_profile(session, project_id=project_id, category_id=category_id)
    if profile is None:
        return fallback
    return profile.version


__all__ = [
    "CategoryProfile",
    "CategoryProfileError",
    "get_active_profile_version",
    "load_active_profile",
]
