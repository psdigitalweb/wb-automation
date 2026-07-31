from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SeoCategoryProfile, SeoCategoryProfileDeriveRun
from app.routers import seo_category_profile as seo_category_profile_router
from app.schemas.seo_category_profile import CategoryProfileListResponse
from app.services.seo.category_profile_admin import (
    CategoryProfileActivationError,
    activate_category_profile,
    list_derive_runs,
)


TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _payload(*, self_check_status: str = "passed", schema_version: str = "category_profile_v1") -> dict[str, object]:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["schema_version"] = schema_version
    payload["self_check"] = {"status": self_check_status, "checks": []}
    return payload


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


def _create_profile(
    session: Session,
    *,
    profile_id: int | None = None,
    project_id: int = 1,
    category_id: int = 812,
    version: str,
    is_active: bool,
    self_check_status: str = "passed",
    schema_version: str = "category_profile_v1",
) -> SeoCategoryProfile:
    row = SeoCategoryProfile(
        id=profile_id,
        project_id=project_id,
        category_id=category_id,
        version=version,
        is_active=is_active,
        payload=_payload(self_check_status=self_check_status, schema_version=schema_version),
        source_note=f"test:{version}",
    )
    session.add(row)
    session.flush()
    return row


def _build_client(SessionLocal: sessionmaker) -> TestClient:
    app = FastAPI()
    app.include_router(seo_category_profile_router.router)
    app.dependency_overrides[seo_category_profile_router.allow_local_debug_read] = lambda: {
        "allowed": True,
        "project_id": 1,
    }
    seo_category_profile_router.SessionLocal = SessionLocal
    return TestClient(app)


def test_failed_self_check_cannot_be_activated() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        row = _create_profile(
            session,
            version="v1.812.failed",
            is_active=False,
            self_check_status="failed",
        )
        profile_id = int(row.id)

    with SessionLocal() as session:
        try:
            activate_category_profile(session, profile_id)
        except CategoryProfileActivationError as exc:
            assert "self_check.status" in str(exc)
        else:
            raise AssertionError("failed profile must not activate")


def test_passed_profile_activation_deactivates_previous_only_for_same_scope() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        active_old = _create_profile(session, version="v1.812.old", is_active=True)
        inactive_new = _create_profile(session, version="v1.812.new", is_active=False)
        other_category = _create_profile(session, category_id=999, version="v1.999.keep", is_active=True)
        new_id = int(inactive_new.id)
        old_id = int(active_old.id)
        other_id = int(other_category.id)

    with SessionLocal.begin() as session:
        activated = activate_category_profile(session, new_id)
        assert int(activated.id) == new_id
        assert bool(activated.is_active) is True

    with SessionLocal() as session:
        old_row = session.get(SeoCategoryProfile, old_id)
        new_row = session.get(SeoCategoryProfile, new_id)
        other_row = session.get(SeoCategoryProfile, other_id)
        assert bool(old_row.is_active) is False
        assert bool(new_row.is_active) is True
        assert bool(other_row.is_active) is True


def test_activate_previous_version_behaves_like_rollback() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        previous = _create_profile(session, version="v1.812.previous", is_active=False)
        current = _create_profile(session, version="v1.812.current", is_active=True)
        previous_id = int(previous.id)
        current_id = int(current.id)

    with SessionLocal.begin() as session:
        activate_category_profile(session, previous_id)

    with SessionLocal() as session:
        previous_row = session.get(SeoCategoryProfile, previous_id)
        current_row = session.get(SeoCategoryProfile, current_id)
        assert bool(previous_row.is_active) is True
        assert bool(current_row.is_active) is False


def test_unknown_schema_version_cannot_be_activated() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        row = _create_profile(
            session,
            version="v1.812.bad-schema",
            is_active=False,
            schema_version="category_profile_v999",
        )
        profile_id = int(row.id)

    with SessionLocal() as session:
        try:
            activate_category_profile(session, profile_id)
        except CategoryProfileActivationError as exc:
            assert "unsupported schema_version" in str(exc)
        else:
            raise AssertionError("unknown schema must block activation")


def test_list_derive_runs_returns_rows() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        session.add(
            SeoCategoryProfileDeriveRun(
                project_id=1,
                category_id=812,
                run_id="run-1",
                status="succeeded",
                method="skeleton_v0",
                profile_version="v1.812.skeleton",
                self_check_json={"status": "passed"},
            )
        )

    with SessionLocal() as session:
        rows = list_derive_runs(session, project_id=1, category_id=812)
        assert len(rows) == 1
        assert str(rows[0].run_id) == "run-1"


def test_list_profiles_endpoint_returns_profiles() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        _create_profile(session, version="v1.812.api", is_active=False)
    client = _build_client(SessionLocal)

    response = client.get("/api/v1/projects/1/seo/category-profiles", params={"category_id": 812})

    assert response.status_code == 200, response.text
    payload = CategoryProfileListResponse.model_validate(response.json())
    assert len(payload.items) == 1
    assert payload.items[0].version == "v1.812.api"


def test_get_profile_endpoint_returns_payload() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        row = _create_profile(session, version="v1.812.detail", is_active=False)
        profile_id = int(row.id)
    client = _build_client(SessionLocal)

    response = client.get(f"/api/v1/projects/1/seo/category-profiles/{profile_id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == profile_id
    assert payload["payload"]["schema_version"] == "category_profile_v1"


def test_activate_endpoint_rejects_failed_profile() -> None:
    SessionLocal = _session_factory()
    with SessionLocal.begin() as session:
        row = _create_profile(
            session,
            version="v1.812.failed-api",
            is_active=False,
            self_check_status="failed",
        )
        profile_id = int(row.id)
    client = _build_client(SessionLocal)

    response = client.post(f"/api/v1/projects/1/seo/category-profiles/{profile_id}/activate")

    assert response.status_code == 409, response.text
    assert "self_check.status" in response.json()["detail"]


def test_derive_dry_run_endpoint_does_not_activate_or_persist_profile() -> None:
    SessionLocal = _session_factory()
    client = _build_client(SessionLocal)

    response = client.post(
        "/api/v1/projects/1/seo/category-profiles/derive",
        json={"category_id": 812, "dry_run": True, "activate": False},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["self_check"]["status"] == "passed"
    assert payload["is_active"] is False
    with SessionLocal() as session:
        count = session.query(SeoCategoryProfile).count()
        assert count == 0
