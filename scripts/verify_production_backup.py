"""Verify checksums and restore an EcomCore backup into isolated PostgreSQL 16."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Sequence


def _run(
    command: Sequence[str],
    *,
    input_file: BinaryIO | None = None,
    stdout: int | None = subprocess.PIPE,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        list(command),
        stdin=input_file,
        stdout=stdout,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Command failed ({command[0]}): {stderr}")
    return result


def _text(command: Sequence[str], *, check: bool = True) -> str:
    return _run(command, check=check).stdout.decode("utf-8", errors="replace").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_checksums(backup_dir: Path) -> None:
    checksums = _load_json(backup_dir / "checksums.json")
    if not isinstance(checksums, dict) or not checksums:
        raise RuntimeError("checksums.json is empty or invalid")
    for filename, expected in checksums.items():
        path = backup_dir / filename
        if not path.is_file():
            raise RuntimeError(f"Backup artifact is missing: {filename}")
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch: {filename}")


def _verify_tar_archive(path: Path) -> int:
    count = 0
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts:
                raise RuntimeError(f"Unsafe path in {path.name}: {member.name}")
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or ".." in link.parts:
                    raise RuntimeError(f"Unsafe link in {path.name}: {member.linkname}")
            count += 1
    return count


def _query(container: str, sql: str) -> str:
    return _text(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "restore_user",
            "-d",
            "restore_db",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ]
    )


def _restored_inventory(container: str, expected: dict[str, int]) -> dict[str, int]:
    actual: dict[str, int] = {}
    for table, expected_count in expected.items():
        if expected_count == -1:
            exists = _query(container, f"SELECT to_regclass('public.{table}') IS NOT NULL")
            actual[table] = -1 if exists == "f" else int(_query(container, f'SELECT COUNT(*) FROM "{table}"'))
            continue
        actual[table] = int(_query(container, f'SELECT COUNT(*) FROM "{table}"'))
    return actual


def verify_backup(backup_dir: Path, postgres_image: str | None = None) -> dict[str, Any]:
    backup_dir = backup_dir.expanduser().resolve()
    metadata_path = backup_dir / "metadata.json"
    dump_path = backup_dir / "database.dump"
    if not metadata_path.is_file() or not dump_path.is_file():
        raise RuntimeError("Backup must contain metadata.json and database.dump")
    _verify_checksums(backup_dir)
    metadata = _load_json(metadata_path)
    if metadata.get("format_version") != 1:
        raise RuntimeError("Unsupported backup format")

    volume_members: dict[str, int] = {}
    for volume in metadata.get("volumes", {}).values():
        archive_name = volume["archive"]
        volume_members[archive_name] = _verify_tar_archive(backup_dir / archive_name)

    image = postgres_image or metadata.get("postgres_image") or "postgres:16"
    if not str(image).startswith("postgres:16"):
        raise RuntimeError(f"Restore verification requires PostgreSQL 16, got {image!r}")
    suffix = uuid.uuid4().hex[:12]
    container = f"ecomcore-restore-verify-{suffix}"
    password = secrets.token_urlsafe(24)
    started = False
    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--env",
                "POSTGRES_USER=restore_user",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "--env",
                "POSTGRES_DB=restore_db",
                str(image),
            ]
        )
        started = True
        for _ in range(60):
            ready = _run(
                ["docker", "exec", container, "pg_isready", "-U", "restore_user", "-d", "restore_db"],
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Temporary PostgreSQL did not become ready")

        with dump_path.open("rb") as handle:
            _run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "restore_user",
                    "-d",
                    "restore_db",
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                ],
                input_file=handle,
                stdout=subprocess.DEVNULL,
            )

        expected_inventory = metadata["database_inventory"]
        actual_inventory = _restored_inventory(container, expected_inventory)
        mismatches = {
            table: {"expected": expected_inventory[table], "actual": actual_inventory[table]}
            for table in expected_inventory
            if expected_inventory[table] != actual_inventory[table]
        }
        if mismatches:
            raise RuntimeError(f"Restored row counts differ: {mismatches}")
        revisions = _query(container, "SELECT version_num FROM alembic_version ORDER BY version_num").splitlines()
        if revisions != metadata["alembic_revisions"]:
            raise RuntimeError(
                f"Alembic revision mismatch: expected {metadata['alembic_revisions']}, got {revisions}"
            )
        invalid_foreign_keys = int(
            _query(container, "SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")
        )
        expected_invalid_foreign_keys = int(metadata.get("unvalidated_foreign_keys", 0))
        if invalid_foreign_keys != expected_invalid_foreign_keys:
            raise RuntimeError(
                "Unvalidated foreign key count differs: "
                f"expected {expected_invalid_foreign_keys}, got {invalid_foreign_keys}"
            )
        return {
            "status": "verified",
            "git_commit": metadata["git_commit"],
            "alembic_revisions": revisions,
            "database_inventory": actual_inventory,
            "unvalidated_foreign_keys": invalid_foreign_keys,
            "volume_archive_members": volume_members,
        }
    finally:
        if started:
            if not container.startswith("ecomcore-restore-verify-"):
                raise RuntimeError("Refusing to remove an unexpected container")
            _run(["docker", "rm", "--force", container], check=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir")
    parser.add_argument("--postgres-image")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = verify_backup(Path(args.backup_dir), args.postgres_image)
    except Exception as exc:
        print(f"RESTORE VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
