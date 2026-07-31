from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, Table, create_engine, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoQueryBatch, SeoQueryNormalized
from app.services.seo.query_pipeline import assemble_unified_query_dataset


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

    batch_old = SeoQueryBatch(
        id=1,
        project_id=1,
        category_id=821,
        source_type="csv",
        status="completed",
        created_at=ts_old,
        updated_at=ts_old,
    )
    batch_latest = SeoQueryBatch(
        id=2,
        project_id=1,
        category_id=821,
        source_type="csv",
        status="completed",
        created_at=ts_new,
        updated_at=ts_new,
    )
    batch_processing = SeoQueryBatch(
        id=3,
        project_id=1,
        category_id=821,
        source_type="csv",
        status="processing",
        created_at=ts_processing,
        updated_at=ts_processing,
    )
    session.add_all([batch_old, batch_latest, batch_processing])
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
                batch_id=1,
                project_id=1,
                category_id=821,
                normalized_query="платье красное",
                display_query="Платье красное old",
                raw_row_count=1,
                frequency_total=Decimal("30"),
                created_at=ts_old,
                updated_at=ts_old,
            ),
            SeoQueryNormalized(
                id=3,
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
                id=4,
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
                id=5,
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
                (1, 15, 821, 'noise')
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
                (6, 1, 15, '!!!', 0, 0, :ts_new, :ts_new)
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


def test_unified_dataset_assembles_scope_and_traceability():
    session = _make_session()
    try:
        _seed_scope_data(session)
        result = assemble_unified_query_dataset(session, project_id=1, category_id=821)

        assert result.latest_csv_batch_id == 2
        assert result.diagnostics.latest_csv_batch_id == 2
        assert result.diagnostics.total_canonical_queries == 8
        assert result.diagnostics.total_source_linked_queries == 13
        assert result.diagnostics.queries_by_source_presence == {
            "csv_only": 2,
            "wb_terms_only": 3,
            "wb_daily_only": 2,
            "csv_wb_terms": 0,
            "csv_wb_daily": 0,
            "wb_terms_wb_daily": 0,
            "csv_wb_terms_wb_daily": 1,
        }
        assert result.diagnostics.source_inventory[0].record_count == 4
        assert result.diagnostics.source_inventory[1].record_count == 5
        assert result.diagnostics.source_inventory[2].record_count == 4

        rows = {row.normalized_query_text: row for row in result.canonical_queries}
        assert "старый запрос" in rows
        assert "processing query" not in rows
        assert rows["старый запрос"].frequency_total == Decimal("100")

        merged = rows["платье красное"]
        assert merged.display_query == "Платье красное"
        assert merged.source_count == 3
        assert merged.source_presence == {
            "has_csv_normalized": True,
            "has_wb_terms": True,
            "has_wb_daily": True,
        }
        assert merged.frequency_total == Decimal("50")
        assert merged.orders_total == Decimal("3")
        assert merged.ranking_value_used == Decimal("50")
        assert merged.avg_position_best == Decimal("2.5")
        assert merged.is_duplicate_candidate is True
        assert {ref.source_type for ref in merged.source_record_refs} == {"csv_normalized", "wb_terms", "wb_daily"}
        csv_ref = next(ref for ref in merged.source_record_refs if ref.source_type == "csv_normalized")
        assert csv_ref.batch_ids == [1, 2]
        assert csv_ref.raw_value_summary["frequency_total"] == "40"

        wb_terms_ref = next(ref for ref in merged.source_record_refs if ref.source_type == "wb_terms")
        wb_daily_ref = next(ref for ref in merged.source_record_refs if ref.source_type == "wb_daily")
        assert wb_terms_ref.nm_ids == [10, 11]
        assert wb_terms_ref.record_count == 2
        assert wb_daily_ref.nm_ids == [10, 11]
        assert wb_daily_ref.date_range == {"from": "2026-04-10", "to": "2026-04-11"}

        informational = rows["как выбрать платье"]
        assert informational.is_informational_candidate is True
        assert informational.is_navigation_candidate is False
        assert informational.bucket_basis == "orders_total"
        assert informational.ranking_value_used == Decimal("5")

        navigation = rows["wildberries"]
        assert navigation.is_navigation_candidate is True
        assert navigation.is_garbage_candidate is True

        empty_row = rows[""]
        assert empty_row.is_empty_candidate is True
        assert empty_row.is_garbage_candidate is True
        assert empty_row.head_tail_bucket == "tail"
        assert empty_row.bucket_basis == "none"

        csv_only = rows["999"]
        assert csv_only.source_count == 1
        assert csv_only.source_presence["has_csv_normalized"] is True
        assert csv_only.bucket_basis == "none"
    finally:
        session.close()


def test_unified_dataset_head_mid_tail_and_diagnostics_serialization():
    session = _make_session()
    try:
        _seed_scope_data(session)
        result = assemble_unified_query_dataset(session, project_id=1, category_id=821, top_limit=3, samples_limit=10)

        rows = {row.normalized_query_text: row for row in result.canonical_queries}
        assert rows["старый запрос"].head_tail_bucket == "head"
        assert rows["платье красное"].head_tail_bucket == "head"
        assert rows["как выбрать платье"].head_tail_bucket == "mid"
        assert rows["юбка синяя"].head_tail_bucket == "mid"
        assert rows["ozon"].head_tail_bucket == "mid"
        assert rows["wildberries"].head_tail_bucket == "tail"
        assert rows[""].head_tail_bucket == "tail"
        assert rows["999"].head_tail_bucket == "tail"

        assert result.diagnostics.queries_by_head_tail_bucket == {
            "head": 2,
            "mid": 3,
            "tail": 3,
        }
        assert result.diagnostics.top_queries[0].normalized_query_text == "старый запрос"
        assert result.diagnostics.partial_coverage_samples[0].source_count == 1
        assert any(sample.normalized_query_text in {"wildberries", "ozon"} for sample in result.diagnostics.flagged_samples)
        assert any(sample.normalized_query_text == "платье красное" for sample in result.diagnostics.conflict_samples)

        serialized = result.diagnostics.to_dict()
        assert serialized["top_queries"][0]["ranking_value_used"] == "100"
        assert serialized["queries_by_head_tail_bucket"]["tail"] == 3
        assert serialized["source_inventory"][0]["latest_timestamp"] == "2026-04-02T08:00:00+00:00"
    finally:
        session.close()
