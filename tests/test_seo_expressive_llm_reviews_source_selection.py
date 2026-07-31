from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence


def _ensure_reviews_tables(session) -> None:
    session.execute(text("ALTER TABLE products ADD COLUMN subject_name TEXT"))
    session.execute(
        text(
            """
            CREATE TABLE wb_feedback_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                nm_id INTEGER NOT NULL,
                product_valuation INTEGER,
                created_date DATETIME,
                raw TEXT
            )
            """
        )
    )
    session.commit()


def test_fetch_category_review_scope_filters_by_rating_and_category_and_combines_text():
    from app.services.seo.expressive_llm.reviews_source import fetch_category_review_scope

    session = make_session()
    try:
        _ensure_reviews_tables(session)

        # Category 821 products
        upsert_product_evidence(session, nm_id=10, subject_id=821, title="sku10")
        upsert_product_evidence(session, nm_id=11, subject_id=821, title="sku11")
        session.execute(
            text("UPDATE products SET subject_name='Тарелки' WHERE project_id=1 AND subject_id=821")
        )

        # Another category product
        upsert_product_evidence(session, nm_id=20, subject_id=999, title="other")
        session.execute(
            text("UPDATE products SET subject_name='Другое' WHERE project_id=1 AND subject_id=999")
        )

        ts = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)

        def ins(nm_id: int, rating: int | None, raw: dict | None) -> None:
            session.execute(
                text(
                    """
                    INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
                    VALUES (1, :nm_id, :rating, :ts, :raw)
                    """
                ),
                {"nm_id": nm_id, "rating": rating, "ts": ts, "raw": json.dumps(raw, ensure_ascii=False) if raw else None},
            )

        # Good review in category 821
        ins(10, 5, {"text": " Отлично ", "pros": " яркие ", "cons": ""})

        # Low rating (must be filtered out)
        ins(10, 3, {"text": "Плохо"})

        # Empty text (must be dropped)
        ins(11, 5, {"text": "  ", "pros": "", "cons": ""})

        # Another category (must not leak)
        ins(20, 5, {"text": "В другой категории"})

        session.commit()

        scope = fetch_category_review_scope(session, project_id=1, category_id=821, min_rating=4, limit=100)

        assert scope.project_id == 1
        assert scope.category_id == 821
        assert scope.category_name == "Тарелки"

        assert scope.fetched_rows == 2  # rating>=4 for nm_id=10 and nm_id=11
        assert scope.dropped_empty_text == 1

        assert [item.nm_id for item in scope.review_snippets] == [10]
        assert scope.nm_ids == [10]

        snippet = scope.review_snippets[0]
        assert snippet.rating == 5
        assert snippet.text == "Отлично\nяркие"
        assert snippet.created_at is not None
    finally:
        session.close()

