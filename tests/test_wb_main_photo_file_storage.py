from __future__ import annotations

import asyncio

import pytest

from app.services.wb_product_content.file_storage import (
    LocalMainPhotoStorage,
    _is_allowed_photo_url,
)


def test_only_https_wb_photo_hosts_are_allowed():
    assert _is_allowed_photo_url("https://basket-01.wbbasket.ru/photo.jpg")
    assert _is_allowed_photo_url("https://images.wbstatic.net/photo.webp")
    assert not _is_allowed_photo_url("http://basket-01.wbbasket.ru/photo.jpg")
    assert not _is_allowed_photo_url("https://wbbasket.ru.attacker.example/photo.jpg")
    assert not _is_allowed_photo_url("https://example.com/photo.jpg")


def test_storage_path_cannot_escape_root(tmp_path):
    storage = LocalMainPhotoStorage(str(tmp_path))

    with pytest.raises(ValueError):
        storage.resolve_storage_path("../../secret.txt")

    safe = storage.resolve_storage_path("project-1/nm-2/hash.webp")
    assert tmp_path.resolve() in safe.parents


def test_archive_writes_once_and_reuses_same_file(tmp_path, monkeypatch):
    payload = b"fake-webp-image"

    class _Response:
        headers = {"content-type": "image/webp"}
        url = "https://basket-01.wbbasket.ru/photo.webp"

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(
        "app.services.wb_product_content.file_storage.httpx.AsyncClient",
        _Client,
    )
    storage = LocalMainPhotoStorage(str(tmp_path))

    first = asyncio.run(
        storage.archive(
            project_id=1,
            nm_id=2,
            source_url="https://basket-01.wbbasket.ru/photo.webp",
        )
    )
    second = asyncio.run(
        storage.archive(
            project_id=1,
            nm_id=2,
            source_url="https://basket-01.wbbasket.ru/photo.webp",
        )
    )

    assert first.reused is False
    assert second.reused is True
    assert first.sha256 == second.sha256
    assert storage.resolve_storage_path(first.storage_path).read_bytes() == payload
    assert len(list(tmp_path.rglob("*.webp"))) == 1
