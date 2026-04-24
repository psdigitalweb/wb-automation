from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import settings
from app.services.seo.expressive_llm.category_input_builder import build_category_expressive_input
from app.services.seo.expressive_llm.reviews_source import fetch_category_review_scope
from app.services.seo.expressive_llm.storage import CategoryExpressiveCacheKey, CategoryExpressiveStore
from app.services.seo.meaning_extraction import build_category_meaning
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


def _fetch_titles(session, *, project_id: int, nm_ids: list[int]) -> list[str]:
    if not nm_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT p.title
            FROM products p
            WHERE p.project_id = :project_id
              AND p.nm_id IN :nm_ids
              AND p.title IS NOT NULL
            ORDER BY p.nm_id
            """
        ).bindparams(__import__("sqlalchemy").bindparam("nm_ids", expanding=True)),
        {"project_id": int(project_id), "nm_ids": [int(x) for x in nm_ids]},
    ).all()
    return [str(row[0]) for row in rows if row and row[0] is not None]


def test_category_meaning_loads_expressive_from_llm_cache(tmp_path: Path):
    session = make_session()
    old_env = os.environ.get("SEO_EXPRESSIVE_CACHE_DIR")
    os.environ["SEO_EXPRESSIVE_CACHE_DIR"] = str(tmp_path)
    try:
        _ensure_reviews_tables(session)

        # Seed category 812 (Кружки): products + reviews (rating>=4).
        upsert_product_evidence(session, nm_id=10, subject_id=812, title="Кружка котик")
        upsert_product_evidence(session, nm_id=11, subject_id=812, title="Кружка подарок")
        session.execute(text("UPDATE products SET subject_name='Кружки' WHERE project_id=1 AND subject_id=812"))

        ts = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
                VALUES (1, 10, 5, :ts, :raw)
                """
            ),
            {"ts": ts, "raw": json.dumps({"text": "Очень милая кружка"}, ensure_ascii=False)},
        )
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
                VALUES (1, 11, 5, :ts, :raw)
                """
            ),
            {"ts": ts, "raw": json.dumps({"text": "Покупала в подарок"}, ensure_ascii=False)},
        )
        session.commit()

        scope = fetch_category_review_scope(session, project_id=1, category_id=812, min_rating=4, limit=5000)
        titles = _fetch_titles(session, project_id=1, nm_ids=list(scope.nm_ids))
        built = build_category_expressive_input(category_name=scope.category_name or "Кружки", reviews=scope.review_snippets, titles=titles)

        parsed_llm = {
            "version": "v1",
            "task": "category",
            "category_name": "Кружки",
            "vibes": [
                {"label": "Подарочность", "confidence": 0.9, "evidence_spans": ["Покупала в подарок", "Очень милая кружка"]},
            ],
            "summary": "",
        }

        store = CategoryExpressiveStore(root_dir=tmp_path)
        key = CategoryExpressiveCacheKey(
            project_id=1,
            category_id=812,
            model=str(settings.OPENROUTER_CHAT_MODEL),
            prompt_version="v1",
            input_hash=built.input_hash,
        )
        store.put(
            key=key,
            raw_response={"usage": {"cost": 0.0}},
            parsed=parsed_llm,
            validation={"evidence_quality": 1.0},
            overwrite=True,
        )

        meaning = build_category_meaning(session, project_id=1, category_id=812)
        payload = meaning.to_dict()

        assert payload["expressive"]["vibes"] == ["Подарочность"]
        assert payload["expressive"]["llm"]["category_name"] == "Кружки"
    finally:
        if old_env is None:
            os.environ.pop("SEO_EXPRESSIVE_CACHE_DIR", None)
        else:
            os.environ["SEO_EXPRESSIVE_CACHE_DIR"] = old_env
        session.close()

