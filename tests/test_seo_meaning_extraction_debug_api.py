from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app import deps
from app.db import Base
from app.models import SeoQueryCluster
from app.routers import seo_meaning_extraction_debug as seo_meaning_extraction_debug_router
from app.services.seo.query_pipeline import run_query_hybrid_annotation

from seo_query_pipeline_test_helpers import add_term_query, ensure_projects_stub, seed_scope_data, upsert_product_evidence


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

    app = FastAPI()
    app.include_router(seo_meaning_extraction_debug_router.router)
    override = lambda: {"project_id": 1, "user_id": 1, "role": "owner", "local_debug": True}
    app.dependency_overrides[deps.allow_local_debug_read] = override
    app.dependency_overrides[seo_meaning_extraction_debug_router.allow_local_debug_read] = override
    seo_meaning_extraction_debug_router.SessionLocal = TestingSessionLocal

    return TestClient(app), TestingSessionLocal


def test_meaning_extraction_debug_endpoint_returns_three_meaning_objects_and_flags():
    client, session_local = _build_client()

    with session_local() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))

        # Match existing query pipeline test setup: products + WB query terms/daily tables.
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

        # Ensure category meaning prior exists (>= 3 SKU with repeating vibe token).
        for nm_id in (9001, 9002, 9003):
            upsert_product_evidence(
                session,
                nm_id=nm_id,
                subject_id=821,
                title="Тарелка premium",
                description="aesthetic",
                characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
            )

        # Target SKU for product projection.
        upsert_product_evidence(
            session,
            nm_id=18,
            subject_id=821,
            title="Тарелка для супа",
            description="Керамическая тарелка",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        # Seed queries so clustering/hybrid/profile extraction has something to work with.
        add_term_query(session, nm_id=18, search_text="тарелка для супа", frequency=30)
        add_term_query(session, nm_id=18, search_text="тарелка premium", frequency=10)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        session.commit()

        cluster_key = session.scalars(
            select(SeoQueryCluster.cluster_key).where(SeoQueryCluster.project_id == 1, SeoQueryCluster.category_id == 821)
        ).first()
        assert cluster_key is not None

    response = client.get(
        "/api/v1/projects/1/seo/meaning-extraction/debug",
        params={"category_id": 821, "nm_id": 18, "cluster_key": cluster_key},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert "category_meaning" in payload
    assert "product_projection" in payload
    assert "query_meaning" in payload
    assert "product_projection_flags" in payload
    assert "query_meaning_flags" in payload

    assert payload["category_meaning"]["project_id"] == 1
    assert payload["category_meaning"]["category_id"] == 821
    assert payload["product_projection"]["nm_id"] == 18
    assert payload["query_meaning"]["cluster_key"] == cluster_key

    # Minimal flags are present.
    assert "weak_expressive_signal" in payload["product_projection_flags"]
    assert payload["query_meaning_flags"]["expressive_vibes_are_mvp_proxy"] is True


def test_meaning_extraction_debug_requires_cluster_key_and_nm_id():
    client, _session_local = _build_client()

    response = client.get(
        "/api/v1/projects/1/seo/meaning-extraction/debug",
        params={"category_id": 821},
    )
    assert response.status_code == 400, response.text
