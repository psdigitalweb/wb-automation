"""Tiny TTL cache with Redis primary and in-memory fallback.

Used for lightweight API response caching (e.g. Articles Base summary/coverage).
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from app import settings

_mem_cache: dict[str, tuple[float, Any]] = {}


def _mem_get(key: str) -> Any | None:
    item = _mem_cache.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at <= time.time():
        _mem_cache.pop(key, None)
        return None
    return value


def _mem_set(key: str, value: Any, ttl_s: int) -> None:
    _mem_cache[key] = (time.time() + ttl_s, value)


def get_json(key: str) -> Optional[dict]:
    """Return cached JSON object, or None."""
    # Try Redis first
    try:
        import redis  # type: ignore

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    # Fallback to in-memory
    value = _mem_get(key)
    if isinstance(value, dict):
        return value
    return None


def set_json(key: str, value: dict, ttl_s: int) -> None:
    """Cache JSON object."""
    # Try Redis first
    try:
        import redis  # type: ignore

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.setex(key, ttl_s, json.dumps(value, ensure_ascii=False))
        return
    except Exception:
        pass

    _mem_set(key, value, ttl_s)


def delete(key: str) -> None:
    """Delete cache key (best-effort)."""
    try:
        import redis  # type: ignore

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete(key)
    except Exception:
        pass
    _mem_cache.pop(key, None)

