from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, Table, create_engine, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    SeoQueryBatch,
    SeoQueryClusterMembership,
    SeoQueryNormalized,
)
from app.services.seo.query_pipeline import (
    get_query_clusters,
    run_query_clustering,
    run_query_pruning_and_basic_annotation,
)


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _make_session() -> Session:
    _ensure_projects_stub()
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
                title TEXT
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


def _seed_scope_data(session: Session) -> None:
    ts_old = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
    ts_new = datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
    ts_processing = datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc)

    session.add_all(
        [
            SeoQueryBatch(
                id=1,
                project_id=1,
                category_id=821,
                source_type="csv",
                status="completed",
                created_at=ts_old,
                updated_at=ts_old,
            ),
            SeoQueryBatch(
                id=2,
                project_id=1,
                category_id=821,
                source_type="csv",
                status="completed",
                created_at=ts_new,
                updated_at=ts_new,
            ),
            SeoQueryBatch(
                id=3,
                project_id=1,
                category_id=821,
                source_type="csv",
                status="processing",
                created_at=ts_processing,
                updated_at=ts_processing,
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            SeoQueryNormalized(
                id=1,
                batch_id=2,
                project_id=1,
                category_id=821,
                normalized_query="платье красное",
                display_query="Платье красное",
                raw_row_count=2,
                frequency_total=Decimal("10"),
                created_at=ts_new,
                updated_at=ts_new,
            ),
            SeoQueryNormalized(
                id=2,
                batch_id=2,
                project_id=1,
                category_id=821,
                normalized_query="999",
                display_query="999",
                raw_row_count=1,
                frequency_total=Decimal("0"),
                created_at=ts_new,
                updated_at=ts_new,
            ),
            SeoQueryNormalized(
                id=3,
                batch_id=2,
                project_id=1,
                category_id=821,
                normalized_query="для дома",
                display_query="Для дома",
                raw_row_count=1,
                frequency_total=Decimal("0"),
                created_at=ts_new,
                updated_at=ts_new,
            ),
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
        {
            "day_1": date(2026, 4, 10),
            "ts_new": ts_new,
        },
    )
    session.commit()


def test_query_clustering_groups_variants_and_persists_memberships():
    session = _make_session()
    try:
        _seed_scope_data(session)
        pruning_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert pruning_result.diagnostics.keep_count == 6

        result = run_query_clustering(
            session,
            project_id=1,
            category_id=821,
            top_limit=3,
            samples_limit=3,
            persist=True,
        )

        assert result.diagnostics.total_input_queries == 6
        assert result.diagnostics.total_clusters_created == 4
        assert result.diagnostics.singleton_cluster_count == 3
        assert result.diagnostics.average_cluster_size == "1.5"
        assert result.diagnostics.counts_by_query_type == {
            "head": 2,
            "mid": 2,
            "tail": 2,
        }
        assert result.diagnostics.top_clusters[0].cluster_key.startswith("qcl:v1:")

        clusters = get_query_clusters(session, project_id=1, category_id=821)
        assert [cluster.cluster_label_candidate for cluster in clusters] == [
            "Платье красное",
            "платья",
            "Для дома",
            "юбка синяя",
        ]

        main_cluster = clusters[0]
        assert main_cluster.cluster_label_candidate == "Платье красное"
        assert main_cluster.top_query_text == "платье красное"
        assert main_cluster.query_count == 3
        assert main_cluster.head_query_count == 2
        assert main_cluster.mid_query_count == 1
        assert main_cluster.tail_query_count == 0
        assert [(member.normalized_query_text, member.membership_reason_code) for member in main_cluster.members] == [
            ("платье красное", "canonical_token_signature"),
            ("красное платье", "canonical_token_signature"),
            ("платье красное хлопок", "guarded_parent_signature"),
        ]

        memberships = session.scalars(
            select(SeoQueryClusterMembership).where(
                SeoQueryClusterMembership.project_id == 1,
                SeoQueryClusterMembership.category_id == 821,
            )
        ).all()
        assert len(memberships) == 6
        assert {item.normalized_query_text for item in memberships} == {
            "платье красное",
            "красное платье",
            "платье красное хлопок",
            "юбка синяя",
            "платья",
            "для дома",
        }
        assert all(item.annotation_id is not None for item in memberships)
    finally:
        session.close()


def test_query_clustering_is_stable_on_rerun_and_supports_bucket_filter():
    session = _make_session()
    try:
        _seed_scope_data(session)
        run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)

        first_result = run_query_clustering(session, project_id=1, category_id=821, persist=True)
        second_result = run_query_clustering(session, project_id=1, category_id=821, persist=True)

        assert [cluster.cluster_key for cluster in first_result.clusters] == [cluster.cluster_key for cluster in second_result.clusters]
        assert first_result.diagnostics.to_dict() == second_result.diagnostics.to_dict()

        persisted = get_query_clusters(session, project_id=1, category_id=821, bucket="head")
        assert len(persisted) == 1
        assert persisted[0].cluster_key.startswith("qcl:v1:")
        assert [member.normalized_query_text for member in persisted[0].members] == [
            "платье красное",
            "красное платье",
        ]

        mid_scope_result = run_query_clustering(
            session,
            project_id=1,
            category_id=821,
            bucket="mid",
            top_limit=5,
            samples_limit=5,
            persist=False,
        )
        assert mid_scope_result.diagnostics.total_input_queries == 2
        assert mid_scope_result.diagnostics.total_clusters_created == 2
        assert [cluster.cluster_label_candidate for cluster in mid_scope_result.clusters] == [
            "платье красное хлопок",
            "юбка синяя",
        ]
    finally:
        session.close()
