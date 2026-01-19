"""Encryption utilities for sensitive data using Fernet (symmetric encryption).

Uses PROJECT_SECRETS_KEY environment variable for encryption key.
If key is not set, uses a persistent dev key stored in a file (development only).
"""

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_CACHED_KEY: Optional[bytes] = None
_KEY_FILE_ENV = "PROJECT_SECRETS_KEY_FILE"
_DEFAULT_KEY_FILE = "/app/.project_secrets_key"


def _key_file_path() -> str:
    return os.getenv(_KEY_FILE_ENV, _DEFAULT_KEY_FILE)


def has_project_secrets_key() -> bool:
    """True if we have a stable key configured (env or persisted file)."""
    if os.getenv("PROJECT_SECRETS_KEY"):
        return True
    return os.path.exists(_key_file_path())


def _get_encryption_key() -> bytes:
    """Get or generate encryption key from environment variable.
    
    Returns:
        bytes: Fernet encryption key (32 bytes, base64-encoded)
    
    Raises:
        ValueError: If PROJECT_SECRETS_KEY is invalid
    """
    key_str = os.getenv("PROJECT_SECRETS_KEY")
    
    if not key_str:
        # Development fallback: persist a generated Fernet key to a file mounted with the app.
        # This makes encrypt/decrypt stable across container restarts without leaking tokens in plaintext.
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
            # Last resort: generate in-memory (will break decrypt after restart).
            key = Fernet.generate_key()
            _CACHED_KEY = key
            return key
    
    # Try to use key directly (if it's a valid Fernet key)
    try:
        # Fernet keys are base64-encoded 32-byte keys
        # Try to decode to validate
        base64.b64decode(key_str)
        if len(base64.b64decode(key_str)) == 32:
            return key_str.encode()
    except Exception:
        pass
    
    # If not a valid Fernet key, derive from password using PBKDF2
    # This allows using a password-like string as PROJECT_SECRETS_KEY
    password = key_str.encode()
    salt = b'wb_automation_salt'  # Fixed salt (in production, use random salt per project)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key


def encrypt_token(token: str) -> str:
    """Encrypt a token using Fernet encryption.
    
    Args:
        token: Plain text token to encrypt.
    
    Returns:
        str: Base64-encoded encrypted token.
    
    Raises:
        ValueError: If encryption fails.
    """
    if not token:
        raise ValueError("Token cannot be empty")
    
    key = _get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()  # Base64 string


def decrypt_token(encrypted_token: str) -> Optional[str]:
    """Decrypt a token using Fernet decryption.
    
    Args:
        encrypted_token: Base64-encoded encrypted token.
    
    Returns:
        str: Decrypted token, or None if decryption fails.
    """
    if not encrypted_token:
        return None
    
    try:
        key = _get_encryption_key()
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"decrypt_token: failed to decrypt token: {type(e).__name__}: {e}")
        return None

