from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.services.seo.expressive_llm.category_extractive_service import run_single_category_expressive_extraction
from app.services.seo.expressive_llm.storage import CategoryExpressiveStore
from app.services.seo.providers.base import ChatResponse
from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence


class _FakeProvider:
    def __init__(self, *, content: str, model: str = "fake-model") -> None:
        self._content = content
        self._model = model
        self.calls: int = 0

    def generate_chat(self, messages, *, temperature=None, top_p=None, max_tokens=None):  # noqa: ANN001
        self.calls += 1
        return ChatResponse(model=self._model, content=self._content, raw_response={"usage": {"cost": 0.0}})


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


def test_single_category_runner_cache_hit_and_persistence(tmp_path: Path):
    session = make_session()
    try:
        _ensure_reviews_tables(session)

        # Category 821
        upsert_product_evidence(session, nm_id=10, subject_id=821, title="Title A")
        upsert_product_evidence(session, nm_id=11, subject_id=821, title="Title B")
        session.execute(text("UPDATE products SET subject_name='Тарелки' WHERE project_id=1 AND subject_id=821"))

        ts = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)
        # Reviews must be exact substrings for evidence spans.
        r1 = "Очень милые"
        r2 = "Цвета нежные"
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
                VALUES (1, 10, 5, :ts, :raw)
                """
            ),
            {"ts": ts, "raw": json.dumps({"text": r1}, ensure_ascii=False)},
        )
        session.execute(
            text(
                """
                INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
                VALUES (1, 11, 5, :ts, :raw)
                """
            ),
            {"ts": ts, "raw": json.dumps({"text": r2}, ensure_ascii=False)},
        )
        session.commit()

        content = json.dumps(
            {
                "version": "v1",
                "task": "category",
                "category_name": "Тарелки",
                "vibes": [
                    {"label": "милые", "confidence": 0.9, "evidence_spans": [r1, r2]},
                ],
                "summary": "",
            },
            ensure_ascii=False,
        )
        provider = _FakeProvider(content=content)
        store = CategoryExpressiveStore(root_dir=tmp_path)

        res1 = run_single_category_expressive_extraction(
            session,
            project_id=1,
            category_id=821,
            model="openai/gpt-4.1-mini",
            prompt_version="v1",
            store=store,
            provider=provider,
        )
        assert res1.cache_hit is False
        assert provider.calls == 1
        assert (res1.artifact.artifact_dir / "parsed.json").exists()
        assert (res1.artifact.artifact_dir / "input_payload.json").exists()
        assert (res1.artifact.artifact_dir / "llm_messages.json").exists()
        assert float(res1.validation["evidence_quality"]) == 1.0

        res2 = run_single_category_expressive_extraction(
            session,
            project_id=1,
            category_id=821,
            model="openai/gpt-4.1-mini",
            prompt_version="v1",
            store=store,
            provider=provider,
        )
        assert res2.cache_hit is True
        assert provider.calls == 1  # no second LLM call
    finally:
        session.close()
