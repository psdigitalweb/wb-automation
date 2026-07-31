from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts.production_backup import (
    REPO_ROOT,
    _compose_prefix,
    _ensure_external_output_dir,
    _sha256,
)
from scripts.verify_production_backup import _verify_checksums, _verify_tar_archive


def test_backup_output_must_be_outside_repository() -> None:
    with pytest.raises(ValueError, match="outside the Git repository"):
        _ensure_external_output_dir(REPO_ROOT / "artifacts" / "backup")


def test_compose_prefix_uses_explicit_env_file() -> None:
    command = _compose_prefix(
        Path("/srv/ecomcore/docker-compose.prod.yml"),
        "ecomcore",
        Path("/srv/ecomcore/.env"),
    )

    assert command == [
        "docker",
        "compose",
        "--project-name",
        "ecomcore",
        "--env-file",
        "/srv/ecomcore/.env",
        "--file",
        "/srv/ecomcore/docker-compose.prod.yml",
    ]


def test_checksum_verification_detects_changed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "database.dump"
    artifact.write_bytes(b"original")
    (tmp_path / "checksums.json").write_text(
        json.dumps({artifact.name: _sha256(artifact)}),
        encoding="utf-8",
    )
    _verify_checksums(tmp_path)

    artifact.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        _verify_checksums(tmp_path)


def test_volume_archive_rejects_parent_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "volume.tar.gz"
    payload = b"unsafe"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("../escape")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(RuntimeError, match="Unsafe path"):
        _verify_tar_archive(archive_path)
