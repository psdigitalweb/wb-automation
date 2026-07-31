"""Text normalization shared only by the competitor-analysis pipeline."""

from __future__ import annotations

import re
from typing import Any


MAX_FIELD_CHARS = 1200
_SPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)


def normalize_text(value: Any) -> str:
    normalized = _SPACE_RE.sub(" ", str(value or "")).strip()
    normalized = _EMAIL_RE.sub("[email удалён]", normalized)
    normalized = _PHONE_RE.sub("[телефон удалён]", normalized)
    return normalized[:MAX_FIELD_CHARS]
