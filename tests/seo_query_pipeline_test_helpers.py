from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, Table, create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoQueryBatch, SeoQueryCluster, SeoQueryClusterMembership, SeoQueryNormalized
from app.services.seo.query_pipeline import run_query_clustering, run_query_pruning_and_basic_annotation


def ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def make_session() -> Session:
    ensure_projects_stub()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
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
    session = Session(engine)
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
    session.execute(text("CREATE VIEW v_wb_product_source AS SELECT *, NULL AS marketplace_product_id FROM products"))
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
    return session


def seed_scope_data(session: Session) -> None:
    ts_old = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
    ts_new = datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
    ts_processing = datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc)

    session.add_all(
        [
            SeoQueryBatch(id=1, project_id=1, category_id=821, source_type="csv", status="completed", created_at=ts_old, updated_at=ts_old),
            SeoQueryBatch(id=2, project_id=1, category_id=821, source_type="csv", status="completed", created_at=ts_new, updated_at=ts_new),
            SeoQueryBatch(id=3, project_id=1, category_id=821, source_type="csv", status="processing", created_at=ts_processing, updated_at=ts_processing),
        ]
    )
    session.flush()

    session.add_all(
        [
            SeoQueryNormalized(id=1, batch_id=2, project_id=1, category_id=821, normalized_query="платье красное", display_query="Платье красное", raw_row_count=2, frequency_total=Decimal("10"), created_at=ts_new, updated_at=ts_new),
            SeoQueryNormalized(id=2, batch_id=2, project_id=1, category_id=821, normalized_query="999", display_query="999", raw_row_count=1, frequency_total=Decimal("0"), created_at=ts_new, updated_at=ts_new),
            SeoQueryNormalized(id=3, batch_id=2, project_id=1, category_id=821, normalized_query="для дома", display_query="Для дома", raw_row_count=1, frequency_total=Decimal("0"), created_at=ts_new, updated_at=ts_new),
        ]
    )

    session.execute(
        text(
            """
            INSERT INTO products (project_id, nm_id, subject_id, title) VALUES
                (1, 10, 821, 'dress base'),
                (1, 11, 821, 'dress reverse'),
                (1, 12, 821, 'dress cotton'),
                (1, 13, 821, 'skirt'),
                (1, 14, 821, 'plural'),
                (1, 15, 821, 'noise'),
                (1, 16, 821, 'unknown'),
                (1, 17, 821, 'info')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO wb_search_query_terms
                (id, project_id, nm_id, search_text, frequency, is_ad, created_at, updated_at)
            VALUES
                (1, 1, 10, 'Платье красное', 10, 0, :ts_new, :ts_new),
                (2, 1, 11, 'красное платье', 8, 0, :ts_new, :ts_new),
                (3, 1, 12, 'платье красное хлопок', 5, 0, :ts_new, :ts_new),
                (4, 1, 14, 'платья', 4, 0, :ts_new, :ts_new),
                (5, 1, 15, 'wildberries', 1, 0, :ts_new, :ts_new),
                (6, 1, 15, '!!!', 0, 0, :ts_new, :ts_new),
                (7, 1, 16, 'Для дома', 0, 0, :ts_new, :ts_new)
            """
        ),
        {"ts_new": ts_new},
    )
    session.execute(
        text(
            """
            INSERT INTO wb_search_query_daily
                (id, project_id, nm_id, search_text, stat_date, orders, avg_position, created_at, updated_at)
            VALUES
                (10, 1, 13, 'юбка синяя', :day_1, 6, 4.0, :ts_new, :ts_new),
                (11, 1, 17, 'как выбрать платье', :day_1, 5, 4.5, :ts_new, :ts_new)
            """
        ),
        {"day_1": date(2026, 4, 10), "ts_new": ts_new},
    )
    session.commit()


def add_term_query(session: Session, *, nm_id: int, search_text: str, frequency: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO products (project_id, nm_id, subject_id, title)
            VALUES (1, :nm_id, 821, :title)
            """
        ),
        {"nm_id": nm_id, "title": search_text},
    )
    session.execute(
        text(
            """
            INSERT INTO wb_search_query_terms (project_id, nm_id, search_text, frequency, is_ad, created_at, updated_at)
            VALUES (1, :nm_id, :search_text, :frequency, 0, :ts, :ts)
            """
        ),
        {"nm_id": nm_id, "search_text": search_text, "frequency": frequency, "ts": datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)},
    )
    session.flush()


def upsert_product_evidence(
    session: Session,
    *,
    nm_id: int,
    title: str | None,
    description: str | None = None,
    characteristics: list[dict] | None = None,
    sizes: list | None = None,
    colors: list | None = None,
    dimensions: dict | None = None,
    subject_id: int = 821,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO products (
                project_id,
                nm_id,
                subject_id,
                title,
                description,
                characteristics,
                sizes,
                colors,
                dimensions,
                raw,
                updated_at
            )
            VALUES (
                1,
                :nm_id,
                :subject_id,
                :title,
                :description,
                :characteristics,
                :sizes,
                :colors,
                :dimensions,
                :raw,
                :updated_at
            )
            """
        ),
        {
            "nm_id": nm_id,
            "subject_id": subject_id,
            "title": title,
            "description": description,
            "characteristics": json.dumps(characteristics, ensure_ascii=False) if characteristics is not None else None,
            "sizes": json.dumps(sizes, ensure_ascii=False) if sizes is not None else None,
            "colors": json.dumps(colors, ensure_ascii=False) if colors is not None else None,
            "dimensions": json.dumps(dimensions, ensure_ascii=False) if dimensions is not None else None,
            "raw": None,
            "updated_at": datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc),
        },
    )
    session.flush()


def run_base_pipeline(session: Session) -> None:
    run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
    run_query_clustering(session, project_id=1, category_id=821, persist=True)


def cluster_id_for_query(session: Session, query_text: str) -> int:
    membership = session.scalars(
        select(SeoQueryClusterMembership).where(SeoQueryClusterMembership.normalized_query_text == query_text)
    ).one()
    return int(membership.cluster_id)


def move_query_to_cluster(session: Session, *, query_text: str, target_cluster_id: int, query_type: str) -> None:
    membership = session.scalars(
        select(SeoQueryClusterMembership).where(SeoQueryClusterMembership.normalized_query_text == query_text)
    ).one()
    membership.cluster_id = target_cluster_id
    membership.query_type = query_type
    session.flush()


def delete_empty_clusters(session: Session) -> None:
    clusters = session.scalars(select(SeoQueryCluster)).all()
    empty_cluster_ids: list[int] = []
    for cluster in clusters:
        member_count = int(
            session.execute(
                select(text("COUNT(*)")).select_from(SeoQueryClusterMembership).where(
                    SeoQueryClusterMembership.cluster_id == cluster.id
                )
            ).scalar_one()
        )
        if member_count == 0:
            empty_cluster_ids.append(int(cluster.id))
    if empty_cluster_ids:
        session.execute(delete(SeoQueryCluster).where(SeoQueryCluster.id.in_(empty_cluster_ids)))
        session.flush()


def refresh_cluster_stats(session: Session, cluster_id: int) -> None:
    memberships = session.scalars(
        select(SeoQueryClusterMembership).where(SeoQueryClusterMembership.cluster_id == cluster_id)
    ).all()
    cluster = session.get(SeoQueryCluster, cluster_id)
    assert cluster is not None
    cluster.query_count = len(memberships)
    cluster.head_query_count = sum(1 for membership in memberships if membership.query_type == "head")
    cluster.mid_query_count = sum(1 for membership in memberships if membership.query_type == "mid")
    cluster.tail_query_count = sum(1 for membership in memberships if membership.query_type == "tail")
    session.flush()
