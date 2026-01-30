"""Encryption utilities for proxy secrets using Fernet (symmetric encryption).

Uses PROJECT_PROXY_SECRET_KEY environment variable for encryption key.
If key is not set, uses a persistent dev key stored in a file (development only).
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet

_CACHED_KEY: Optional[bytes] = None
_KEY_FILE_ENV = "PROJECT_PROXY_SECRET_KEY_FILE"
_DEFAULT_KEY_FILE = "/app/.project_proxy_secret_key"


def _key_file_path() -> str:
    return os.getenv(_KEY_FILE_ENV, _DEFAULT_KEY_FILE)


def has_project_proxy_secrets_key() -> bool:
    """True if we have a stable key configured (env or persisted file)."""
    if os.getenv("PROJECT_PROXY_SECRET_KEY"):
        return True
    return os.path.exists(_key_file_path())


def _get_encryption_key() -> bytes:
    """Return Fernet key for proxy secrets.

    Expected format: base64 urlsafe-encoded 32-byte key (Fernet.generate_key()).
    """
    key_str = os.getenv("PROJECT_PROXY_SECRET_KEY")

    if not key_str:
        # Development fallback: persist a generated Fernet key to a file mounted with the app.
        global _CACHED_KEY
        if _CACHED_KEY is not None:
            return _CACHED_KEY

        path = _key_file_path()
        try:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    key = f.read().strip()
            else:
                key = Fernet.generate_key()
                # Best effort write; if it fails we'll still keep it in-memory for this process.
                with open(path, "wb") as f:
                    f.write(key)
            _CACHED_KEY = key
            return key
        except Exception:
            key = Fernet.generate_key()
            _CACHED_KEY = key
            return key

    # Validate provided key is a valid Fernet key (base64, 32 bytes after decode)
    try:
        decoded = base64.urlsafe_b64decode(key_str.encode())
        if len(decoded) != 32:
            raise ValueError("Invalid PROJECT_PROXY_SECRET_KEY length")
        return key_str.encode()
    except Exception as e:
        raise ValueError("Invalid PROJECT_PROXY_SECRET_KEY (expected Fernet key)") from e


def encrypt_proxy_secret(plain: str) -> str:
    """Encrypt a proxy secret (e.g., password) using Fernet."""
    if plain is None or not str(plain).strip():
        raise ValueError("Secret cannot be empty")
    key = _get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(str(plain).encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_proxy_secret(token: str) -> str:
    """Decrypt a proxy secret using Fernet."""
    if token is None or not str(token).strip():
        raise ValueError("Encrypted secret cannot be empty")
    key = _get_encryption_key()
    fernet = Fernet(key)
    decrypted = fernet.decrypt(str(token).encode("utf-8"))
    return decrypted.decode("utf-8")

