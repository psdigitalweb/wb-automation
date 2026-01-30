"""Project-scoped proxy settings for WB storefront parsing (frontend_prices only)."""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.utils.httpx_client import make_async_client
from app.db_project_proxy_settings import (
    get_project_proxy_settings,
    set_last_test,
    upsert_project_proxy_settings,
)
from app.deps import get_current_active_user, get_project_membership, require_project_admin
from app.schemas.project_proxy_settings import (
    ProjectProxySettingsResponse,
    ProjectProxySettingsUpdate,
    ProjectProxyTestResponse,
)
from app.utils.proxy_secrets_encryption import decrypt_proxy_secret, encrypt_proxy_secret

router = APIRouter(prefix="/api/v1", tags=["project-proxy-settings"])


def _to_response(row: dict) -> ProjectProxySettingsResponse:
    return ProjectProxySettingsResponse(
        enabled=bool(row.get("enabled")),
        scheme=(row.get("scheme") or "http"),
        host=(row.get("host") or ""),
        port=int(row.get("port") or 0),
        username=row.get("username"),
        rotate_mode=(row.get("rotate_mode") or "fixed"),
        test_url=(row.get("test_url") or "https://www.wildberries.ru"),
        last_test_at=row.get("last_test_at"),
        last_test_ok=row.get("last_test_ok"),
        last_test_error=row.get("last_test_error"),
        password_set=bool(row.get("password_encrypted")),
    )


def _validate_settings_for_enabled_use(*, enabled: bool, scheme: str, host: str, port: int, rotate_mode: str, test_url: str) -> None:
    scheme_norm = str(scheme or "").strip().lower()
    rotate_norm = str(rotate_mode or "").strip().lower()
    host_norm = str(host or "").strip()

    if rotate_norm != "fixed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rotate_mode must be 'fixed'")
    if scheme_norm not in ("http", "https"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheme must be 'http' or 'https'")
    if test_url is None or not str(test_url).strip() or any(ch.isspace() for ch in str(test_url).strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="test_url must be a non-empty string without whitespace")

    if enabled:
        if not host_norm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="host is required when proxy is enabled")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="port must be in range 1..65535")


def _build_proxy_url(*, scheme: str, host: str, port: int, username: Optional[str], password: Optional[str]) -> str:
    scheme_norm = str(scheme).strip().lower()
    host_norm = str(host).strip()

    auth = ""
    if username is not None and str(username) != "":
        user_escaped = quote(str(username), safe="")
        if password is not None and str(password) != "":
            pass_escaped = quote(str(password), safe="")
            auth = f"{user_escaped}:{pass_escaped}@"
        else:
            auth = f"{user_escaped}@"

    return f"{scheme_norm}://{auth}{host_norm}:{int(port)}"


@router.get(
    "/projects/{project_id}/settings/proxy",
    response_model=ProjectProxySettingsResponse,
)
async def get_project_proxy_settings_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    row = get_project_proxy_settings(int(project_id))
    return _to_response(row)


@router.put(
    "/projects/{project_id}/settings/proxy",
    response_model=ProjectProxySettingsResponse,
)
async def update_project_proxy_settings_endpoint(
    body: ProjectProxySettingsUpdate,
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    existing = get_project_proxy_settings(int(project_id))

    enabled = bool(body.enabled) if body.enabled is not None else bool(existing.get("enabled"))
    scheme = body.scheme if body.scheme is not None else (existing.get("scheme") or "http")
    host = body.host if body.host is not None else (existing.get("host") or "")
    port = int(body.port) if body.port is not None else int(existing.get("port") or 0)
    rotate_mode = body.rotate_mode if body.rotate_mode is not None else (existing.get("rotate_mode") or "fixed")
    test_url = body.test_url if body.test_url is not None else (existing.get("test_url") or "https://www.wildberries.ru")

    username: Optional[str] = None
    if body.username is not None:
        username = body.username  # may be empty string => explicit clear

    password_encrypted: Optional[str] = None
    if body.password is not None:
        # IMPORTANT: empty string means "do not change" (per requirements)
        if str(body.password).strip():
            try:
                password_encrypted = encrypt_proxy_secret(str(body.password).strip())
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        else:
            password_encrypted = None

    _validate_settings_for_enabled_use(
        enabled=enabled,
        scheme=scheme,
        host=host,
        port=port,
        rotate_mode=rotate_mode,
        test_url=test_url,
    )

    saved = upsert_project_proxy_settings(
        project_id=int(project_id),
        enabled=enabled,
        scheme=str(scheme).strip().lower(),
        host=str(host).strip(),
        port=int(port),
        username=username,
        password_encrypted=password_encrypted,
        rotate_mode=str(rotate_mode).strip().lower(),
        test_url=str(test_url).strip(),
    )
    return _to_response(saved)


@router.post(
    "/projects/{project_id}/settings/proxy/test",
    response_model=ProjectProxyTestResponse,
)
async def test_project_proxy_settings_endpoint(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin),
):
    settings = get_project_proxy_settings(int(project_id))

    enabled = bool(settings.get("enabled"))
    scheme = (settings.get("scheme") or "http")
    host = (settings.get("host") or "")
    port = int(settings.get("port") or 0)
    rotate_mode = (settings.get("rotate_mode") or "fixed")
    test_url = (settings.get("test_url") or "https://www.wildberries.ru")

    # Test makes sense only when enabled, to match how ingestion applies it.
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proxy is disabled")

    _validate_settings_for_enabled_use(
        enabled=True,
        scheme=scheme,
        host=host,
        port=port,
        rotate_mode=rotate_mode,
        test_url=test_url,
    )

    username = settings.get("username")
    password_plain: Optional[str] = None
    if settings.get("password_encrypted"):
        try:
            password_plain = decrypt_proxy_secret(settings["password_encrypted"])
        except Exception:
            set_last_test(project_id=int(project_id), ok=False, error="decrypt_failed")
            return ProjectProxyTestResponse(ok=False, error="decrypt_failed", status_code=None, elapsed_ms=0)

    proxy_url = _build_proxy_url(
        scheme=scheme,
        host=host,
        port=port,
        username=username,
        password=password_plain,
    )

    timeout_s = 20.0
    timeout = httpx.Timeout(timeout_s, connect=timeout_s, read=timeout_s, write=timeout_s, pool=timeout_s)

    started = time.perf_counter()
    last_error: Optional[str] = None
    last_status: Optional[int] = None

    for attempt in range(1, 3):  # 2 tries
        try:
            async with make_async_client(timeout=timeout, proxy_url=proxy_url, follow_redirects=True) as client:
                r = await client.get(str(test_url))
                last_status = int(r.status_code)
                if 200 <= r.status_code < 400:
                    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
                    set_last_test(project_id=int(project_id), ok=True, error=None)
                    return ProjectProxyTestResponse(ok=True, status_code=last_status, elapsed_ms=elapsed_ms)

                last_error = f"http_status_{last_status}"
        except Exception as e:
            last_error = f"{type(e).__name__}"
        if attempt < 2:
            await asyncio.sleep(0.5 * attempt)

    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    set_last_test(project_id=int(project_id), ok=False, error=last_error or "unknown_error")
    return ProjectProxyTestResponse(ok=False, error=last_error or "unknown_error", status_code=last_status, elapsed_ms=elapsed_ms)

