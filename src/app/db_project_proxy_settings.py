"""DB helpers for project-scoped proxy settings (frontend_prices only)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from app.db import engine


_DEFAULTS: Dict[str, Any] = {
    "project_id": None,
    "enabled": False,
    "scheme": "http",
    "host": "",
    "port": 0,
    "username": None,
    "password_encrypted": None,
    "rotate_mode": "fixed",
    "test_url": "https://www.wildberries.ru",
    "last_test_at": None,
    "last_test_ok": None,
    "last_test_error": None,
    "created_at": None,
    "updated_at": None,
}


def get_project_proxy_settings(project_id: int) -> Dict[str, Any]:
    """Get proxy settings for a project. Never 404: returns defaults if missing."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT
                      project_id,
                      enabled,
                      scheme,
                      host,
                      port,
                      username,
                      password_encrypted,
                      rotate_mode,
                      test_url,
                      last_test_at,
                      last_test_ok,
                      last_test_error,
                      created_at,
                      updated_at
                    FROM project_proxy_settings
                    WHERE project_id = :project_id
                    """
                ),
                {"project_id": int(project_id)},
            )
            .mappings()
            .first()
        )
        if not row:
            return {**_DEFAULTS, "project_id": int(project_id)}
        data = dict(row)
        # Ensure all expected keys exist (for forward/backward compatibility)
        return {**_DEFAULTS, **data, "project_id": int(project_id)}


def upsert_project_proxy_settings(
    *,
    project_id: int,
    enabled: bool,
    scheme: str,
    host: str,
    port: int,
    username: Optional[str],
    password_encrypted: Optional[str],
    rotate_mode: str,
    test_url: str,
) -> Dict[str, Any]:
    """Create or update proxy settings.

    Rules:
    - password_encrypted: COALESCE (None -> keep existing)
    - username: COALESCE (None -> keep existing; empty string -> explicit value)
    """
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    INSERT INTO project_proxy_settings (
                      project_id,
                      enabled,
                      scheme,
                      host,
                      port,
                      username,
                      password_encrypted,
                      rotate_mode,
                      test_url,
                      created_at,
                      updated_at
                    )
                    VALUES (
                      :project_id,
                      :enabled,
                      :scheme,
                      :host,
                      :port,
                      :username,
                      :password_encrypted,
                      :rotate_mode,
                      :test_url,
                      now(),
                      now()
                    )
                    ON CONFLICT (project_id)
                    DO UPDATE SET
                      enabled = EXCLUDED.enabled,
                      scheme = EXCLUDED.scheme,
                      host = EXCLUDED.host,
                      port = EXCLUDED.port,
                      username = COALESCE(EXCLUDED.username, project_proxy_settings.username),
                      password_encrypted = COALESCE(EXCLUDED.password_encrypted, project_proxy_settings.password_encrypted),
                      rotate_mode = EXCLUDED.rotate_mode,
                      test_url = EXCLUDED.test_url,
                      updated_at = now()
                    RETURNING
                      project_id,
                      enabled,
                      scheme,
                      host,
                      port,
                      username,
                      password_encrypted,
                      rotate_mode,
                      test_url,
                      last_test_at,
                      last_test_ok,
                      last_test_error,
                      created_at,
                      updated_at
                    """
                ),
                {
                    "project_id": int(project_id),
                    "enabled": bool(enabled),
                    "scheme": str(scheme),
                    "host": str(host),
                    "port": int(port),
                    "username": username,
                    "password_encrypted": password_encrypted,
                    "rotate_mode": str(rotate_mode),
                    "test_url": str(test_url),
                },
            )
            .mappings()
            .first()
        )
        return {**_DEFAULTS, **dict(row), "project_id": int(project_id)}


def set_last_test(*, project_id: int, ok: bool, error: Optional[str]) -> Dict[str, Any]:
    """Persist last test status (upsert-safe)."""
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    INSERT INTO project_proxy_settings (
                      project_id,
                      enabled,
                      scheme,
                      host,
                      port,
                      rotate_mode,
                      test_url,
                      last_test_at,
                      last_test_ok,
                      last_test_error,
                      created_at,
                      updated_at
                    )
                    VALUES (
                      :project_id,
                      false,
                      'http',
                      '',
                      0,
                      'fixed',
                      'https://www.wildberries.ru',
                      now(),
                      :ok,
                      :error,
                      now(),
                      now()
                    )
                    ON CONFLICT (project_id)
                    DO UPDATE SET
                      last_test_at = now(),
                      last_test_ok = :ok,
                      last_test_error = :error,
                      updated_at = now()
                    RETURNING
                      project_id,
                      enabled,
                      scheme,
                      host,
                      port,
                      username,
                      password_encrypted,
                      rotate_mode,
                      test_url,
                      last_test_at,
                      last_test_ok,
                      last_test_error,
                      created_at,
                      updated_at
                    """
                ),
                {"project_id": int(project_id), "ok": bool(ok), "error": error},
            )
            .mappings()
            .first()
        )
        return {**_DEFAULTS, **dict(row), "project_id": int(project_id)}

