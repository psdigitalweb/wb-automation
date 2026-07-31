from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.utils import secrets_encryption
from scripts.rotate_project_secrets_key import audit_encrypted_tokens


def _configure_key_ring(monkeypatch, *, primary: bytes, previous: bytes | None) -> None:
    monkeypatch.setenv("PROJECT_SECRETS_KEY", primary.decode())
    monkeypatch.delenv("PROJECT_SECRETS_KEY_FILE", raising=False)
    monkeypatch.delenv("PROJECT_SECRETS_PREVIOUS_KEY_FILE", raising=False)
    if previous is None:
        monkeypatch.delenv("PROJECT_SECRETS_PREVIOUS_KEY", raising=False)
    else:
        monkeypatch.setenv("PROJECT_SECRETS_PREVIOUS_KEY", previous.decode())
    secrets_encryption._CACHED_KEY = None


def test_urlsafe_fernet_environment_key_is_not_treated_as_password():
    key = Fernet.generate_key()
    while b"-" not in key and b"_" not in key:
        key = Fernet.generate_key()

    assert secrets_encryption._derive_environment_key(key.decode()) == key


def test_key_ring_decrypts_previous_tokens_and_encrypts_with_primary(monkeypatch):
    primary_key = Fernet.generate_key()
    previous_key = Fernet.generate_key()
    _configure_key_ring(
        monkeypatch,
        primary=primary_key,
        previous=previous_key,
    )

    previous_token = Fernet(previous_key).encrypt(b"wb-token").decode()
    assert secrets_encryption.decrypt_token(previous_token) == "wb-token"

    new_token = secrets_encryption.encrypt_token("new-wb-token")
    assert Fernet(primary_key).decrypt(new_token.encode()) == b"new-wb-token"
    with pytest.raises(InvalidToken):
        Fernet(previous_key).decrypt(new_token.encode())


def test_rotate_token_reencrypts_previous_token_with_primary(monkeypatch):
    primary_key = Fernet.generate_key()
    previous_key = Fernet.generate_key()
    _configure_key_ring(
        monkeypatch,
        primary=primary_key,
        previous=previous_key,
    )
    previous_token = Fernet(previous_key).encrypt(b"wb-token").decode()

    rotated = secrets_encryption.rotate_token(previous_token)

    assert Fernet(primary_key).decrypt(rotated.encode()) == b"wb-token"
    with pytest.raises(InvalidToken):
        Fernet(previous_key).decrypt(rotated.encode())


def test_rotation_audit_reports_primary_previous_and_invalid_tokens():
    primary = Fernet(Fernet.generate_key())
    previous = Fernet(Fernet.generate_key())
    key_ring = MultiFernet([primary, previous])
    tokens = [
        primary.encrypt(b"primary").decode(),
        previous.encrypt(b"previous").decode(),
        "not-a-fernet-token",
    ]

    audit = audit_encrypted_tokens(
        tokens,
        primary=primary,
        key_ring=key_ring,
    )

    assert audit.total == 3
    assert audit.encrypted_with_primary == 1
    assert audit.requires_rotation == 1
    assert audit.invalid == 1


def test_identical_previous_key_is_not_added_to_key_ring(monkeypatch):
    primary_key = Fernet.generate_key()
    _configure_key_ring(
        monkeypatch,
        primary=primary_key,
        previous=primary_key,
    )

    assert len(secrets_encryption.get_project_secrets_fernets()) == 1
    with pytest.raises(ValueError, match="distinct previous"):
        secrets_encryption.rotate_token(
            Fernet(primary_key).encrypt(b"wb-token").decode()
        )
