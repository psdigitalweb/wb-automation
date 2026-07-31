"""Validate a Wildberries API token from the command line.

Usage:
    python scripts/validate_wb_token.py
    $env:WB_TOKEN_TO_CHECK="..."
    python scripts/validate_wb_token.py --token-env WB_TOKEN_TO_CHECK
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from app.utils.wb_token_validator import validate_wb_token  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Wildberries API token by calling WB API."
    )
    parser.add_argument(
        "--token-env",
        default="WB_TOKEN_TO_CHECK",
        help="Environment variable containing the token. Defaults to WB_TOKEN_TO_CHECK.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    token = os.getenv(args.token_env)
    if not token:
        token = getpass.getpass("WB token: ")

    is_valid, error_message = await validate_wb_token(token)
    if is_valid:
        print("VALID")
        return 0

    print(f"INVALID: {error_message or 'validation failed'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
