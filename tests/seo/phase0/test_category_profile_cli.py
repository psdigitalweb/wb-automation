from __future__ import annotations

import io
import importlib.util
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from sqlalchemy import Column, Integer, Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SeoCategoryProfile


ROOT = Path(__file__).resolve().parents[3]


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _session_factory() -> sessionmaker:
    _ensure_projects_stub()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    return SessionLocal


def _load_script_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_derive_cli_help_works() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "scripts.derive_category_profile", "--help"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--persist" in result.stdout


def test_activate_cli_help_works() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "scripts.activate_category_profile", "--help"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--profile-id" in result.stdout


def test_derive_cli_dry_run_does_not_write_active_profile(monkeypatch) -> None:
    derive_cli = _load_script_module("derive_category_profile_cli", "scripts/derive_category_profile.py")

    SessionLocal = _session_factory()
    monkeypatch.setattr(derive_cli, "SessionLocal", SessionLocal)
    monkeypatch.setattr(sys, "argv", ["derive_category_profile", "--project", "1", "--category", "812", "--dry-run"])

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = derive_cli.main()

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["persisted_inactive"] is False
    with SessionLocal() as session:
        assert session.query(SeoCategoryProfile).count() == 0


def test_derive_cli_persist_creates_inactive_profile(monkeypatch) -> None:
    derive_cli = _load_script_module("derive_category_profile_cli_persist", "scripts/derive_category_profile.py")

    SessionLocal = _session_factory()
    monkeypatch.setattr(derive_cli, "SessionLocal", SessionLocal)
    monkeypatch.setattr(sys, "argv", ["derive_category_profile", "--project", "1", "--category", "812", "--persist"])

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = derive_cli.main()

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["dry_run"] is False
    assert payload["persisted_inactive"] is True
    with SessionLocal() as session:
        rows = session.query(SeoCategoryProfile).all()
        assert len(rows) == 1
        assert bool(rows[0].is_active) is False


def test_activate_cli_activates_passed_profile(monkeypatch) -> None:
    activate_cli = _load_script_module("activate_category_profile_cli", "scripts/activate_category_profile.py")

    SessionLocal = _session_factory()
    payload = json.loads(Path("config/seo/category_profiles/templates/812_skeleton_v1.json").read_text(encoding="utf-8"))
    payload["self_check"] = {"status": "passed", "checks": []}
    with SessionLocal.begin() as session:
        row = SeoCategoryProfile(
            project_id=1,
            category_id=812,
            version="v1.812.cli",
            is_active=False,
            payload=payload,
            source_note="cli-test",
        )
        session.add(row)
        session.flush()
        profile_id = int(row.id)

    monkeypatch.setattr(activate_cli, "SessionLocal", SessionLocal)
    monkeypatch.setattr(sys, "argv", ["activate_category_profile", "--profile-id", str(profile_id)])

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = activate_cli.main()

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["profile_id"] == profile_id
    assert payload["is_active"] is True
    with SessionLocal() as session:
        row = session.get(SeoCategoryProfile, profile_id)
        assert bool(row.is_active) is True
