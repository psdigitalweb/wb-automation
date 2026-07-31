#!/usr/bin/env python3
"""Run deterministic query scoring preparation for one project/category/SKU scope."""

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
    return os.getenv("ECOMCORE_SCORING_PREP_IN_DOCKER") == "1" or Path("/.dockerenv").exists()


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
        "worker",
    ]
    inline_runner = """
import json
import sys

sys.path.insert(0, '/app/src')

from app.db import SessionLocal
from app.services.seo.scoring.preparation import QueryScoringPreparationError, run_query_scoring_preparation


def _parse_flag(args, name, default):
    positive = f'--{name}'
    negative = f'--no-{name}'
    if positive in args:
        return True
    if negative in args:
        return False
    return default


def _parse_int(args, name):
    flag = f'--{name}'
    for index, value in enumerate(args):
        if value == flag and index + 1 < len(args):
            return int(args[index + 1])
    raise SystemExit(json.dumps({'ok': False, 'error': f'Missing required argument: {flag}'}, ensure_ascii=False))


cli_args = sys.argv[1:]
project_id = _parse_int(cli_args, 'project-id')
category_id = _parse_int(cli_args, 'category-id')
nm_id = _parse_int(cli_args, 'nm-id')
top_limit = next((int(cli_args[index + 1]) for index, value in enumerate(cli_args[:-1]) if value == '--top-limit'), 20)
samples_limit = next((int(cli_args[index + 1]) for index, value in enumerate(cli_args[:-1]) if value == '--samples-limit'), 20)
refresh_hybrid = _parse_flag(cli_args, 'refresh-hybrid', True)
pretty = _parse_flag(cli_args, 'pretty', True)

session = SessionLocal()
try:
    result = run_query_scoring_preparation(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        top_limit=max(1, top_limit),
        samples_limit=max(1, samples_limit),
        refresh_hybrid=bool(refresh_hybrid),
    )
    session.commit()
    print(json.dumps(
        {
            'sku_evidence_summary': result.sku_evidence_summary.to_dict(),
            'diagnostics': result.diagnostics.to_dict(),
            'sample_preparations': [item.to_dict() for item in result.preparations[: max(1, samples_limit)]],
        },
        ensure_ascii=False,
        indent=2 if pretty else None,
        default=lambda value: value.to_dict() if hasattr(value, 'to_dict') else str(value),
    ))
except QueryScoringPreparationError as exc:
    session.rollback()
    print(json.dumps(
        {
            'ok': False,
            'error': str(exc),
            'project_id': project_id,
            'category_id': category_id,
            'nm_id': nm_id,
        },
        ensure_ascii=False,
        indent=2 if pretty else None,
    ), file=sys.stderr)
    raise SystemExit(2)
except Exception as exc:
    session.rollback()
    print(json.dumps(
        {
            'ok': False,
            'error': str(exc),
            'project_id': project_id,
            'category_id': category_id,
            'nm_id': nm_id,
        },
        ensure_ascii=False,
        indent=2 if pretty else None,
    ), file=sys.stderr)
    raise SystemExit(1)
finally:
    session.close()
""".strip()
    exec_command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-e",
        "ECOMCORE_SCORING_PREP_IN_DOCKER=1",
        "worker",
        "python",
        "-c",
        inline_runner,
        *argv,
    ]
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running query scoring preparation in the worker container...",
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
    from app.services.seo.scoring.preparation import (
        QueryScoringPreparationError,
        run_query_scoring_preparation,
    )

    parser = argparse.ArgumentParser(description="Run SEO query scoring preparation")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id scope")
    parser.add_argument("--nm-id", required=True, type=int, help="WB nm_id of the target SKU")
    parser.add_argument("--top-limit", type=int, default=20, help="Number of top diagnostics items")
    parser.add_argument("--samples-limit", type=int, default=20, help="Number of sample preparations")
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
        result = run_query_scoring_preparation(
            session,
            project_id=args.project_id,
            category_id=args.category_id,
            nm_id=args.nm_id,
            top_limit=max(1, int(args.top_limit)),
            samples_limit=max(1, int(args.samples_limit)),
            refresh_hybrid=bool(args.refresh_hybrid),
        )
        session.commit()
        print(
            json.dumps(
                {
                    "sku_evidence_summary": result.sku_evidence_summary.to_dict(),
                    "diagnostics": result.diagnostics.to_dict(),
                    "sample_preparations": [item.to_dict() for item in result.preparations[: max(1, int(args.samples_limit))]],
                },
                ensure_ascii=False,
                indent=2 if args.pretty else None,
                default=lambda value: value.to_dict() if hasattr(value, "to_dict") else str(value),
            )
        )
        return 0
    except QueryScoringPreparationError as exc:
        session.rollback()
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "project_id": args.project_id,
                    "category_id": args.category_id,
                    "nm_id": args.nm_id,
                },
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        session.rollback()
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "project_id": args.project_id,
                    "category_id": args.category_id,
                    "nm_id": args.nm_id,
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
