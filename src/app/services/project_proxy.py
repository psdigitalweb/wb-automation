"""Project-scoped proxy configuration shared by storefront consumers."""

from __future__ import annotations

from urllib.parse import quote

from app.db_project_proxy_settings import get_project_proxy_settings
from app.utils.proxy_secrets_encryption import decrypt_proxy_secret


def get_frontend_prices_proxy_config(project_id: int) -> tuple[str | None, str | None]:
    """Return a credential-bearing proxy URL without exposing it to API responses."""
    settings = get_project_proxy_settings(int(project_id))
    if not bool(settings and settings.get("enabled")):
        return None, None

    scheme = str(settings.get("scheme") or "http").strip().lower()
    host = str(settings.get("host") or "").strip()
    port = int(settings.get("port") or 0)
    rotate_mode = str(settings.get("rotate_mode") or "fixed").strip().lower()
    if rotate_mode != "fixed":
        raise ValueError("proxy_invalid_rotate_mode")
    if scheme not in ("http", "https"):
        raise ValueError("proxy_invalid_scheme")
    if not host:
        raise ValueError("proxy_host_required")
    if port < 1 or port > 65535:
        raise ValueError("proxy_invalid_port")

    username = settings.get("username")
    password = None
    if settings.get("password_encrypted"):
        password = decrypt_proxy_secret(settings["password_encrypted"])

    auth = ""
    if username is not None and str(username) != "":
        auth = quote(str(username), safe="")
        if password is not None and str(password) != "":
            auth += f":{quote(str(password), safe='')}"
        auth += "@"
    return f"{scheme}://{auth}{host}:{port}", scheme
