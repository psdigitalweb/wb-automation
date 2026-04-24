#!/usr/bin/env python3
"""Run deterministic query profile extraction for one project/category scope."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}


def _running_inside_container() -> bool:
    return os.getenv("ECOMCORE_PROFILE_EXTRACTION_IN_DOCKER") == "1" or Path("/.dockerenv").exists()


def _load_env_defaults(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _declared_database_host() -> str | None:
    env_defaults = _load_env_defaults(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL") or env_defaults.get("DATABASE_URL")
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.hostname:
            return parsed.hostname
    return os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST")


def _should_reroute_to_docker() -> bool:
    if _running_inside_container():
        return False
    database_host = _declared_database_host()
    return bool(database_host and database_host.lower() in DOCKER_ONLY_DB_HOSTS)


def _rerun_in_api_container(argv: list[str]) -> int:
    compose_file = PROJECT_ROOT / "infra" / "docker" / "docker-compose.yml"
    ensure_stack_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "-d",
        "postgres",
        "api",
    ]
    exec_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-e",
        "ECOMCORE_PROFILE_EXTRACTION_IN_DOCKER=1",
        "api",
        "python",
        "scripts/run_query_profile_extraction.py",
        *argv,
    ]
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running query profile extraction in the api container...",
        file=sys.stderr,
    )
    try:
        ensure_result = subprocess.run(ensure_stack_command, cwd=PROJECT_ROOT)
        if ensure_result.returncode != 0:
            return ensure_result.returncode
        return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode
    except FileNotFoundError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Docker CLI not found. Install/start Docker Desktop and rerun the same command.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_api_container(sys.argv[1:])

    sys.path.insert(0, str(SRC_ROOT))

    from app.db import SessionLocal
    from app.services.seo.query_pipeline import run_query_profile_extraction

    parser = argparse.ArgumentParser(description="Run SEO query profile extraction")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id scope")
    parser.add_argument("--top-limit", type=int, default=20, help="Number of top profiles in diagnostics")
    parser.add_argument("--samples-limit", type=int, default=20, help="Number of sample profiles in diagnostics")
    parser.add_argument(
        "--refresh-hybrid",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh persisted hybrid projection if missing (default: enabled)",
    )
    parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print JSON output (default: enabled)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = run_query_profile_extraction(
            session,
            project_id=args.project_id,
            category_id=args.category_id,
            top_limit=max(1, int(args.top_limit)),
            samples_limit=max(1, int(args.samples_limit)),
            refresh_hybrid=bool(args.refresh_hybrid),
            persist=False,
        )
        if result.diagnostics.total_profiles_built == 0:
            session.rollback()
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "No query profiles built for project/category scope",
                        "project_id": args.project_id,
                        "category_id": args.category_id,
                    },
                    ensure_ascii=False,
                    indent=2 if args.pretty else None,
                ),
                file=sys.stderr,
            )
            return 2

        session.commit()
        print(
            json.dumps(
                {
                    "diagnostics": result.diagnostics.to_dict(),
                    "sample_profiles": [profile.to_dict() for profile in result.profiles[: max(1, int(args.samples_limit))]],
                },
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0
    except Exception as exc:
        session.rollback()
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "project_id": args.project_id,
                    "category_id": args.category_id,
                },
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
