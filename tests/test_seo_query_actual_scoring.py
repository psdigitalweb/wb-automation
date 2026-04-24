from __future__ import annotations

from app.services.seo.query_pipeline import run_query_hybrid_annotation
from app.services.seo.scoring.actual import _score_preparation, run_query_actual_scoring
from app.services.seo.scoring.preparation import (
    AttributeMatchResult,
    ClusterScoringPreparation,
    PreparationFlags,
    ProductTypeMatchResult,
    ScoringPreparationMarkerEvaluation,
    SkuEvidenceSummary,
    UseCaseMatchResult,
)

from seo_query_pipeline_test_helpers import (
    add_term_query,
    make_session,
    run_base_pipeline,
    seed_scope_data,
    upsert_product_evidence,
)


def _find_score(result, needle: str):
    needle = needle.lower()
    return next(
        item
        for item in result.scores
        if needle in (item.profile_label_candidate or "").lower()
    )


def test_actual_scoring_ranks_relevant_profiles_above_conflicts():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=30, search_text="тарелки для супа", frequency=40)
        add_term_query(session, nm_id=31, search_text="тарелка глубокая", frequency=35)
        add_term_query(session, nm_id=32, search_text="тарелка керамическая", frequency=30)
        add_term_query(session, nm_id=33, search_text="тарелки фарфоровые", frequency=25)
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
        result = run_query_actual_scoring(
            session,
            project_id=1,
            category_id=821,
            nm_id=38802116,
            top_limit=10,
        )

        soup_score = _find_score(result, "для супа")
        deep_score = _find_score(result, "глубокая")
        ceramic_score = _find_score(result, "керамическая")
        porcelain_score = _find_score(result, "фарфор")
        lowest_score = result.scores[-1]

        assert soup_score.final_score > 0
        assert deep_score.final_score > 0
        assert ceramic_score.final_score > porcelain_score.final_score
        assert soup_score.final_score > porcelain_score.final_score
        assert lowest_score.final_score < soup_score.final_score
        assert lowest_score.final_score <= porcelain_score.final_score
        assert "product_type" in soup_score.final_reason
        assert result.diagnostics.total_clusters_scored == len(result.scores)
        assert result.diagnostics.top_score >= result.diagnostics.avg_score >= result.diagnostics.bottom_score
        assert result.diagnostics.avg_product_type_score > 0
        assert result.diagnostics.top_clusters[0].final_score >= result.diagnostics.top_clusters[-1].final_score
    finally:
        session.close()


def test_actual_scoring_applies_insufficient_sku_penalty_for_poor_evidence():
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
        result = run_query_actual_scoring(
            session,
            project_id=1,
            category_id=821,
            nm_id=499001,
            top_limit=10,
        )

        soup_score = _find_score(result, "для супа")
        assert soup_score.readiness_for_scoring == "poor"
        assert soup_score.preparation_flags.insufficient_sku_data is True
        assert any(penalty.name == "insufficient_sku_data" for penalty in soup_score.penalties)
        assert soup_score.final_score <= -0.5
        assert result.diagnostics.negative_score_share > 0
    finally:
        session.close()


def test_actual_scoring_distribution_ranges_are_mutually_exclusive():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=30, search_text="тарелки для супа", frequency=40)
        add_term_query(session, nm_id=31, search_text="тарелка керамическая", frequency=35)
        add_term_query(session, nm_id=32, search_text="салфетки на стол", frequency=25)
        upsert_product_evidence(
            session,
            nm_id=38802116,
            title="Тарелка глубокая для супа",
            description="Керамическая тарелка для сервировки.",
            characteristics=[{"name": "Материал посуды", "value": ["керамика"]}],
        )

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_actual_scoring(
            session,
            project_id=1,
            category_id=821,
            nm_id=38802116,
            top_limit=10,
        )

        diagnostics = result.diagnostics
        assert (
            diagnostics.positive_score_count
            + diagnostics.neutral_score_count
            + diagnostics.negative_score_count
            == diagnostics.total_clusters_scored
        )
        assert abs(
            diagnostics.positive_score_share
            + diagnostics.neutral_score_share
            + diagnostics.negative_score_share
            - 1.0
        ) <= 0.0002
    finally:
        session.close()


def test_actual_scoring_downweights_semantically_weak_use_case_matches():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=30, search_text="тарелки для супа", frequency=40)
        add_term_query(session, nm_id=31, search_text="тарелка для любимого", frequency=35)
        upsert_product_evidence(
            session,
            nm_id=38802116,
            title="Тарелка для супа",
            description="Керамическая тарелка, подарок для любимого.",
            characteristics=[
                {"name": "Материал посуды", "value": ["керамика"]},
                {"name": "Назначение посуды", "value": ["тарелка"]},
            ],
        )

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_actual_scoring(
            session,
            project_id=1,
            category_id=821,
            nm_id=38802116,
            top_limit=10,
        )

        soup_score = _find_score(result, "для супа")
        romantic_score = _find_score(result, "для любимого")

        assert soup_score.use_case_score > romantic_score.use_case_score
        assert romantic_score.use_case_score == 0.05
        assert "weak_use_case_marker downweighted" in romantic_score.final_reason
        assert "weak_use_case_marker" not in soup_score.final_reason
        assert romantic_score.ranking_eligible is True
        assert romantic_score.generation_eligible is False
        assert romantic_score.generation_guardrail_reason == "weak_semantic_use_case"
    finally:
        session.close()


def test_actual_scoring_generation_guardrails_cover_true_and_false_cases():
    ready_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c1",
            profile_label_candidate="тарелки для супа",
            profile_strength="strong",
            profile_confidence=1.0,
            product_type_match=ProductTypeMatchResult(status="matched"),
            use_case_match=UseCaseMatchResult(
                matched_markers=[
                    ScoringPreparationMarkerEvaluation(
                        value="для супа",
                        normalized_value="для супа",
                        family=None,
                        status="matched",
                    )
                ]
            ),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=True,
                normalized_evidence_fields_used=["title_text"],
            ),
            preparation_flags=PreparationFlags(),
            readiness_for_scoring="ready",
        )
    )
    assert ready_item.ranking_eligible is True
    assert ready_item.generation_eligible is True
    assert ready_item.generation_guardrail_reason is None
    assert ready_item.use_case_score == 0.3

    weak_semantic_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c-weak",
            profile_label_candidate="тарелка для любимого",
            profile_strength="strong",
            profile_confidence=1.0,
            product_type_match=ProductTypeMatchResult(status="matched"),
            use_case_match=UseCaseMatchResult(
                matched_markers=[
                    ScoringPreparationMarkerEvaluation(
                        value="для любимого",
                        normalized_value="для любимого",
                        family=None,
                        status="matched",
                    )
                ]
            ),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=True,
                normalized_evidence_fields_used=["title_text", "description_text"],
            ),
            preparation_flags=PreparationFlags(),
            readiness_for_scoring="ready",
        )
    )
    assert weak_semantic_item.final_score > 0.8
    assert weak_semantic_item.ranking_eligible is True
    assert weak_semantic_item.generation_eligible is False
    assert weak_semantic_item.generation_guardrail_reason == "weak_semantic_use_case"

    weak_but_compensated_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c-weak-strong",
            profile_label_candidate="тарелка керамическая для любимого",
            profile_strength="strong",
            profile_confidence=1.0,
            product_type_match=ProductTypeMatchResult(status="matched"),
            use_case_match=UseCaseMatchResult(
                matched_markers=[
                    ScoringPreparationMarkerEvaluation(
                        value="для любимого",
                        normalized_value="для любимого",
                        family=None,
                        status="matched",
                    )
                ]
            ),
            attribute_match=AttributeMatchResult(
                matched_markers=[
                    ScoringPreparationMarkerEvaluation(
                        value="керамическая",
                        normalized_value="керамическая",
                        family="material",
                        status="matched",
                    )
                ]
            ),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=True,
                normalized_evidence_fields_used=["title_text", "attributes_text"],
            ),
            preparation_flags=PreparationFlags(),
            readiness_for_scoring="ready",
        )
    )
    assert weak_but_compensated_item.final_score >= 1.2
    assert weak_but_compensated_item.generation_eligible is True
    assert weak_but_compensated_item.generation_guardrail_reason is None

    poor_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c2",
            profile_label_candidate="тарелки для супа",
            profile_strength="strong",
            profile_confidence=1.0,
            product_type_match=ProductTypeMatchResult(status="matched"),
            use_case_match=UseCaseMatchResult(),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=False,
                description_present=False,
                normalized_evidence_fields_used=["title_text"],
            ),
            preparation_flags=PreparationFlags(),
            readiness_for_scoring="poor",
        )
    )
    assert poor_item.generation_eligible is False
    assert poor_item.generation_guardrail_reason == "poor_readiness"

    empty_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c3",
            profile_label_candidate="",
            profile_strength="empty",
            profile_confidence=0.0,
            product_type_match=ProductTypeMatchResult(status="unknown"),
            use_case_match=UseCaseMatchResult(),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=False,
                normalized_evidence_fields_used=["title_text"],
            ),
            preparation_flags=PreparationFlags(empty_profile=True, missing_product_type=True),
            readiness_for_scoring="poor",
        )
    )
    assert empty_item.generation_eligible is False
    assert empty_item.generation_guardrail_reason == "empty_profile"

    missing_type_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c4",
            profile_label_candidate="для сервировки",
            profile_strength="medium",
            profile_confidence=0.6,
            product_type_match=ProductTypeMatchResult(status="unknown"),
            use_case_match=UseCaseMatchResult(),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=True,
                normalized_evidence_fields_used=["title_text"],
            ),
            preparation_flags=PreparationFlags(missing_product_type=True),
            readiness_for_scoring="partial",
        )
    )
    assert missing_type_item.generation_eligible is False
    assert missing_type_item.generation_guardrail_reason == "missing_product_type"

    conflicting_item = _score_preparation(
        ClusterScoringPreparation(
            cluster_key="c5",
            profile_label_candidate="тарелка спорная",
            profile_strength="strong",
            profile_confidence=1.0,
            product_type_match=ProductTypeMatchResult(status="matched"),
            use_case_match=UseCaseMatchResult(),
            attribute_match=AttributeMatchResult(),
            sku_evidence_summary=SkuEvidenceSummary(
                title_present=True,
                attributes_present=True,
                description_present=True,
                normalized_evidence_fields_used=["title_text"],
            ),
            preparation_flags=PreparationFlags(conflicting_profile_markers=True),
            readiness_for_scoring="partial",
        )
    )
    assert conflicting_item.generation_eligible is False
    assert conflicting_item.generation_guardrail_reason == "conflicting_profile_markers"
