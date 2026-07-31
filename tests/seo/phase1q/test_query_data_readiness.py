from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, MetaData, Numeric, Table, Text, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    SeoCategoryMeaningAxes,
    SeoQueryAnnotation,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryNormalized,
)
from app.routers import seo_query_import as seo_query_import_router


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_query_batches"],
            Base.metadata.tables["seo_queries_normalized"],
            Base.metadata.tables["seo_query_annotations"],
            Base.metadata.tables["seo_query_clusters"],
            Base.metadata.tables["seo_query_cluster_memberships"],
            Base.metadata.tables["seo_category_meaning_axes"],
        ],
    )
    with SessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
        metadata = MetaData()
        Table(
            "products",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("project_id", Integer, nullable=False),
            Column("nm_id", Integer, nullable=False),
            Column("subject_id", Integer, nullable=False),
        )
        Table(
            "wb_feedback_snapshots",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("project_id", Integer, nullable=False),
            Column("nm_id", Integer, nullable=False),
            Column("product_valuation", Numeric(3, 1)),
            Column("created_date", DateTime(timezone=True)),
            Column("raw", JSON, nullable=False),
            Column("is_archived", Boolean),
        )
        metadata.create_all(engine)
    return SessionLocal


def _build_client(SessionLocal: sessionmaker) -> TestClient:
    app = FastAPI()
    app.include_router(seo_query_import_router.router)
    app.dependency_overrides[seo_query_import_router.allow_local_debug_read] = lambda: {
        "allowed": True,
        "project_id": 1,
    }
    seo_query_import_router.SessionLocal = SessionLocal
    return TestClient(app)


def _seed_query_data(SessionLocal: sessionmaker) -> int:
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    cluster_id = 0
    with SessionLocal.begin() as session:
        batch = SeoQueryBatch(
            project_id=1,
            category_id=73001,
            status="completed",
            row_count=3,
            normalized_row_count=2,
            deduplicated_row_count=2,
            original_filename="queries.csv",
            created_at=now,
            updated_at=now,
        )
        session.add(batch)
        session.flush()
        normalized = SeoQueryNormalized(
            project_id=1,
            category_id=73001,
            batch_id=int(batch.id),
            normalized_query="alpha compact",
            display_query="Alpha compact",
            raw_row_count=2,
            frequency_total=Decimal("42"),
            normalization_version="v1_minimal",
            sample_source_payload={"raw_query": "Alpha compact"},
            created_at=now,
            updated_at=now,
        )
        annotation = SeoQueryAnnotation(
            project_id=1,
            category_id=73001,
            normalized_query_text="alpha compact",
            intent_type="commercial",
            query_type="head",
            created_at=now,
            updated_at=now,
        )
        cluster = SeoQueryCluster(
            project_id=1,
            category_id=73001,
            cluster_key="cluster-alpha",
            label="Alpha cluster",
            top_query_text="alpha compact",
            status="ready",
            query_count=1,
            head_query_count=1,
            created_at=now,
            updated_at=now,
        )
        axes = SeoCategoryMeaningAxes(
            project_id=1,
            category_id=73001,
            schema_version="category_meaning_axes_v0",
            source="deterministic",
            status="ready",
            evidence_hash="axes-hash",
            axes_payload={
                "confidence": {"reviews": 0.75, "deterministic": 0.5},
                "evidence_refs": ["query_clusters", "products", "reviews"],
                "expressive_axes": ["cozy", "giftable"],
                "audience_axes": ["student"],
                "occasion_axes": ["birthday"],
                "use_case_axes": ["travel"],
                "product_type_axes": ["alpha"],
                "attribute_axes": ["compact"],
                "constraint_axes": ["material:steel"],
                "negative_constraint_axes": ["fragile"],
            },
            canonical_text="alpha axes",
            prompt_version="category_meaning_axes_v0",
            input_hash="axes-input",
            created_at=now,
            updated_at=now,
        )
        session.add_all([normalized, annotation, cluster, axes])
        session.flush()
        session.add(
            SeoQueryClusterMembership(
                project_id=1,
                category_id=73001,
                cluster_id=int(cluster.id),
                annotation_id=int(annotation.id),
                normalized_query_text="alpha compact",
                query_type="head",
                ranking_value_used=Decimal("42"),
                membership_reason_code="test",
                created_at=now,
                updated_at=now,
            )
        )
        cluster_id = int(cluster.id)
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products (id, project_id, nm_id, subject_id)
                VALUES
                    (1, 1, 1001, 73001),
                    (2, 1, 1002, 73001),
                    (3, 1, 2001, 99999)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots
                    (id, project_id, nm_id, product_valuation, created_date, raw, is_archived)
                VALUES
                    (1, 1, 1001, 5, :created_date, :raw_text, 0),
                    (2, 1, 1001, 3, :created_date, :raw_pros, 0),
                    (3, 1, 1002, 4, :created_date, :raw_empty, 0),
                    (4, 1, 2001, 5, :created_date, :raw_other, 0)
                """
            ),
            {
                "created_date": now,
                "raw_text": '{"text":"Nice","userName":"must not be returned"}',
                "raw_pros": '{"pros":"Useful"}',
                "raw_empty": '{"text":""}',
                "raw_other": '{"text":"Other category"}',
            },
        )
    return cluster_id


def test_query_data_status_reports_readiness() -> None:
    SessionLocal = _session_factory()
    _seed_query_data(SessionLocal)
    client = _build_client(SessionLocal)

    response = client.get("/api/v1/projects/1/seo/categories/73001/query-data/status")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["query_count"] == 3
    assert payload["normalized_query_count"] == 1
    assert payload["cluster_count"] == 1
    assert payload["latest_batch"]["status"] == "completed"
    assert payload["expressive_prior"]["ready"] is True
    assert payload["expressive_prior"]["llm_model"] is None
    assert payload["expressive_prior"]["confidence"] == {"reviews": 0.75, "deterministic": 0.5}
    assert payload["expressive_prior"]["evidence_refs"] == ["query_clusters", "products", "reviews"]
    assert payload["expressive_prior"]["expressive_axes"] == ["cozy", "giftable"]
    assert payload["expressive_prior"]["negative_constraint_axes"] == ["fragile"]
    assert payload["review_archive"] == {
        "source_table": "wb_feedback_snapshots",
        "category_join": "products.subject_id",
        "total_review_rows": 3,
        "text_review_rows": 2,
        "sku_with_reviews": 2,
        "sku_with_text_reviews": 1,
        "rating_positive_rows": 2,
    }
    assert payload["readiness"]["ready"] is True


def test_cluster_list_and_detail_are_read_only_browser_contract() -> None:
    SessionLocal = _session_factory()
    cluster_id = _seed_query_data(SessionLocal)
    client = _build_client(SessionLocal)

    list_response = client.get("/api/v1/projects/1/seo/categories/73001/clusters")
    detail_response = client.get(f"/api/v1/projects/1/seo/categories/73001/clusters/{cluster_id}")

    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["items"][0]["cluster_key"] == "cluster-alpha"
    assert list_response.json()["items"][0]["top_frequency"] == "42.0000"
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()
    assert detail_payload["cluster"]["cluster_id"] == cluster_id
    assert detail_payload["queries"][0]["normalized_query_text"] == "alpha compact"
    assert detail_payload["queries"][0]["frequency_total"] == "42.0000"
