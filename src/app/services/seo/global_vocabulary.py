"""Read-only loader for global cross-category SEO vocabulary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "config" / "seo" / "global_vocabulary.json"
_REQUIRED_TOP_LEVEL_KEYS = (
    "schema_version",
    "audience_taxonomy",
    "audience_synonyms",
    "expressive_taxonomy",
    "expressive_synonyms",
    "recipient_synonyms",
    "color_taxonomy",
    "color_synonyms",
    "material_taxonomy",
    "material_synonyms",
)


@dataclass(frozen=True)
class GlobalVocabulary:
    """Immutable view over the shared SEO vocabulary JSON config."""

    schema_version: str
    audience_taxonomy: tuple[str, ...]
    audience_synonyms: Mapping[str, tuple[str, ...]]
    expressive_taxonomy: tuple[str, ...]
    expressive_synonyms: Mapping[str, tuple[str, ...]]
    recipient_synonyms: Mapping[str, str]
    color_taxonomy: tuple[str, ...]
    color_synonyms: Mapping[str, str]
    material_taxonomy: tuple[str, ...]
    material_synonyms: Mapping[str, tuple[str, ...]]


def _mapping_of_tuples(raw: object, section: str) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(raw, dict):
        raise ValueError(f"{section} must be a JSON object")
    normalized: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"{section} keys must be strings")
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{section}.{key} must be a list of strings")
        normalized[key] = tuple(value)
    return MappingProxyType(normalized)


def _mapping_of_strings(raw: object, section: str) -> Mapping[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"{section} must be a JSON object")
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"{section} must be a string-to-string mapping")
        normalized[key] = value
    return MappingProxyType(normalized)


def _tuple_of_strings(raw: object, section: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{section} must be a list of strings")
    return tuple(raw)


@lru_cache(maxsize=None)
def load_global_vocabulary(path: Path | None = None) -> GlobalVocabulary:
    """Load and validate the shared SEO vocabulary config from disk."""

    resolved_path = (path or _DEFAULT_PATH).resolve()
    raw = json.loads(resolved_path.read_text(encoding="utf-8"))

    missing_keys = [key for key in _REQUIRED_TOP_LEVEL_KEYS if key not in raw]
    if missing_keys:
        raise ValueError(f"Missing required global vocabulary sections: {', '.join(missing_keys)}")

    schema_version = raw.get("schema_version")
    assert schema_version == "global_vocabulary_v1", f"Unknown schema_version: {schema_version!r}"

    return GlobalVocabulary(
        schema_version=schema_version,
        audience_taxonomy=_tuple_of_strings(raw["audience_taxonomy"], "audience_taxonomy"),
        audience_synonyms=_mapping_of_tuples(raw["audience_synonyms"], "audience_synonyms"),
        expressive_taxonomy=_tuple_of_strings(raw["expressive_taxonomy"], "expressive_taxonomy"),
        expressive_synonyms=_mapping_of_tuples(raw["expressive_synonyms"], "expressive_synonyms"),
        recipient_synonyms=_mapping_of_strings(raw["recipient_synonyms"], "recipient_synonyms"),
        color_taxonomy=_tuple_of_strings(raw["color_taxonomy"], "color_taxonomy"),
        color_synonyms=_mapping_of_strings(raw["color_synonyms"], "color_synonyms"),
        material_taxonomy=_tuple_of_strings(raw["material_taxonomy"], "material_taxonomy"),
        material_synonyms=_mapping_of_tuples(raw["material_synonyms"], "material_synonyms"),
    )
