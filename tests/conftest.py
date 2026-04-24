from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest


def _ensure_src_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


_ensure_src_on_path()


def _safe_node_id(node_name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_.-]+", "_", str(node_name or "test"))


@pytest.fixture
def tmp_path(request) -> Path:
    """Sandbox-friendly tmp_path fixture.

    Some environments deny access to pytest's default temp roots (e.g., %TEMP% and
    `pytest-of-*` directories). Provide a workspace-local temp directory with
    deterministic cleanup.
    """

    base = Path(__file__).resolve().parent / "_runtime_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{_safe_node_id(request.node.name)}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
