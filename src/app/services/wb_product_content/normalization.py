"""Canonical WB card content and field-level diff helpers."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


NORMALIZATION_VERSION = "wb-content-v1"
_SPACE_RE = re.compile(r"[ \t]+")


def _normalized_text(value: Any, *, multiline: bool = False) -> Optional[str]:
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if multiline:
        return "\n".join(_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")).strip()
    return _SPACE_RE.sub(" ", text).strip()


def _first(item: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item.get(key)
    return None


def _canonical_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json(value[key])
            for key in sorted(value.keys(), key=lambda candidate: str(candidate))
        }
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json(item) for item in value]
    if isinstance(value, str):
        return _normalized_text(value, multiline=True)
    return value


def _characteristic_sort_key(value: Any) -> str:
    if not isinstance(value, Mapping):
        return json.dumps(_canonical_json(value), ensure_ascii=False, sort_keys=True)
    characteristic_id = _first(value, "id", "charcID", "characteristicID", "characteristicId")
    name = _first(value, "name", "title", "characteristicName")
    return f"{characteristic_id if characteristic_id is not None else ''}:{_normalized_text(name) or ''}"


def _normalize_characteristics(value: Any) -> List[Any]:
    if not isinstance(value, list):
        return []
    canonical = [_canonical_json(item) for item in value]
    return sorted(canonical, key=_characteristic_sort_key)


def _normalize_dimensions(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _canonical_json(value)


def _normalize_sizes(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, Any]] = []
    for size in value:
        if not isinstance(size, Mapping):
            continue
        normalized = {
            "chrtID": _first(size, "chrtID", "chrtId", "chrt_id"),
            "techSize": _normalized_text(_first(size, "techSize", "tech_size")),
            "wbSize": _normalized_text(_first(size, "wbSize", "wb_size")),
        }
        if any(item is not None for item in normalized.values()):
            result.append(normalized)
    return sorted(
        result,
        key=lambda item: (
            str(item.get("chrtID") or ""),
            item.get("techSize") or "",
            item.get("wbSize") or "",
        ),
    )


def _normalize_photos(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, Any]] = []
    for position, photo in enumerate(value):
        if isinstance(photo, str):
            normalized_photo: Dict[str, Any] = {"url": photo}
        elif isinstance(photo, Mapping):
            normalized_photo = {
                str(key): _canonical_json(photo[key])
                for key in sorted(photo.keys(), key=str)
                if photo.get(key) is not None
            }
        else:
            continue
        normalized_photo["position"] = position
        normalized_photo["isMain"] = position == 0
        result.append(normalized_photo)
    return result


def main_photo_url(content: Mapping[str, Any]) -> Optional[str]:
    photos = content.get("photos")
    if not isinstance(photos, list) or not photos:
        return None
    first_photo = photos[0]
    if isinstance(first_photo, str):
        return first_photo
    if not isinstance(first_photo, Mapping):
        return None
    for key in ("big", "original", "url", "c900x1200", "c516x688", "c246x328", "square"):
        value = first_photo.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in first_photo.values():
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def normalize_wb_card_content(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the versioned subset of a WB Content API card."""
    photos = _first(item, "photos", "pics", "images")
    return {
        "vendorCode": _normalized_text(_first(item, "vendorCode", "vendor_code", "article")),
        "title": _normalized_text(_first(item, "title", "name")),
        "brand": _normalized_text(item.get("brand")),
        "subjectID": _first(item, "subjectID", "subject_id", "subjectId"),
        "subjectName": _normalized_text(_first(item, "subjectName", "subject_name", "subject")),
        "description": _normalized_text(item.get("description"), multiline=True),
        "dimensions": _normalize_dimensions(item.get("dimensions")),
        "characteristics": _normalize_characteristics(item.get("characteristics")),
        "sizes": _normalize_sizes(item.get("sizes")),
        "photos": _normalize_photos(photos),
        "needKiz": _first(item, "needKiz", "need_kiz"),
    }


def content_hash(content: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _canonical_json(content),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


_CHANGE_TYPE_BY_FIELD = {
    "vendorCode": "identity",
    "title": "content",
    "brand": "content",
    "description": "content",
    "subjectID": "category",
    "subjectName": "category",
    "characteristics": "characteristics",
    "dimensions": "dimensions",
    "sizes": "variants",
    "photos": "media",
    "needKiz": "marking",
}


def _photo_identity(photo: Any) -> str:
    if isinstance(photo, Mapping):
        cleaned = {key: value for key, value in photo.items() if key not in {"position", "isMain"}}
        return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(photo)


def _photo_diff(old: Any, new: Any) -> Dict[str, Any]:
    old_list = old if isinstance(old, list) else []
    new_list = new if isinstance(new, list) else []
    old_ids = [_photo_identity(photo) for photo in old_list]
    new_ids = [_photo_identity(photo) for photo in new_list]
    old_set = set(old_ids)
    new_set = set(new_ids)
    return {
        "old": deepcopy(old_list),
        "new": deepcopy(new_list),
        "added": [new_list[index] for index, value in enumerate(new_ids) if value not in old_set],
        "removed": [old_list[index] for index, value in enumerate(old_ids) if value not in new_set],
        "orderChanged": old_ids != new_ids and old_set == new_set,
        "mainChanged": (old_ids[0] if old_ids else None) != (new_ids[0] if new_ids else None),
    }


def build_content_diff(
    old: Optional[Mapping[str, Any]],
    new: Mapping[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    if old is None:
        return {}, []
    changes: Dict[str, Any] = {}
    change_types: List[str] = []
    for field in new.keys():
        old_value = old.get(field)
        new_value = new.get(field)
        if old_value == new_value:
            continue
        if field == "photos":
            changes[field] = _photo_diff(old_value, new_value)
        else:
            changes[field] = {"old": deepcopy(old_value), "new": deepcopy(new_value)}
        change_type = _CHANGE_TYPE_BY_FIELD.get(field, "content")
        if change_type not in change_types:
            change_types.append(change_type)
    return changes, change_types


def parse_card_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}
