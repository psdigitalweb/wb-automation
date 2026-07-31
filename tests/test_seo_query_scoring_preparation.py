from __future__ import annotations

from app.services.seo.query_pipeline import run_query_hybrid_annotation
from app.services.seo.scoring.preparation import run_query_scoring_preparation

from seo_query_pipeline_test_helpers import (
    add_term_query,
    make_session,
    run_base_pipeline,
    seed_scope_data,
    upsert_product_evidence,
)


def _find_preparation(result, needle: str):
    needle = needle.lower()
    return next(
        item
        for item in result.preparations
        if needle in (item.profile_label_candidate or "").lower()
    )


def test_scoring_preparation_matches_use_case_and_attributes_and_detects_conflict():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=30, search_text="тарелка для супа", frequency=40)
        add_term_query(session, nm_id=31, search_text="тарелка глубокая", frequency=35)
        add_term_query(session, nm_id=32, search_text="тарелка керамическая", frequency=30)
        add_term_query(session, nm_id=33, search_text="тарелка фарфоровая", frequency=25)
        upsert_product_evidence(
            session,
            nm_id=38802116,
            title="Тарелка глубокая для супа",
            description="Керамическая глубокая тарелка для первых блюд и сервировки стола.",
            characteristics=[
                {"name": "Материал посуды", "value": ["керамика"]},
                {"name": "Назначение посуды", "value": ["тарелка глубокая", "суповая"]},
            ],
        )

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_scoring_preparation(
            session,
            project_id=1,
            category_id=821,
            nm_id=38802116,
            refresh_hybrid=False,
        )

        soup_prep = _find_preparation(result, "для супа")
        assert soup_prep.product_type_match.status == "matched"
        assert any(marker.normalized_value == "для супа" for marker in soup_prep.use_case_match.matched_markers)
        assert soup_prep.readiness_for_scoring == "partial"

        deep_prep = _find_preparation(result, "глубокая")
        assert deep_prep.product_type_match.status == "matched"
        assert any(marker.family == "format" for marker in deep_prep.attribute_match.matched_markers)

        ceramic_prep = _find_preparation(result, "керамическая")
        assert any(marker.family == "material" for marker in ceramic_prep.attribute_match.matched_markers)

        porcelain_prep = _find_preparation(result, "фарфор")
        assert any(marker.family == "material" for marker in porcelain_prep.attribute_match.conflicting_markers)
        assert result.diagnostics.attribute_matched_rate > 0
        assert result.diagnostics.total_cluster_comparisons == len(result.preparations)
    finally:
        session.close()


def test_scoring_preparation_marks_unknown_and_poor_when_sku_evidence_missing():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=41, search_text="тарелка для супа", frequency=30)
        upsert_product_evidence(
            session,
            nm_id=499001,
            title=None,
            description=None,
            characteristics=None,
        )

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_scoring_preparation(
            session,
            project_id=1,
            category_id=821,
            nm_id=499001,
            refresh_hybrid=False,
        )

        soup_prep = _find_preparation(result, "для супа")
        assert soup_prep.product_type_match.status == "unknown"
        assert soup_prep.use_case_match.unknown_markers
        assert soup_prep.preparation_flags.insufficient_sku_data is True
        assert soup_prep.readiness_for_scoring == "poor"
        assert result.diagnostics.insufficient_sku_data_count == len(result.preparations)
    finally:
        session.close()


def test_scoring_preparation_exposes_missing_product_type_profiles_conservatively():
    session = make_session()
    try:
        seed_scope_data(session)
        upsert_product_evidence(
            session,
            nm_id=38802116,
            title="Тарелка глубокая для супа",
            description="Керамическая глубокая тарелка для первых блюд.",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_scoring_preparation(
            session,
            project_id=1,
            category_id=821,
            nm_id=38802116,
            refresh_hybrid=False,
        )

        assert any(item.preparation_flags.missing_product_type for item in result.preparations)
        assert any(
            item.preparation_flags.missing_product_type and item.readiness_for_scoring in {"partial", "poor"}
            for item in result.preparations
        )
        assert result.diagnostics.missing_product_type_count > 0
    finally:
        session.close()
