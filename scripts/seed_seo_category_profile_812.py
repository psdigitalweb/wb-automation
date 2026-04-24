"""Seed the active ``SeoCategoryProfile`` for category 812.

Reads the JSON manifest from
``config/seo/category_profiles/812.json`` and inserts (or updates) one
``SeoCategoryProfile`` row per project that owns category 812. Idempotent:
re-running the script is a no-op when the manifest version + payload are
unchanged for a given (project_id, category_id, version) tuple.

Usage:

    python -m scripts.seed_seo_category_profile_812 --project-id 1
    python -m scripts.seed_seo_category_profile_812 --project-id 1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a top-level script.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SeoCategoryProfile  # noqa: E402


MANIFEST_PATH = ROOT / "config" / "seo" / "category_profiles" / "812.json"


def _load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _seed_profile(session, *, project_id: int, manifest: dict, dry_run: bool) -> dict:
    category_id = int(manifest["category_id"])
    version = str(manifest["version"])
    source_note = manifest.get("source_note")
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"source_note"}
    }

    existing = session.scalars(
        select(SeoCategoryProfile).where(
            SeoCategoryProfile.project_id == int(project_id),
            SeoCategoryProfile.category_id == int(category_id),
            SeoCategoryProfile.version == version,
        )
    ).first()

    if existing is not None:
        unchanged = (
            existing.is_active is True
            and dict(existing.payload or {}) == payload
            and (existing.source_note or "") == (source_note or "")
        )
        if unchanged:
            return {"action": "noop", "profile_id": int(existing.id)}
        if dry_run:
            return {"action": "would_update", "profile_id": int(existing.id)}
        existing.payload = payload
        existing.source_note = source_note
        existing.is_active = True
        session.flush()
        # Deactivate other versions for the same category to keep "active" unique
        # in practice (the schema only enforces unique on version).
        session.execute(
            SeoCategoryProfile.__table__.update()
            .where(
                SeoCategoryProfile.project_id == int(project_id),
                SeoCategoryProfile.category_id == int(category_id),
                SeoCategoryProfile.id != int(existing.id),
            )
            .values(is_active=False)
        )
        return {"action": "updated", "profile_id": int(existing.id)}

    if dry_run:
        return {"action": "would_create", "version": version}

    # Deactivate any prior active version before inserting the new one.
    session.execute(
        SeoCategoryProfile.__table__.update()
        .where(
            SeoCategoryProfile.project_id == int(project_id),
            SeoCategoryProfile.category_id == int(category_id),
        )
        .values(is_active=False)
    )
    row = SeoCategoryProfile(
        project_id=int(project_id),
        category_id=int(category_id),
        version=version,
        is_active=True,
        payload=payload,
        source_note=source_note,
    )
    session.add(row)
    session.flush()
    return {"action": "created", "profile_id": int(row.id)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the SEO category profile for 812.")
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="Project ID that owns the SEO scope for this seed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the action without committing.",
    )
    args = parser.parse_args()

    manifest = _load_manifest()
    session = SessionLocal()
    try:
        result = _seed_profile(
            session,
            project_id=args.project_id,
            manifest=manifest,
            dry_run=bool(args.dry_run),
        )
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps({"category_id": int(manifest["category_id"]), **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
