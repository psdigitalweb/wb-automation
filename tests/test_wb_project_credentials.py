import pytest

from app.utils import get_project_marketplace_token as credentials_module


def _marketplace_connection(
    *,
    encrypted_token: str | None = "encrypted-token",
    settings: object = None,
    is_enabled: bool = True,
) -> dict[str, object]:
    return {
        "is_enabled": is_enabled,
        "api_token_encrypted": encrypted_token,
        "settings_json": settings,
    }


def test_wb_credentials_accept_token_without_brand_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(),
    )
    monkeypatch.setattr(credentials_module, "decrypt_token", lambda _value: "wb-token")

    credentials = credentials_module.get_wb_credentials_for_project(42)

    assert credentials == {"token": "wb-token", "brand_id": None}


def test_wb_api_token_does_not_require_brand_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(),
    )
    monkeypatch.setattr(credentials_module, "decrypt_token", lambda _value: "wb-token")

    assert credentials_module.get_wb_api_token_for_project(42) == "wb-token"


def test_wb_api_token_returns_none_for_disabled_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(
            is_enabled=False
        ),
    )

    assert credentials_module.get_wb_api_token_for_project(42) is None


def test_wb_api_token_rejects_enabled_connection_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(
            encrypted_token=None
        ),
    )

    with pytest.raises(ValueError, match="WB not connected"):
        credentials_module.get_wb_api_token_for_project(42)


def test_wb_credentials_keep_optional_brand_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(
            settings={"brand_id": "123"}
        ),
    )
    monkeypatch.setattr(credentials_module, "decrypt_token", lambda _value: "wb-token")

    credentials = credentials_module.get_wb_credentials_for_project(42)

    assert credentials == {"token": "wb-token", "brand_id": 123}


def test_wb_credentials_accept_legacy_settings_token_without_brand_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(
            encrypted_token=None,
            settings={"api_token": "legacy-token"},
        ),
    )

    credentials = credentials_module.get_wb_credentials_for_project(42)

    assert credentials == {"token": "legacy-token", "brand_id": None}


def test_wb_credentials_report_saved_token_decryption_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(),
    )
    monkeypatch.setattr(credentials_module, "decrypt_token", lambda _value: None)

    with pytest.raises(ValueError, match="cannot be decrypted"):
        credentials_module.get_wb_credentials_for_project(42)


def test_wb_credentials_reject_enabled_connection_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        credentials_module,
        "_get_project_marketplace_by_code",
        lambda _project_id, _marketplace_code: _marketplace_connection(
            encrypted_token=None
        ),
    )

    with pytest.raises(ValueError, match="WB not connected"):
        credentials_module.get_wb_credentials_for_project(42)
