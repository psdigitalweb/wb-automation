"""Safe local-disk archive for WB main photos."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from app import settings


_ALLOWED_HOST_SUFFIXES = (
    ".wbbasket.ru",
    ".wb.ru",
    ".wbstatic.net",
)
_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


@dataclass(frozen=True)
class ArchivedPhoto:
    sha256: str
    storage_path: str
    source_url: str
    content_type: Optional[str]
    file_size: int
    reused: bool


def _is_allowed_photo_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == suffix.lstrip(".") or host.endswith(suffix)
        for suffix in _ALLOWED_HOST_SUFFIXES
    )


def _safe_extension(content_type: Optional[str], url: str) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[normalized_type]
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    guessed = mimetypes.guess_extension(normalized_type) if normalized_type else None
    return guessed if guessed in {".jpg", ".png", ".webp", ".avif"} else ".img"


class LocalMainPhotoStorage:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = Path(root or settings.WB_CONTENT_MEDIA_DIR).expanduser().resolve()

    def resolve_storage_path(self, storage_path: str) -> Path:
        candidate = (self.root / storage_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Invalid archived photo path")
        return candidate

    async def archive(self, *, project_id: int, nm_id: int, source_url: str) -> ArchivedPhoto:
        if not _is_allowed_photo_url(source_url):
            raise ValueError("WB main photo URL uses an untrusted host")

        max_bytes = max(1, int(settings.WB_CONTENT_MEDIA_MAX_FILE_SIZE_MB)) * 1024 * 1024
        timeout = max(1, int(settings.WB_CONTENT_MEDIA_DOWNLOAD_TIMEOUT_SECONDS))
        digest = hashlib.sha256()
        downloaded = 0
        content_type: Optional[str] = None
        temp_path: Optional[Path] = None

        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".wb-main-photo-",
            suffix=".tmp",
            dir=self.root,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    async with client.stream("GET", source_url) as response:
                        response.raise_for_status()
                        if not _is_allowed_photo_url(str(response.url)):
                            raise ValueError("WB main photo redirected to an untrusted host")
                        content_type = response.headers.get("content-type")
                        if content_type and not content_type.lower().startswith("image/"):
                            raise ValueError("WB main photo response is not an image")
                        async for chunk in response.aiter_bytes():
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                raise ValueError("WB main photo exceeds configured maximum size")
                            digest.update(chunk)
                            temp_file.write(chunk)
                if downloaded == 0:
                    raise ValueError("WB main photo response is empty")
            except Exception:
                temp_file.close()
                temp_path.unlink(missing_ok=True)
                raise

        sha256 = digest.hexdigest()
        extension = _safe_extension(content_type, source_url)
        relative = Path(f"project-{int(project_id)}") / f"nm-{int(nm_id)}" / f"{sha256}{extension}"
        destination = self.resolve_storage_path(str(relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        reused = destination.exists()
        if reused:
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, destination)

        return ArchivedPhoto(
            sha256=sha256,
            storage_path=str(relative).replace("\\", "/"),
            source_url=source_url,
            content_type=(content_type or "").split(";", 1)[0].strip() or None,
            file_size=downloaded,
            reused=reused,
        )
