from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, Table, create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    SeoQueryAnnotation,
    SeoQueryAnnotationVersion,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryNormalized,
)
from app.services.seo.query_pipeline import (
    run_query_clustering,
    run_query_hybrid_annotation,
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
                (10, 1, 13, 'юбка синяя', '2026-04-10', 6, 4.0, :ts_new, :ts_new),
                (11, 1, 17, 'как выбрать платье', '2026-04-10', 5, 4.5, :ts_new, :ts_new)
            """
        ),
        {"ts_new": ts_new},
    )
    session.commit()


def _run_base_pipeline(session: Session) -> None:
    run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
    run_query_clustering(session, project_id=1, category_id=821, persist=True)


def _cluster_id_for_query(session: Session, query_text: str) -> int:
    membership = session.scalars(
        select(SeoQueryClusterMembership).where(SeoQueryClusterMembership.normalized_query_text == query_text)
    ).one()
    return int(membership.cluster_id)


def _move_query_to_cluster(session: Session, *, query_text: str, target_cluster_id: int, query_type: str) -> None:
    membership = session.scalars(
        select(SeoQueryClusterMembership).where(SeoQueryClusterMembership.normalized_query_text == query_text)
    ).one()
    membership.cluster_id = target_cluster_id
    membership.query_type = query_type
    session.flush()


def _delete_empty_clusters(session: Session) -> None:
    clusters = session.scalars(select(SeoQueryCluster)).all()
    empty_cluster_ids = []
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


def _refresh_cluster_stats(session: Session, cluster_id: int) -> None:
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


def _add_term_query(session: Session, *, nm_id: int, search_text: str, frequency: int) -> None:
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
        {
            "nm_id": nm_id,
            "search_text": search_text,
            "frequency": frequency,
            "ts": datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc),
        },
    )
    session.flush()


def test_hybrid_annotation_selects_head_anchor_persists_projection_and_is_idempotent():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _add_term_query(session, nm_id=18, search_text="весенняя куртка", frequency=20)
        _add_term_query(session, nm_id=19, search_text="куртка весенняя", frequency=20)

        first_result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        rows = {row.normalized_query_text: row for row in first_result.annotated_queries}

        assert rows["весенняя куртка"].provenance == "individual"
        assert rows["весенняя куртка"].inheritance_reason_code == "individual_anchor"
        assert rows["куртка весенняя"].provenance == "cluster"
        assert rows["куртка весенняя"].inheritance_reason_code == "compatible_plural_variant"
        assert rows["платье красное хлопок"].provenance == "cluster"
        assert rows["платье красное хлопок"].source_anchor_query == "платье красное"
        assert rows["для дома"].provenance == "fallback"
        assert first_result.diagnostics.anchor_count >= 1
        assert first_result.diagnostics.inherited_head_member_count >= 1
        assert first_result.diagnostics.rejected_head_member_count >= 0
        assert first_result.diagnostics.individual_count >= 1
        assert first_result.diagnostics.cluster_derived_count >= 1
        assert first_result.diagnostics.rejected_count >= 1
        assert first_result.diagnostics.fallback_count >= 1

        persisted_anchor = session.scalars(
            select(SeoQueryAnnotation).where(SeoQueryAnnotation.normalized_query_text == "весенняя куртка")
        ).one()
        assert persisted_anchor.meta["hybrid_annotation"]["provenance"] == "individual"

        latest_version = session.scalars(
            select(SeoQueryAnnotationVersion)
            .where(SeoQueryAnnotationVersion.annotation_id == persisted_anchor.id)
            .order_by(SeoQueryAnnotationVersion.version_number.desc())
        ).first()
        assert latest_version is not None
        assert latest_version.annotation_payload["hybrid_annotation"]["provenance"] == "individual"

        second_result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        assert second_result.annotations_upserted == 0
        assert second_result.versions_created == 0
    finally:
        session.close()


def test_hybrid_annotation_skips_large_no_head_cluster_anchor_fallback():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _run_base_pipeline(session)

        target_cluster_id = _cluster_id_for_query(session, "для дома")
        for query_text, query_type in (
            ("платье красное хлопок", "mid"),
            ("юбка синяя", "mid"),
            ("платья", "mid"),
        ):
            _move_query_to_cluster(session, query_text=query_text, target_cluster_id=target_cluster_id, query_type=query_type)

        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, target_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["для дома"].provenance == "rejected"
        assert rows["для дома"].inheritance_reason_code == "no_anchor"
        assert rows["платье красное хлопок"].inheritance_reason_code == "no_anchor"
        assert rows["юбка синяя"].inheritance_reason_code == "no_anchor"
        assert rows["платья"].inheritance_reason_code == "no_anchor"
        assert any(item.issue_reason == "no_anchor" for item in result.diagnostics.clusters_without_anchor)
    finally:
        session.close()


def test_hybrid_annotation_rejects_single_token_generic_member():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _run_base_pipeline(session)

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        _move_query_to_cluster(session, query_text="платья", target_cluster_id=main_cluster_id, query_type="mid")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["платья"].provenance == "rejected"
        assert rows["платья"].inheritance_reason_code == "single_token_generic"
    finally:
        session.close()


def test_hybrid_annotation_rejects_head_member_when_strong_core_differs():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _add_term_query(session, nm_id=18, search_text="платье красное", frequency=20)
        _add_term_query(session, nm_id=19, search_text="красное платье", frequency=19)
        _add_term_query(session, nm_id=20, search_text="платье синее", frequency=18)
        _run_base_pipeline(session)

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        _move_query_to_cluster(session, query_text="платье синее", target_cluster_id=main_cluster_id, query_type="head")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["платье синее"].provenance == "rejected"
        assert rows["платье синее"].inheritance_reason_code == "head_strong_core_mismatch"
    finally:
        session.close()


def test_hybrid_annotation_rejects_intent_conflict_member():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _run_base_pipeline(session)

        session.execute(
            text(
                """
                UPDATE seo_query_annotations
                SET intent_type = 'category'
                WHERE normalized_query_text = 'для дома'
                """
            )
        )
        session.flush()

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        _move_query_to_cluster(session, query_text="для дома", target_cluster_id=main_cluster_id, query_type="tail")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["для дома"].provenance == "rejected"
        assert rows["для дома"].inheritance_reason_code == "intent_conflict"
    finally:
        session.close()


def test_hybrid_annotation_rejects_lexical_core_mismatch_member():
    session = _make_session()
    try:
        _seed_scope_data(session)
        _add_term_query(session, nm_id=18, search_text="платье синее", frequency=3)
        _run_base_pipeline(session)

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        _move_query_to_cluster(session, query_text="платье синее", target_cluster_id=main_cluster_id, query_type="mid")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["платье синее"].provenance == "rejected"
        assert rows["платье синее"].inheritance_reason_code == "lexical_core_mismatch"
    finally:
        session.close()


def test_hybrid_annotation_rejects_cluster_when_too_large():
    session = _make_session()
    try:
        _seed_scope_data(session)
        for nm_id, search_text in (
            (18, "платье синее"),
            (19, "платье белое"),
            (20, "платье длинное"),
            (21, "платье короткое"),
            (22, "платье зеленое"),
            (23, "платье летнее"),
            (24, "платье зимнее"),
            (25, "платье вечернее"),
        ):
            _add_term_query(session, nm_id=nm_id, search_text=search_text, frequency=3)
        _run_base_pipeline(session)

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        for query_text in (
            "платье синее",
            "платье белое",
            "платье длинное",
            "платье короткое",
            "платье зеленое",
            "платье летнее",
            "платье зимнее",
            "платье вечернее",
        ):
            _move_query_to_cluster(session, query_text=query_text, target_cluster_id=main_cluster_id, query_type="mid")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["платье белое"].provenance == "rejected"
        assert rows["платье белое"].inheritance_reason_code == "cluster_too_large"
    finally:
        session.close()


def test_hybrid_annotation_allows_clean_medium_cluster_relaxation():
    session = _make_session()
    try:
        _seed_scope_data(session)
        for nm_id, search_text in (
            (18, "платье красное длинное"),
            (19, "платье красное вечернее"),
            (20, "платье красное летнее"),
            (21, "платье красное хлопок"),
        ):
            _add_term_query(session, nm_id=nm_id, search_text=search_text, frequency=4)
        _run_base_pipeline(session)

        main_cluster_id = _cluster_id_for_query(session, "платье красное")
        for query_text in (
            "платье красное длинное",
            "платье красное вечернее",
            "платье красное летнее",
            "платье красное хлопок",
        ):
            _move_query_to_cluster(session, query_text=query_text, target_cluster_id=main_cluster_id, query_type="mid")
        _delete_empty_clusters(session)
        _refresh_cluster_stats(session, main_cluster_id)

        result = run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=False)
        rows = {row.normalized_query_text: row for row in result.annotated_queries}

        assert rows["платье красное вечернее"].provenance == "cluster"
        assert rows["платье красное вечернее"].inheritance_reason_code == "compatible_attribute_extension"
    finally:
        session.close()
