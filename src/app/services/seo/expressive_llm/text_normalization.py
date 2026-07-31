"""Technical text normalization helpers (no semantic logic).

Rules (iteration 19):
- trim whitespace
- truncate to fixed max chars
- dedup by normalized key: lowercase + collapse whitespace + ё→е
"""

from __future__ import annotations

import re


_WS_RE = re.compile(r"\s+")


def trim(text_value: str | None) -> str:
    return str(text_value or "").strip()


def truncate(text_value: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    value = str(text_value or "")
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def dedupe_key(text_value: str | None) -> str:
    """Key used ONLY for deduping (not for display/evidence)."""

    value = trim(text_value).lower().replace("ё", "е")
    value = _WS_RE.sub(" ", value).strip()
    return value


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        key = dedupe_key(item)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

