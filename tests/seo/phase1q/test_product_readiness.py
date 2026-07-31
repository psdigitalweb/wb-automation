from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, Numeric, Table, Text, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    SeoCategoryMatchingReadiness,
    SeoCategoryMeaningAxes,
    SeoMeaningAtom,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryNormalized,
    SeoSkuMeaningAnnotation,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)
from app.services.seo.products import get_product_readiness
from app.services.seo import products as product_service


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
            Base.metadata.tables["seo_query_clusters"],
            Base.metadata.tables["seo_category_matching_readiness"],
            Base.metadata.tables["seo_category_meaning_axes"],
            Base.metadata.tables["seo_sku_meaning_annotations"],
            Base.metadata.tables["seo_sku_meaning_audit_events"],
            Base.metadata.tables["seo_meaning_atoms"],
            Base.metadata.tables["seo_sku_query_sets"],
            Base.metadata.tables["seo_sku_query_set_items"],
        ],
    )
    metadata = MetaData()
    Table(
        "products",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer, nullable=False),
        Column("nm_id", Integer, nullable=False),
        Column("vendor_code", Text),
        Column("brand", Text),
        Column("subject_id", Integer),
        Column("subject_name", Text),
        Column("title", Text),
        Column("description", Text),
        Column("price_u", Integer),
        Column("sale_price_u", Integer),
        Column("rating", Numeric),
        Column("feedbacks", Integer),
        Column("sizes", JSON),
        Column("colors", JSON),
        Column("pics", JSON),
        Column("dimensions", JSON),
        Column("characteristics", JSON),
        Column("updated_at", DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    with SessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    return SessionLocal


def test_product_readiness_blocks_when_ai_vision_is_missing() -> None:
    SessionLocal = _session_factory()
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products (id, project_id, nm_id, subject_id, subject_name, title, updated_at)
                VALUES (1, 1, 1001, 73001, 'Alpha category', 'Alpha product', :updated_at)
                """
            ),
            {"updated_at": now},
        )
        batch = SeoQueryBatch(
            project_id=1,
            category_id=73001,
            status="completed",
            row_count=3,
            normalized_row_count=2,
            deduplicated_row_count=2,
            created_at=now,
            updated_at=now,
        )
        session.add(batch)
        session.flush()
        session.add_all(
            [
                SeoQueryNormalized(
                    project_id=1,
                    category_id=73001,
                    batch_id=int(batch.id),
                    normalized_query="alpha compact",
                    display_query="Alpha compact",
                    raw_row_count=1,
                    frequency_total=Decimal("10"),
                    sample_source_payload={},
                    created_at=now,
                    updated_at=now,
                ),
                SeoQueryCluster(
                    project_id=1,
                    category_id=73001,
                    cluster_key="cluster-alpha",
                    status="ready",
                    query_count=1,
                    created_at=now,
                    updated_at=now,
                ),
                SeoCategoryMeaningAxes(
                    project_id=1,
                    category_id=73001,
                    status="ready",
                    evidence_hash="axes-hash",
                    axes_payload={"expressive_axes": ["cozy"]},
                    canonical_text="alpha axes",
                    input_hash="axes-input",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )

    with SessionLocal() as session:
        readiness = get_product_readiness(session, project_id=1, nm_id=1001)

    assert readiness.product_card_exists is True
    assert readiness.category_id == 73001
    assert readiness.normalized_query_count == 1
    assert readiness.cluster_count == 1
    assert readiness.expressive_prior_ready is True
    assert readiness.ai_vision.ready is False
    assert readiness.can_select_queries is False
    assert readiness.blocking_reasons == ["AI vision по товару не выполнен или не готов."]


def test_product_readiness_allows_selection_and_summarizes_query_set() -> None:
    SessionLocal = _session_factory()
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products (id, project_id, nm_id, subject_id, subject_name, title, updated_at)
                VALUES (1, 1, 1001, 73001, 'Alpha category', 'Alpha product', :updated_at)
                """
            ),
            {"updated_at": now},
        )
        batch = SeoQueryBatch(
            project_id=1,
            category_id=73001,
            status="completed",
            row_count=2,
            normalized_row_count=2,
            deduplicated_row_count=2,
            created_at=now,
            updated_at=now,
        )
        session.add(batch)
        session.flush()
        annotation = SeoSkuMeaningAnnotation(
            project_id=1,
            category_id=73001,
            nm_id=1001,
            status="ready",
            meaning_payload={},
            evidence_hash="evidence-hash",
            created_at=now,
            updated_at=now,
        )
        query_set = SeoSkuQuerySet(
            project_id=1,
            category_id=73001,
            nm_id=1001,
            status="draft",
            approval_state="approved",
            trust_state="verified",
            created_at=now,
            updated_at=now,
        )
        session.add_all(
            [
                SeoQueryNormalized(
                    project_id=1,
                    category_id=73001,
                    batch_id=int(batch.id),
                    normalized_query="alpha compact",
                    display_query="Alpha compact",
                    raw_row_count=1,
                    frequency_total=Decimal("10"),
                    sample_source_payload={},
                    created_at=now,
                    updated_at=now,
                ),
                SeoQueryCluster(
                    project_id=1,
                    category_id=73001,
                    cluster_key="cluster-alpha",
                    status="ready",
                    query_count=1,
                    created_at=now,
                    updated_at=now,
                ),
                SeoCategoryMeaningAxes(
                    project_id=1,
                    category_id=73001,
                    status="ready",
                    evidence_hash="axes-hash",
                    axes_payload={"expressive_axes": ["cozy"]},
                    canonical_text="alpha axes",
                    input_hash="axes-input",
                    created_at=now,
                    updated_at=now,
                ),
                SeoCategoryMatchingReadiness(
                    project_id=1,
                    category_id=73001,
                    status="ready_for_matching",
                    queries_count=2,
                    clusters_count=1,
                    category_axes_status="ready",
                    created_at=now,
                    updated_at=now,
                ),
                annotation,
                query_set,
            ]
        )
        session.flush()
        session.add_all(
            [
                SeoMeaningAtom(
                    project_id=1,
                    category_id=73001,
                    entity_type="sku_vision",
                    entity_id=int(annotation.id),
                    nm_id=1001,
                    input_hash="vision-input",
                    atoms_payload={"facts": [{"type": "visual", "field": "color", "value": "blue"}]},
                    canonical_summary="blue",
                    status="ready",
                    created_at=now,
                    updated_at=now,
                ),
                SeoSkuQuerySetItem(
                    query_set_id=int(query_set.id),
                    normalized_query_text="alpha compact",
                    display_query="Alpha compact",
                    bucket="primary",
                    score=Decimal("0.9000"),
                    selection_state="pinned",
                ),
            ]
        )

    with SessionLocal() as session:
        readiness = get_product_readiness(session, project_id=1, nm_id=1001)

    assert readiness.can_select_queries is True
    assert readiness.blocking_reasons == []
    assert readiness.ai_vision.label == "AI vision готов"
    assert readiness.ai_vision.items == ["blue"]
    assert readiness.existing_query_set is not None
    assert readiness.existing_query_set.approved is True
    assert readiness.existing_query_set.selected_items == 1


def test_product_analysis_propagates_selected_image_urls(monkeypatch) -> None:
    SessionLocal = _session_factory()
    captured: dict[str, object] = {}
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    selected_urls = ["https://cdn.example.test/selected-1.jpg", "https://cdn.example.test/selected-2.jpg"]
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, project_id, nm_id, subject_id, subject_name, title, pics, characteristics, updated_at)
                VALUES
                    (1, 1, 1001, 73001, 'Alpha category', 'Alpha product', :pics, '[]', :updated_at)
                """
            ),
            {
                "pics": '["https://cdn.example.test/original-1.jpg","https://cdn.example.test/original-2.jpg"]',
                "updated_at": now,
            },
        )

    def fail_draft(*args, **kwargs):
        raise RuntimeError("draft disabled in focused test")

    def capture_atoms(*args, **kwargs):
        captured["evidence_payload"] = kwargs["evidence_payload"]
        captured["force_refresh"] = kwargs["force_refresh"]
        captured["include_vision"] = kwargs["include_vision"]
        return {"vision_status": "ready"}

    monkeypatch.setattr(product_service, "generate_sku_meaning_draft", fail_draft)
    monkeypatch.setattr(product_service, "ensure_sku_atoms", capture_atoms)

    with SessionLocal.begin() as session:
        product_service.run_product_analysis(
            session,
            project_id=1,
            category_id=73001,
            nm_id=1001,
            force_refresh=True,
            include_vision=True,
            selected_image_urls=selected_urls,
        )

    evidence_payload = captured["evidence_payload"]
    assert isinstance(evidence_payload, dict)
    assert evidence_payload["product"]["pics"] == selected_urls
    assert captured["force_refresh"] is True
    assert captured["include_vision"] is True
