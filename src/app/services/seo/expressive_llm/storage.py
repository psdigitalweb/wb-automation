"""File-based storage/cache for category expressive LLM artifacts (offline/precompute).

Iteration 19 constraint: avoid DB migrations; store artifacts on disk keyed by:
  project_id + category_id + model + prompt_version + input_hash
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import settings


_MODEL_SAFE_RE = re.compile(r"[^0-9a-zA-Z_.-]+")


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sanitize_model_id(model_id: str) -> str:
    value = str(model_id or "").strip()
    value = value.replace("/", "__").replace(":", "_")
    value = _MODEL_SAFE_RE.sub("_", value)
    return value or "unknown_model"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CategoryExpressiveCacheKey:
    project_id: int
    category_id: int
    model: str
    prompt_version: str
    input_hash: str

    def normalized(self) -> CategoryExpressiveCacheKey:
        return CategoryExpressiveCacheKey(
            project_id=int(self.project_id),
            category_id=int(self.category_id),
            model=str(self.model or "").strip(),
            prompt_version=str(self.prompt_version or "").strip(),
            input_hash=str(self.input_hash or "").strip(),
        )


@dataclass(frozen=True)
class StoredCategoryExpressiveArtifact:
    key: CategoryExpressiveCacheKey
    artifact_dir: Path
    meta: dict[str, Any]
    raw_response: dict[str, Any] | None
    parsed: dict[str, Any] | None
    validation: dict[str, Any] | None


class CategoryExpressiveStore:
    """File-based cache for category expressive artifacts."""

    def __init__(self, *, root_dir: str | Path | None = None) -> None:
        self._root_dir = Path(root_dir) if root_dir is not None else self._default_root_dir()

    @staticmethod
    def _default_root_dir() -> Path:
        # Allow override for experiments/tests without changing app settings.
        override = os.getenv("SEO_EXPRESSIVE_CACHE_DIR", "").strip()
        if override:
            return Path(override)
        return Path(settings.INTERNAL_DATA_DIR) / "seo_expressive_cache"

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def artifact_dir_for_key(self, *, key: CategoryExpressiveCacheKey) -> Path:
        return self._artifact_dir(key)

    def _artifact_dir(self, key: CategoryExpressiveCacheKey) -> Path:
        normalized = key.normalized()
        model_dir = _sanitize_model_id(normalized.model)
        return (
            self.root_dir
            / "cat_expr"
            / f"p{normalized.project_id}"
            / f"c{normalized.category_id}"
            / f"m_{model_dir}"
            / f"pv_{normalized.prompt_version}"
            / f"h_{normalized.input_hash}"
        )

    def _legacy_artifact_dir(self, key: CategoryExpressiveCacheKey) -> Path:
        """Legacy layout kept for backward compatibility with earlier spikes."""

        normalized = key.normalized()
        model_dir = _sanitize_model_id(normalized.model)
        return (
            self.root_dir
            / "category_expressive"
            / f"project_{normalized.project_id}"
            / f"category_{normalized.category_id}"
            / f"model_{model_dir}"
            / f"prompt_{normalized.prompt_version}"
            / f"input_{normalized.input_hash}"
        )

    def get(self, *, key: CategoryExpressiveCacheKey) -> StoredCategoryExpressiveArtifact | None:
        artifact_dir = self._artifact_dir(key)
        meta_path = artifact_dir / "meta.json"
        if not meta_path.exists():
            legacy_dir = self._legacy_artifact_dir(key)
            legacy_meta = legacy_dir / "meta.json"
            if not legacy_meta.exists():
                return None
            artifact_dir = legacy_dir
            meta_path = legacy_meta

        meta = _read_json(meta_path)
        raw_path = artifact_dir / "raw_response.json"
        parsed_path = artifact_dir / "parsed.json"
        validation_path = artifact_dir / "validation.json"

        raw_response = _read_json(raw_path) if raw_path.exists() else None
        parsed = _read_json(parsed_path) if parsed_path.exists() else None
        validation = _read_json(validation_path) if validation_path.exists() else None

        return StoredCategoryExpressiveArtifact(
            key=key.normalized(),
            artifact_dir=artifact_dir,
            meta=dict(meta) if isinstance(meta, dict) else {"meta": meta},
            raw_response=dict(raw_response) if isinstance(raw_response, dict) else raw_response,
            parsed=dict(parsed) if isinstance(parsed, dict) else parsed,
            validation=dict(validation) if isinstance(validation, dict) else validation,
        )

    def put(
        self,
        *,
        key: CategoryExpressiveCacheKey,
        raw_response: dict[str, Any],
        parsed: dict[str, Any],
        validation: dict[str, Any],
        overwrite: bool = False,
        extra_meta: dict[str, Any] | None = None,
    ) -> StoredCategoryExpressiveArtifact:
        normalized = key.normalized()
        artifact_dir = self._artifact_dir(normalized)
        meta_path = artifact_dir / "meta.json"
        if meta_path.exists() and not overwrite:
            existing = self.get(key=normalized)
            if existing is not None:
                return existing

        meta: dict[str, Any] = {
            "schema_version": "v1",
            "entity": "category_expressive",
            "created_at": _utc_now_iso(),
            "key": {
                "project_id": normalized.project_id,
                "category_id": normalized.category_id,
                "model": normalized.model,
                "prompt_version": normalized.prompt_version,
                "input_hash": normalized.input_hash,
            },
        }
        if extra_meta:
            meta["extra"] = dict(extra_meta)

        _write_json(meta_path, meta)
        _write_json(artifact_dir / "raw_response.json", raw_response)
        _write_json(artifact_dir / "parsed.json", parsed)
        _write_json(artifact_dir / "validation.json", validation)

        return StoredCategoryExpressiveArtifact(
            key=normalized,
            artifact_dir=artifact_dir,
            meta=meta,
            raw_response=raw_response,
            parsed=parsed,
            validation=validation,
        )
