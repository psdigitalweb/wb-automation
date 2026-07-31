from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Column, Integer, Table, create_engine, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoQueryAnnotation, SeoQueryAnnotationVersion, SeoQueryBatch, SeoQueryNormalized
from app.services.seo.query_pipeline.pruning import (
    _apply_annotation_rules,
    _apply_pruning_rules,
    get_clean_query_set,
    get_pruning_slice,
    run_query_pruning_and_basic_annotation,
)
from app.services.seo.query_pipeline.unified_dataset import CanonicalQueryRow


_MIGRATION_PATH = Path(
    r"D:\Work\EcomCore\alembic\versions\20260414_evolve_seo_query_annotations_for_canonical_pruning.py"
)
_MIGRATION_SPEC = importlib.util.spec_from_file_location("seo_pruning_hardening_migration", _MIGRATION_PATH)
assert _MIGRATION_SPEC and _MIGRATION_SPEC.loader
_MIGRATION_MODULE = importlib.util.module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(_MIGRATION_MODULE)


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
                batch_id=1,
                project_id=1,
                category_id=821,
                normalized_query="старый запрос",
                display_query="Старый запрос",
                raw_row_count=1,
                frequency_total=Decimal("100"),
                created_at=ts_old,
                updated_at=ts_old,
            ),
            SeoQueryNormalized(
                id=2,
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
                id=3,
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
                id=4,
                batch_id=3,
                project_id=1,
                category_id=821,
                normalized_query="processing query",
                display_query="Processing query",
                raw_row_count=1,
                frequency_total=Decimal("999"),
                created_at=ts_processing,
                updated_at=ts_processing,
            ),
            SeoQueryNormalized(
                id=5,
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
                (1, 10, 821, 'dress 10'),
                (1, 11, 821, 'dress 11'),
                (1, 12, 999, 'filtered out'),
                (1, 13, 821, 'info'),
                (1, 14, 821, 'skirt'),
                (1, 15, 821, 'noise'),
                (1, 16, 821, 'unknown')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO wb_search_query_terms
                (id, project_id, nm_id, search_text, frequency, is_ad, created_at, updated_at)
            VALUES
                (1, 1, 10, 'Платье красное', 7, 0, :ts_new, :ts_new),
                (2, 1, 11, 'платье, красное', 3, 0, :ts_new, :ts_new),
                (3, 1, 12, 'платье красное', 99, 0, :ts_new, :ts_new),
                (4, 1, 13, 'wildberries', 1, 0, :ts_new, :ts_new),
                (5, 1, 14, 'ozon', 1, 0, :ts_new, :ts_new),
                (6, 1, 15, '!!!', 0, 0, :ts_new, :ts_new),
                (7, 1, 16, 'Для дома', 0, 0, :ts_new, :ts_new),
                (8, 1, 14, 'платья', 2, 0, :ts_new, :ts_new)
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
                (10, 1, 10, 'Платье красное', :day_1, 2, 3.5, :ts_new, :ts_new),
                (11, 1, 11, 'Платье красное', :day_2, 1, 2.5, :ts_new, :ts_new),
                (12, 1, 13, 'как выбрать платье', :day_1, 5, 4.0, :ts_new, :ts_new),
                (13, 1, 14, 'юбка синяя', :day_1, 4, 5.0, :ts_new, :ts_new),
                (14, 1, 12, 'как выбрать платье', :day_1, 10, 1.0, :ts_new, :ts_new)
            """
        ),
        {
            "day_1": date(2026, 4, 10),
            "day_2": date(2026, 4, 11),
            "ts_new": ts_new,
        },
    )
    session.commit()


def _canonical_row(**overrides: object) -> CanonicalQueryRow:
    payload = {
        "project_id": 1,
        "category_id": 821,
        "normalized_query_text": "тест запрос",
        "display_query": "Тест запрос",
        "source_presence": {"has_csv_normalized": False, "has_wb_terms": True, "has_wb_daily": False},
        "source_count": 1,
        "source_record_refs": [],
        "frequency_total": Decimal("0"),
        "orders_total": Decimal("0"),
        "ranking_value_used": Decimal("0"),
        "bucket_basis": "none",
        "head_tail_bucket": "tail",
        "first_seen_at": None,
        "last_seen_at": None,
        "is_empty_candidate": False,
        "is_duplicate_candidate": False,
        "is_garbage_candidate": False,
        "is_informational_candidate": False,
        "is_navigation_candidate": False,
        "preparation_flag_reasons": [],
    }
    payload.update(overrides)
    return CanonicalQueryRow(**payload)


def _make_legacy_annotation_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE seo_queries_normalized (
                    id INTEGER PRIMARY KEY,
                    normalized_query TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE seo_query_annotations (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    normalized_query_id INTEGER,
                    normalized_query_text TEXT,
                    annotation_status TEXT NOT NULL DEFAULT 'pending',
                    latest_version_number INTEGER NOT NULL DEFAULT 0,
                    meta TEXT
                )
                """
            )
        )
    return engine


def test_query_pruning_persists_annotations_and_retrieves_clean_set():
    session = _make_session()
    try:
        _seed_scope_data(session)

        result = run_query_pruning_and_basic_annotation(
            session,
            project_id=1,
            category_id=821,
            top_limit=3,
            samples_limit=10,
            persist=True,
        )

        rows = {row.normalized_query_text: row for row in result.annotated_queries}
        assert result.diagnostics.total_canonical_queries_processed == 10
        assert result.diagnostics.keep_count == 5
        assert result.diagnostics.drop_count == 4
        assert result.diagnostics.review_count == 1
        assert result.annotations_upserted == 10
        assert result.versions_created == 10
        assert result.diagnostics.annotations_upserted == 10
        assert result.diagnostics.versions_created == 10
        assert result.diagnostics.stale_persisted_annotation_count == 0
        assert result.diagnostics.removed_since_last_run_count == 0
        assert result.diagnostics.stale_persisted_annotation_samples == []

        assert rows["платье красное"].pruning_status == "keep"
        assert rows["платье красное"].pruning_reason_code == "pipeline_candidate"
        assert rows["платье красное"].intent_type == "product"
        assert rows["платье красное"].query_type == "head"
        assert rows["платье красное"].normalized_query_id == 2
        assert rows["как выбрать платье"].pruning_status == "review"
        assert rows["как выбрать платье"].pruning_reason_code == "informational_query"
        assert rows["как выбрать платье"].intent_type == "informational"
        assert rows["как выбрать платье"].normalized_query_id is None
        assert rows["wildberries"].pruning_reason_code == "navigation_marketplace"
        assert rows["wildberries"].intent_type == "garbage"
        assert rows[""].pruning_reason_code == "empty_malformed"
        assert rows["999"].pruning_reason_code == "garbage_noise"
        assert rows["платья"].pruning_status == "keep"
        assert rows["платья"].intent_type == "category"
        assert rows["платья"].query_type == "mid"
        assert rows["для дома"].pruning_status == "keep"
        assert rows["для дома"].intent_type == "unknown"
        assert rows["для дома"].query_type == "tail"

        assert result.diagnostics.counts_by_pruning_reason_code == {
            "empty_malformed": 1,
            "navigation_marketplace": 2,
            "garbage_noise": 1,
            "informational_query": 1,
            "single_token_lexical_noise": 0,
            "weak_coverage_no_demand": 0,
            "pipeline_candidate": 5,
        }
        assert result.diagnostics.counts_by_intent_type == {
            "product": 3,
            "category": 1,
            "informational": 1,
            "garbage": 4,
            "unknown": 1,
        }
        assert result.diagnostics.kept_counts_by_query_type == {
            "head": 2,
            "mid": 2,
            "tail": 1,
        }
        assert result.diagnostics.top_kept_queries[0].normalized_query_text == "старый запрос"
        assert any(sample.normalized_query_text == "для дома" for sample in result.diagnostics.sample_unknown_queries)

        persisted_annotations = session.scalars(select(SeoQueryAnnotation)).all()
        persisted_versions = session.scalars(select(SeoQueryAnnotationVersion)).all()
        assert len(persisted_annotations) == 10
        assert len(persisted_versions) == 10

        informational_annotation = next(item for item in persisted_annotations if item.normalized_query_text == "как выбрать платье")
        assert informational_annotation.normalized_query_id is None
        assert informational_annotation.pruning_status == "review"
        informational_version = next(item for item in persisted_versions if item.annotation_id == informational_annotation.id)
        assert informational_version.annotation_payload["normalized_query_text"] == "как выбрать платье"
        assert informational_version.annotation_payload["pruning_status"] == "review"

        clean_rows = get_clean_query_set(session, project_id=1, category_id=821)
        assert {row.normalized_query_text for row in clean_rows} == {"старый запрос", "платье красное", "юбка синяя", "платья", "для дома"}
        assert {row.normalized_query_text for row in get_clean_query_set(session, project_id=1, category_id=821, bucket="mid")} == {
            "юбка синяя",
            "платья",
        }
        assert {row.normalized_query_text for row in get_pruning_slice(session, project_id=1, category_id=821, pruning_status="drop")} == {
            "",
            "999",
            "ozon",
            "wildberries",
        }
        assert {row.normalized_query_text for row in get_pruning_slice(session, project_id=1, category_id=821, pruning_status="review")} == {
            "как выбрать платье"
        }
    finally:
        session.close()


def test_query_pruning_rule_precedence_and_material_change_versioning():
    nav_row = _canonical_row(normalized_query_text="wildberries", is_navigation_candidate=True, is_garbage_candidate=True)
    assert _apply_pruning_rules(nav_row) == ("drop", "navigation_marketplace", False)
    assert _apply_annotation_rules(nav_row, pruning_reason_code="navigation_marketplace") == (
        "garbage",
        "garbage_navigation_marketplace",
    )

    info_row = _canonical_row(
        normalized_query_text="как выбрать платье",
        display_query="Как выбрать платье",
        ranking_value_used=Decimal("5"),
        orders_total=Decimal("5"),
        bucket_basis="orders_total",
        head_tail_bucket="head",
        is_informational_candidate=True,
    )
    assert _apply_pruning_rules(info_row) == ("review", "informational_query", False)
    assert _apply_annotation_rules(info_row, pruning_reason_code="informational_query") == (
        "informational",
        "informational_marker",
    )

    weak_row = _canonical_row(normalized_query_text="аксессуар комплект")
    assert _apply_pruning_rules(weak_row) == ("review", "weak_coverage_no_demand", False)

    session = _make_session()
    try:
        _seed_scope_data(session)

        first_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert first_result.versions_created == 10

        second_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert second_result.annotations_upserted == 0
        assert second_result.versions_created == 0

        session.execute(
            text("UPDATE wb_search_query_terms SET updated_at = :ts WHERE id = 7"),
            {"ts": datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc)},
        )
        session.flush()

        ignored_change_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert ignored_change_result.annotations_upserted == 0
        assert ignored_change_result.versions_created == 0

        session.execute(text("UPDATE wb_search_query_terms SET frequency = 6 WHERE id = 7"))
        session.flush()

        third_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert third_result.annotations_upserted == 2
        assert third_result.versions_created == 2

        changed_row = next(row for row in third_result.annotated_queries if row.normalized_query_text == "для дома")
        assert changed_row.intent_type == "product"
        assert changed_row.annotation_version_number == 2
        assert changed_row.query_type == "mid"
    finally:
        session.close()


def test_query_pruning_disappeared_queries_become_stale_but_not_returned():
    session = _make_session()
    try:
        _seed_scope_data(session)
        initial_result = run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)
        assert initial_result.diagnostics.stale_persisted_annotation_count == 0

        session.execute(text("DELETE FROM wb_search_query_terms WHERE id = 8"))
        session.flush()

        rerun_result = run_query_pruning_and_basic_annotation(
            session,
            project_id=1,
            category_id=821,
            persist=True,
            top_limit=5,
            samples_limit=2,
        )
        assert rerun_result.diagnostics.stale_persisted_annotation_count == 1
        assert rerun_result.diagnostics.removed_since_last_run_count == 1
        assert [sample.normalized_query_text for sample in rerun_result.diagnostics.stale_persisted_annotation_samples] == ["платья"]

        clean_rows = get_clean_query_set(session, project_id=1, category_id=821)
        assert "платья" not in {row.normalized_query_text for row in clean_rows}

        drop_rows = get_pruning_slice(session, project_id=1, category_id=821, pruning_status="drop")
        review_rows = get_pruning_slice(session, project_id=1, category_id=821, pruning_status="review")
        keep_rows = get_clean_query_set(session, project_id=1, category_id=821)
        visible_rows = {row.normalized_query_text for row in drop_rows + review_rows + keep_rows}
        assert "платья" not in visible_rows

        persisted = session.scalars(
            select(SeoQueryAnnotation).where(SeoQueryAnnotation.normalized_query_text == "платья")
        ).one()
        assert persisted.annotation_status == "completed"
    finally:
        session.close()


def test_query_pruning_diagnostics_limits_and_deterministic_ordering():
    session = _make_session()
    try:
        _seed_scope_data(session)
        run_query_pruning_and_basic_annotation(session, project_id=1, category_id=821, persist=True)

        session.execute(text("DELETE FROM wb_search_query_terms WHERE id = 8"))
        session.flush()

        result = run_query_pruning_and_basic_annotation(
            session,
            project_id=1,
            category_id=821,
            top_limit=2,
            samples_limit=1,
            persist=True,
        )
        assert [item.normalized_query_text for item in result.diagnostics.top_kept_queries] == [
            "старый запрос",
            "платье красное",
        ]
        assert len(result.diagnostics.sample_dropped_queries) == 1
        assert len(result.diagnostics.sample_review_queries) == 1
        assert len(result.diagnostics.sample_unknown_queries) == 1
        assert len(result.diagnostics.stale_persisted_annotation_samples) == 1
        assert result.diagnostics.sample_dropped_queries[0].normalized_query_text == "ozon"
        assert result.diagnostics.sample_review_queries[0].normalized_query_text == "как выбрать платье"
        assert result.diagnostics.sample_unknown_queries[0].normalized_query_text == "для дома"
        assert result.diagnostics.stale_persisted_annotation_samples[0].normalized_query_text == "платья"
    finally:
        session.close()


def test_migration_helpers_backfill_and_fail_fast_conflict_examples():
    engine = _make_legacy_annotation_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO seo_queries_normalized (id, normalized_query) VALUES
                        (1, 'платье'),
                        (2, 'платье')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO seo_query_annotations
                        (id, project_id, category_id, normalized_query_id, normalized_query_text, annotation_status, latest_version_number, meta)
                    VALUES
                        (1, 10, 821, 1, NULL, 'completed', 1, '{}'),
                        (2, 10, 821, 2, NULL, 'completed', 1, '{}'),
                        (3, 10, 821, 999, NULL, 'completed', 1, '{}')
                    """
                )
            )
            _MIGRATION_MODULE._backfill_normalized_query_text(conn)

            rows = conn.execute(
                text("SELECT id, normalized_query_text FROM seo_query_annotations ORDER BY id ASC")
            ).fetchall()
            assert rows == [(1, "платье"), (2, "платье"), (3, "legacy:3")]

            conflicts = _MIGRATION_MODULE._find_conflicting_future_canonical_keys(conn)
            assert conflicts == [
                {
                    "project_id": 10,
                    "category_id": 821,
                    "future_key": "платье",
                    "row_count": 2,
                }
            ]

            try:
                _MIGRATION_MODULE._raise_on_conflicting_future_keys(conn)
            except RuntimeError as exc:
                message = str(exc)
                assert "future canonical keys would collide" in message
                assert "project_id=10" in message
                assert "category_id=821" in message
                assert "'платье'" in message
            else:
                raise AssertionError("Expected fail-fast migration conflict error")
    finally:
        engine.dispose()
