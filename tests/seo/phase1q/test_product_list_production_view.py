from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, MetaData, Table, Text, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import SeoCategoryMatchingReadiness, SeoMeaningAtom, SeoSkuMeaningAnnotation
from app.services.seo.products import list_seo_products


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
            Base.metadata.tables["seo_sku_meaning_annotations"],
            Base.metadata.tables["seo_meaning_atoms"],
            Base.metadata.tables["seo_category_matching_readiness"],
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
        Column("title", Text),
        Column("brand", Text),
        Column("subject_id", Integer),
        Column("subject_name", Text),
        Column("rating", Integer),
        Column("feedbacks", Integer),
        Column("pics", JSON),
        Column("updated_at", DateTime(timezone=True)),
    )
    Table(
        "stock_snapshots",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer, nullable=False),
        Column("nm_id", Integer, nullable=False),
        Column("quantity", Integer),
        Column("snapshot_at", DateTime(timezone=True)),
    )
    Table(
        "wb_feedback_snapshots",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer, nullable=False),
        Column("nm_id", Integer, nullable=False),
        Column("is_archived", Boolean),
    )
    metadata.create_all(engine)
    with SessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
        session.execute(text("CREATE VIEW v_wb_product_source AS SELECT *, NULL AS marketplace_product_id FROM products"))
    return SessionLocal


def test_product_list_returns_production_fields_and_stock_filter() -> None:
    SessionLocal = _session_factory()
    now = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, project_id, nm_id, vendor_code, title, brand, subject_id, subject_name, rating, feedbacks, pics, updated_at)
                VALUES
                    (1, 1, 1001, 'A-1001', 'Alpha product', 'Brand A', 73001, 'Alpha category', 5, 7, :pics, :updated_at),
                    (2, 1, 1002, 'A-1002', 'Beta product', 'Brand B', 73001, 'Alpha category', 4, 2, '[]', :updated_at)
                """
            ),
            {"pics": '[{"big":"https://cdn.example.test/1001.jpg"}]', "updated_at": now},
        )
        session.execute(
            text(
                """
                INSERT INTO stock_snapshots (id, project_id, nm_id, quantity, snapshot_at)
                VALUES
                    (1, 1, 1001, 3, :updated_at),
                    (2, 1, 1002, 0, :updated_at)
                """
            ),
            {"updated_at": now},
        )
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots (id, project_id, nm_id, is_archived)
                VALUES
                    (1, 1, 1001, 0),
                    (2, 1, 1001, 0),
                    (3, 1, 1001, 1),
                    (4, 1, 1002, 0)
                """
            )
        )

    with SessionLocal() as session:
        response = list_seo_products(session, project_id=1, category_id=73001, limit=10)
        in_stock_response = list_seo_products(session, project_id=1, category_id=73001, stock_status="in_stock", limit=10)

    assert response.total == 2
    first = next(item for item in response.items if item.nm_id == 1001)
    assert first.photo_url == "https://cdn.example.test/1001.jpg"
    assert first.title == "Alpha product"
    assert first.name == "Alpha product"
    assert first.category_id == 73001
    assert first.subject_id == 73001
    assert first.category_name == "Alpha category"
    assert first.subject_name == "Alpha category"
    assert first.vendor_code == "A-1001"
    assert first.article == "A-1001"
    assert first.review_count == 2
    assert first.stock_quantity == 3
    assert first.in_stock is True
    assert [item.nm_id for item in in_stock_response.items] == [1001]
