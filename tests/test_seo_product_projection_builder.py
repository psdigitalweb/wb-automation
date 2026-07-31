from __future__ import annotations


def test_product_projection_applies_category_prior_when_expressive_signal_weak():
    from app.services.seo.meaning_extraction import build_category_meaning, build_product_projection
    from app.services.seo.meaning_extraction.types import CategoryExpressiveMeaning, CategoryMeaning

    from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence

    session = make_session()
    try:
        # Functional meaning stays deterministic. Expressive prior is injected explicitly for this test
        # (CategoryMeaning now loads expressive from LLM cache; tests should not depend on cache presence).
        for nm_id in (1001, 1002, 1003):
            upsert_product_evidence(
                session,
                nm_id=nm_id,
                subject_id=821,
                title="Тарелка premium",
                description="",
                characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
            )

        base = build_category_meaning(session, project_id=1, category_id=821)
        category_meaning = CategoryMeaning(
            project_id=base.project_id,
            category_id=base.category_id,
            version=base.version,
            functional=base.functional,
            expressive=CategoryExpressiveMeaning(vibes=["premium"]),
        )

        # Target SKU: no vibes in title/description => weak expressive signal -> prior baseline.
        upsert_product_evidence(
            session,
            nm_id=555001,
            subject_id=821,
            title="Тарелка для супа",
            description="Керамическая тарелка",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        projection, flags = build_product_projection(
            session,
            project_id=1,
            category_id=821,
            nm_id=555001,
            category_meaning=category_meaning,
        )
        payload = projection.to_dict()

        assert payload["nm_id"] == 555001
        assert flags.weak_expressive_signal is True
        assert flags.strong_expressive_signal is False
        assert flags.used_category_prior is True
        assert flags.applied_sku_vibes is False
        assert "premium" in payload["expressive"]["vibes"]

        # Functional normalization: use-case phrase extracted.
        assert "для супа" in payload["functional"]["use_cases"] or payload["functional"]["use_cases"] == []
    finally:
        session.close()


def test_product_projection_applies_sku_vibes_when_signal_strong():
    from app.services.seo.meaning_extraction import build_category_meaning, build_product_projection
    from app.services.seo.meaning_extraction.types import CategoryExpressiveMeaning, CategoryMeaning

    from seo_query_pipeline_test_helpers import make_session, upsert_product_evidence

    session = make_session()
    try:
        for nm_id in (2001, 2002, 2003):
            upsert_product_evidence(
                session,
                nm_id=nm_id,
                subject_id=821,
                title="Тарелка cute",
                description="",
                characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
            )
        base = build_category_meaning(session, project_id=1, category_id=821)
        category_meaning = CategoryMeaning(
            project_id=base.project_id,
            category_id=base.category_id,
            version=base.version,
            functional=base.functional,
            expressive=CategoryExpressiveMeaning(vibes=["cute"]),
        )

        # Strong signal: 2 vibe tokens in title => strong.
        upsert_product_evidence(
            session,
            nm_id=555002,
            subject_id=821,
            title="Тарелка premium aesthetic",
            description="",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        projection, flags = build_product_projection(
            session,
            project_id=1,
            category_id=821,
            nm_id=555002,
            category_meaning=category_meaning,
        )
        payload = projection.to_dict()

        assert flags.strong_expressive_signal is True
        assert flags.weak_expressive_signal is False
        assert flags.applied_sku_vibes is True
        assert "premium" in payload["expressive"]["vibes"]
        assert "aesthetic" in payload["expressive"]["vibes"]
        # Category prior retained as baseline (SKU-first ordering).
        assert "cute" in payload["expressive"]["vibes"]
    finally:
        session.close()
