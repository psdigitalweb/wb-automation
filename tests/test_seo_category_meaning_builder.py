from __future__ import annotations


def test_category_meaning_builder_filters_by_scope_and_thresholds():
    from app.services.seo.meaning_extraction import build_category_meaning

    from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence

    session = make_session()
    try:
        # Category scope 821: repeating patterns across >= 3 SKUs.
        for nm_id in (100, 101, 102):
            upsert_product_evidence(
                session,
                nm_id=nm_id,
                subject_id=821,
                title="Тарелка premium для супа",
                description="Aesthetic керамика для кухни",
                characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
            )
        upsert_product_evidence(
            session,
            nm_id=103,
            subject_id=821,
            title="Тарелка базовая",
            description="Просто тарелка",
            characteristics=[{"name": "Материал посуды", "value": ["стекло"]}],
        )

        # Another category (999) must not leak into 821 aggregation.
        upsert_product_evidence(
            session,
            nm_id=200,
            subject_id=999,
            title="Тарелка premium для супа",
            description="premium aesthetic",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        meaning = build_category_meaning(session, project_id=1, category_id=821)
        payload = meaning.to_dict()

        assert payload["project_id"] == 1
        assert payload["category_id"] == 821

        # Product type candidates come from noun-like title tokens; "тарелка" repeats.
        assert "тарелка" in payload["functional"]["product_types"]

        # Use case "для супа" repeats in 3 SKUs.
        assert "для супа" in payload["functional"]["use_cases"]

        # Attribute token "керамика" repeats in 3 SKUs.
        assert "керамика" in payload["functional"]["attributes"]

        # Expressive meaning is loaded from LLM cache if present; otherwise empty.
        assert payload["expressive"]["vibes"] == []
        assert payload["expressive"]["llm"] is None
    finally:
        session.close()


def test_category_meaning_builder_uses_small_category_thresholds():
    from app.services.seo.meaning_extraction import build_category_meaning

    from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence

    session = make_session()
    try:
        # total_sku_count = 3 (< 20), support >= 2 and share >= 0.25
        upsert_product_evidence(
            session,
            nm_id=301,
            subject_id=777,
            title="Тарелка aesthetic",
            description="aesthetic",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )
        upsert_product_evidence(
            session,
            nm_id=302,
            subject_id=777,
            title="Тарелка aesthetic",
            description="",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )
        upsert_product_evidence(
            session,
            nm_id=303,
            subject_id=777,
            title="Тарелка базовая",
            description="",
            characteristics=[{"name": "Материал посуды", "value": ["стекло"]}],
        )

        meaning = build_category_meaning(session, project_id=1, category_id=777)
        payload = meaning.to_dict()

        assert payload["category_id"] == 777
        assert payload["expressive"]["vibes"] == []
        assert payload["expressive"]["llm"] is None
        assert "керамика" in payload["functional"]["attributes"]
    finally:
        session.close()
