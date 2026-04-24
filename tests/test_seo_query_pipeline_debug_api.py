from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import deps
from app.routers import seo_query_pipeline_debug as seo_query_pipeline_debug_router
from app.services.seo.query_pipeline import run_query_hybrid_annotation

from seo_query_pipeline_test_helpers import add_term_query, ensure_projects_stub, seed_scope_data
from app.db import Base


def _build_client() -> tuple[TestClient, sessionmaker]:
    ensure_projects_stub()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_query_batches"],
            Base.metadata.tables["seo_queries_normalized"],
            Base.metadata.tables["seo_query_annotations"],
            Base.metadata.tables["seo_query_annotation_versions"],
            Base.metadata.tables["seo_query_clusters"],
            Base.metadata.tables["seo_query_cluster_memberships"],
        ],
    )
    with TestingSessionLocal() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
        session.execute(
            text(
                """
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    nm_id INTEGER NOT NULL,
                    subject_id INTEGER,
                    title TEXT,
                    description TEXT,
                    characteristics TEXT,
                    sizes TEXT,
                    colors TEXT,
                    dimensions TEXT,
                    raw TEXT,
                    updated_at DATETIME
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE wb_search_query_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    nm_id INTEGER NOT NULL,
                    search_text TEXT NOT NULL,
                    frequency INTEGER,
                    is_ad BOOLEAN,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE wb_search_query_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    nm_id INTEGER NOT NULL,
                    search_text TEXT NOT NULL,
                    stat_date DATE NOT NULL,
                    orders INTEGER,
                    avg_position NUMERIC,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        session.commit()
        seed_scope_data(session)
        add_term_query(session, nm_id=18, search_text="тарелка для микроволновки", frequency=30)
        add_term_query(session, nm_id=19, search_text="тарелки для микроволновки", frequency=18)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        session.commit()

    app = FastAPI()
    app.include_router(seo_query_pipeline_debug_router.router)
    override = lambda: {"project_id": 1, "user_id": 1, "role": "owner", "local_debug": True}
    app.dependency_overrides[deps.allow_local_debug_read] = override
    app.dependency_overrides[seo_query_pipeline_debug_router.allow_local_debug_read] = override
    seo_query_pipeline_debug_router.SessionLocal = TestingSessionLocal
    return TestClient(app), TestingSessionLocal


def test_profiles_tab_returns_profile_payload():
    client, _session_local = _build_client()

    response = client.get(
        "/api/v1/projects/1/seo/query-pipeline/debug",
        params={"category_id": 821, "tab": "profiles", "page": 1, "page_size": 25},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["profiles_diagnostics"]["total_profiles_built"] > 0
    assert payload["profiles_pagination"]["total_count"] > 0
    assert len(payload["profiles"]) > 0

    microwave_profile = next(
        profile
        for profile in payload["profiles"]
        if "микроволнов" in (profile.get("profile_label_candidate") or "")
        or "микроволнов" in (profile.get("source_anchor_query") or "")
    )
    assert microwave_profile["profile_strength"] in {"strong", "medium", "weak", "empty"}
    assert any(marker["normalized_value"] == "для микроволновки" for marker in microwave_profile["use_case_markers"])
    assert any(
        decision["slot"] == "use_case" and decision["selected"] and decision["normalized_value"] == "для микроволновки"
        for decision in microwave_profile["marker_decisions"]
    )


def test_scoring_prep_tab_returns_preparation_payload():
    client, session_local = _build_client()
    with session_local() as session:
        session.execute(
            text(
                """
                UPDATE products
                SET
                    description = :description,
                    characteristics = :characteristics,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = 1 AND nm_id = 18
                """
            ),
            {
                "description": "Керамическая тарелка для микроволновки и сервировки стола.",
                "characteristics": '[{"name":"Материал посуды","value":["керамика"]},{"name":"Особенности посуды","value":["использование в СВЧ"]}]',
            },
        )
        session.commit()

    response = client.get(
        "/api/v1/projects/1/seo/query-pipeline/debug",
        params={"category_id": 821, "tab": "scoring_prep", "nm_id": 18, "page": 1, "page_size": 25},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scoring_prep_diagnostics"]["total_cluster_comparisons"] > 0
    assert payload["scoring_prep_pagination"]["total_count"] > 0
    assert len(payload["scoring_preparations"]) > 0

    microwave_prep = next(
        item
        for item in payload["scoring_preparations"]
        if "микроволнов" in (item.get("profile_label_candidate") or "")
    )
    assert any(
        marker["normalized_value"] == "для микроволновки"
        for marker in microwave_prep["use_case_match"]["matched_markers"]
    )
    assert microwave_prep["product_type_match"]["status"] in {"matched", "not_matched"}
    assert microwave_prep["sku_evidence_summary"]["attributes_present"] is True


def test_scoring_prep_tab_requires_nm_id():
    client, _session_local = _build_client()

    response = client.get(
        "/api/v1/projects/1/seo/query-pipeline/debug",
        params={"category_id": 821, "tab": "scoring_prep", "page": 1, "page_size": 25},
    )

    assert response.status_code == 400, response.text
    assert "nm_id" in response.json()["detail"]


def test_scoring_tab_returns_actual_scores_payload():
    client, session_local = _build_client()
    with session_local() as session:
        session.execute(
            text(
                """
                UPDATE products
                SET
                    description = :description,
                    characteristics = :characteristics,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = 1 AND nm_id = 18
                """
            ),
            {
                "description": "Керамическая тарелка для микроволновки и сервировки стола.",
                "characteristics": '[{"name":"Материал посуды","value":["керамика"]},{"name":"Особенности посуды","value":["использование в СВЧ"]}]',
            },
        )
        session.commit()

    response = client.get(
        "/api/v1/projects/1/seo/query-pipeline/debug",
        params={"category_id": 821, "tab": "scoring", "nm_id": 18, "page": 1, "page_size": 25},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["actual_scoring_diagnostics"]["total_clusters_scored"] > 0
    assert (
        payload["actual_scoring_diagnostics"]["positive_score_count"]
        + payload["actual_scoring_diagnostics"]["neutral_score_count"]
        + payload["actual_scoring_diagnostics"]["negative_score_count"]
        == payload["actual_scoring_diagnostics"]["total_clusters_scored"]
    )
    assert payload["actual_scoring_pagination"]["total_count"] > 0
    assert len(payload["actual_scores"]) > 0

    microwave_score = next(
        item
        for item in payload["actual_scores"]
        if "микроволнов" in (item.get("profile_label_candidate") or "")
    )
    assert microwave_score["final_score"] != 0
    assert "product_type" in microwave_score["final_reason"]
    assert "modifiers" in microwave_score
    assert "ranking_eligible" in microwave_score
    assert "generation_eligible" in microwave_score
    assert "generation_guardrail_reason" in microwave_score


def test_scoring_tab_requires_nm_id():
    client, _session_local = _build_client()

    response = client.get(
        "/api/v1/projects/1/seo/query-pipeline/debug",
        params={"category_id": 821, "tab": "scoring", "page": 1, "page_size": 25},
    )

    assert response.status_code == 400, response.text
    assert "nm_id" in response.json()["detail"]
