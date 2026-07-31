"""Create an auditable pre-migration backup of an EcomCore deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILE = REPO_ROOT / "infra" / "docker" / "docker-compose.prod.yml"
BACKUP_TABLES = (
    "projects",
    "project_marketplaces",
    "products",
    "marketplace_products",
    "internal_data_snapshots",
    "internal_products",
    "internal_catalog_products",
    "marketplace_product_mappings",
    "wb_feedback_snapshots",
    "wb_financial_events",
)
PERSISTENT_VOLUMES = ("internal_data", "wb_content_history")
SECRET_PATHS = (
    "/run/secrets/project_secrets_key",
    "/run/secrets/project_proxy_secret_key",
)


def _run(
    command: Sequence[str],
    *,
    stdout: BinaryIO | int | None = subprocess.PIPE,
    input_file: BinaryIO | None = None,
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
    result = _run(command, check=check)
    return result.stdout.decode("utf-8", errors="replace").strip()


def _compose_prefix(compose_file: Path, project_name: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--file",
        str(compose_file),
    ]


def _ensure_external_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.expanduser().resolve()
    repo = REPO_ROOT.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        raise ValueError("Backup output must be outside the Git repository")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _postgres_query(compose: Sequence[str], sql: str) -> str:
    command = [
        *compose,
        "exec",
        "-T",
        "postgres",
        "sh",
        "-lc",
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "$1"',
        "ecomcore-backup",
        sql,
    ]
    return _text(command)


def _database_inventory(compose: Sequence[str]) -> dict[str, int]:
    inventory: dict[str, int] = {}
    for table in BACKUP_TABLES:
        exists = _postgres_query(compose, f"SELECT to_regclass('public.{table}') IS NOT NULL")
        if exists != "t":
            inventory[table] = -1
            continue
        inventory[table] = int(_postgres_query(compose, f'SELECT COUNT(*) FROM "{table}"'))
    return inventory


def _service_container(compose: Sequence[str], service: str) -> str | None:
    container_id = _text([*compose, "ps", "-q", service], check=False)
    return container_id or None


def _service_images(compose: Sequence[str]) -> dict[str, dict[str, str]]:
    images: dict[str, dict[str, str]] = {}
    for service in ("api", "worker", "beat", "frontend", "postgres"):
        container_id = _service_container(compose, service)
        if not container_id:
            continue
        raw = _text(
            ["docker", "inspect", "--format", "{{.Config.Image}}|{{.Image}}", container_id]
        )
        configured, _, image_id = raw.partition("|")
        images[service] = {"configured": configured, "image_id": image_id}
    return images


def _secret_fingerprints(compose: Sequence[str]) -> dict[str, str | None]:
    if not _service_container(compose, "api"):
        return {path: None for path in SECRET_PATHS}
    fingerprints: dict[str, str | None] = {}
    for secret_path in SECRET_PATHS:
        code = (
            "import hashlib,pathlib;"
            f"p=pathlib.Path({secret_path!r});"
            "print(hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'MISSING')"
        )
        value = _text([*compose, "exec", "-T", "api", "python", "-c", code])
        fingerprints[secret_path] = None if value == "MISSING" else value
    return fingerprints


def _resolve_compose_volume(project_name: str, logical_name: str) -> str:
    names = _text(
        [
            "docker",
            "volume",
            "ls",
            "--filter",
            f"label=com.docker.compose.project={project_name}",
            "--filter",
            f"label=com.docker.compose.volume={logical_name}",
            "--format",
            "{{.Name}}",
        ]
    ).splitlines()
    if len(names) != 1:
        raise RuntimeError(
            f"Expected one Docker volume for {logical_name!r}, found {len(names)}"
        )
    return names[0]


def _configured_volumes(compose: Sequence[str]) -> set[str]:
    return {
        line.strip()
        for line in _text([*compose, "config", "--volumes"]).splitlines()
        if line.strip()
    }


def _archive_volume(
    *,
    project_name: str,
    logical_name: str,
    stage_dir: Path,
    archive_image: str,
) -> tuple[str, str]:
    volume_name = _resolve_compose_volume(project_name, logical_name)
    filename = f"volume-{logical_name}.tar.gz"
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--mount",
            f"type=volume,source={volume_name},target=/source,readonly",
            "--mount",
            f"type=bind,source={stage_dir},target=/backup",
            archive_image,
            "sh",
            "-c",
            f"cd /source && tar -czf /backup/{filename} .",
        ]
    )
    return volume_name, filename


def _dump_database(compose: Sequence[str], destination: Path) -> None:
    with destination.open("wb") as handle:
        _run(
            [
                *compose,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-lc",
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z6 --no-owner --no-acl',
            ],
            stdout=handle,
        )
    if destination.stat().st_size == 0:
        raise RuntimeError("pg_dump produced an empty archive")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_backup(args: argparse.Namespace) -> Path:
    compose_file = Path(args.compose_file).expanduser().resolve()
    if not compose_file.is_file():
        raise FileNotFoundError(f"Compose file not found: {compose_file}")
    output_dir = _ensure_external_output_dir(Path(args.output_dir))
    compose = _compose_prefix(compose_file, args.project_name)
    if not _service_container(compose, "postgres"):
        raise RuntimeError("PostgreSQL service is not running")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_dir = output_dir / f"ecomcore-pre-migration-{timestamp}"
    if final_dir.exists():
        raise FileExistsError(f"Backup destination already exists: {final_dir}")
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.partial-", dir=output_dir))
    os.chmod(stage_dir, 0o700)

    images = _service_images(compose)
    secret_fingerprints = _secret_fingerprints(compose)
    stopped_services: list[str] = []
    try:
        if not args.online:
            for service in ("api", "worker", "beat"):
                if _service_container(compose, service):
                    stopped_services.append(service)
            if stopped_services:
                _run([*compose, "stop", "--timeout", "30", *stopped_services])

        inventory = _database_inventory(compose)
        unvalidated_foreign_keys = int(
            _postgres_query(
                compose,
                "SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated",
            )
        )
        alembic_revisions = _postgres_query(
            compose,
            "SELECT version_num FROM alembic_version ORDER BY version_num",
        ).splitlines()
        _dump_database(compose, stage_dir / "database.dump")

        archived_volumes: dict[str, dict[str, str]] = {}
        configured_volumes = _configured_volumes(compose)
        skipped_unconfigured_volumes: list[str] = []
        if not args.skip_volumes:
            for logical_name in PERSISTENT_VOLUMES:
                if logical_name not in configured_volumes:
                    skipped_unconfigured_volumes.append(logical_name)
                    continue
                volume_name, filename = _archive_volume(
                    project_name=args.project_name,
                    logical_name=logical_name,
                    stage_dir=stage_dir,
                    archive_image=args.archive_image,
                )
                archived_volumes[logical_name] = {
                    "docker_volume": volume_name,
                    "archive": filename,
                }

        git_commit = _text(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"])
        metadata = {
            "format_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "compose_project": args.project_name,
            "compose_file": compose_file.name,
            "postgres_image": images.get("postgres", {}).get("configured", "postgres:16"),
            "alembic_revisions": alembic_revisions,
            "database_inventory": inventory,
            "unvalidated_foreign_keys": unvalidated_foreign_keys,
            "service_images": images,
            "volumes": archived_volumes,
            "volumes_not_configured": skipped_unconfigured_volumes,
            "quiesced_services": stopped_services,
            "secret_key_sha256": secret_fingerprints,
            "secret_key_material_included": False,
        }
        _write_json(stage_dir / "metadata.json", metadata)

        checksums = {
            path.name: _sha256(path)
            for path in sorted(stage_dir.iterdir())
            if path.is_file() and path.name != "checksums.json"
        }
        _write_json(stage_dir / "checksums.json", checksums)
        for path in stage_dir.iterdir():
            if path.is_file():
                os.chmod(path, 0o600)
        stage_dir.rename(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    finally:
        if stopped_services:
            _run([*compose, "up", "-d", *stopped_services])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Existing secure directory outside the repository")
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE))
    parser.add_argument("--project-name", default="ecomcore")
    parser.add_argument("--archive-image", default="alpine:3.20")
    parser.add_argument(
        "--online",
        action="store_true",
        help="Do not stop API/worker/beat; database dump remains consistent but file volumes may move",
    )
    parser.add_argument("--skip-volumes", action="store_true", help="Back up PostgreSQL only")
    return parser


def main() -> int:
    try:
        backup_dir = create_backup(_parser().parse_args())
    except Exception as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"BACKUP CREATED: {backup_dir}")
    print("NEXT: run scripts/verify_production_backup.py against this directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
