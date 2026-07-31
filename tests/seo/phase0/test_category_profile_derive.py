from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.seo.category_profile_derive import derive_category_profile
from app.services.seo.category_profile_snapshot import build_category_profile_snapshot_path


def test_derive_dry_run_builds_profile_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.services.seo.category_profile_derive._latest_ready_axes",
        lambda *args, **kwargs: SimpleNamespace(
            evidence_hash="axes-evidence-1",
            axes_payload={"product_type_axes": ["кружка", "термокружка", "стакан"]},
            source="deterministic",
        ),
    )
    monkeypatch.setattr("app.services.seo.category_profile_derive._count_queries_for_category", lambda *args, **kwargs: 31921)
    monkeypatch.setattr(
        "app.services.seo.category_profile_derive._compute_subject_match_share",
        lambda *args, **kwargs: 0.984,
    )

    result = derive_category_profile(
        project_id=1,
        category_id=812,
        session=None,  # type: ignore[arg-type]
        dry_run=True,
        out_path=tmp_path,
    )

    assert result.profile_payload["schema_version"] == "category_profile_v1"
    assert result.self_check.status == "passed"
    assert result.profile_id is None
    assert result.snapshot_path == build_category_profile_snapshot_path(
        project_id=1,
        category_id=812,
        version=result.profile_version,
        root_dir=tmp_path,
    )


def test_derive_snapshot_path_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.services.seo.category_profile_derive._latest_ready_axes",
        lambda *args, **kwargs: SimpleNamespace(
            evidence_hash="axes-evidence-1",
            axes_payload={"product_type_axes": ["кружка"]},
            source="deterministic",
        ),
    )
    monkeypatch.setattr("app.services.seo.category_profile_derive._count_queries_for_category", lambda *args, **kwargs: 10)
    monkeypatch.setattr("app.services.seo.category_profile_derive._compute_subject_match_share", lambda *args, **kwargs: 0.9)

    first = derive_category_profile(project_id=1, category_id=812, session=None, dry_run=True, out_path=tmp_path)  # type: ignore[arg-type]
    second = derive_category_profile(project_id=1, category_id=812, session=None, dry_run=True, out_path=tmp_path)  # type: ignore[arg-type]

    assert first.profile_version == second.profile_version
    assert first.snapshot_path == second.snapshot_path


def test_derive_activation_remains_separate_from_persist() -> None:
    with pytest.raises(NotImplementedError, match="Activation"):
        derive_category_profile(project_id=1, category_id=99999, session=None, activate=True)  # type: ignore[arg-type]


def test_cli_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.derive_category_profile", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--project" in result.stdout
    assert "--category" in result.stdout
    assert "--dry-run" in result.stdout
