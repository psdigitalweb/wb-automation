"""Helpers for deterministic category-profile snapshot paths and writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "config" / "seo" / "category_profiles"


def build_category_profile_snapshot_path(
    *,
    project_id: int,
    category_id: int,
    version: str,
    root_dir: Path | None = None,
) -> Path:
    """Return the deterministic snapshot path for one profile version."""

    root = (root_dir or _DEFAULT_ROOT).resolve()
    return root / str(int(project_id)) / str(int(category_id)) / f"{version}.json"


def resolve_category_profile_snapshot_path(
    *,
    project_id: int,
    category_id: int,
    version: str,
    out_path: Path | None = None,
) -> Path:
    """Resolve either an explicit output file or the default snapshot path."""

    if out_path is None:
        return build_category_profile_snapshot_path(
            project_id=project_id,
            category_id=category_id,
            version=version,
        )
    resolved = out_path.resolve()
    if resolved.suffix.lower() == ".json":
        return resolved
    return build_category_profile_snapshot_path(
        project_id=project_id,
        category_id=category_id,
        version=version,
        root_dir=resolved,
    )


def write_category_profile_snapshot(
    *,
    path: Path,
    payload: Mapping[str, Any],
    source_note: str | None,
) -> Path:
    """Persist one profile snapshot as a stable JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = dict(payload)
    if source_note is not None:
        snapshot["source_note"] = source_note
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
