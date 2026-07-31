from __future__ import annotations


def test_query_meaning_formalization_maps_language_markers_to_vibes_as_mvp_proxy():
    from app.services.seo.meaning_extraction import formalize_query_meaning
    from app.services.seo.query_pipeline.diagnostics import ExtractedClusterProfile, QueryProfileMarker

    profile = ExtractedClusterProfile(
        cluster_key="c:1",
        profile_label_candidate="тарелка для супа premium",
        profile_strength="strong",
        profile_confidence=0.9,
        source_cluster_key="c:1",
        product_type_markers=[
            QueryProfileMarker(value="тарелка", normalized_value="тарелка", support_query_count=10, support_share=0.8, weighted_support=0.9),
        ],
        use_case_markers=[
            QueryProfileMarker(value="для супа", normalized_value="для супа", support_query_count=6, support_share=0.5, weighted_support=0.6),
        ],
        attribute_markers=[
            QueryProfileMarker(value="керамика", normalized_value="керамика", family="material", support_query_count=5, support_share=0.4, weighted_support=0.5),
        ],
        language_markers=[
            QueryProfileMarker(value="premium aesthetic", normalized_value="premium aesthetic", support_query_count=3, support_share=0.25, weighted_support=0.3),
        ],
    )

    meaning, flags = formalize_query_meaning(profile, project_id=1, category_id=821)
    payload = meaning.to_dict()

    assert payload["project_id"] == 1
    assert payload["category_id"] == 821
    assert payload["cluster_key"] == "c:1"
    assert payload["functional"]["product_type"] == "тарелка"
    assert "для супа" in payload["functional"]["use_cases"]
    assert "керамика" in payload["functional"]["attributes"]

    # MVP proxy: language markers become expressive vibes.
    assert "premium aesthetic" in payload["expressive"]["vibes"]
    assert flags.expressive_vibes_are_mvp_proxy is True
    assert flags.expressive_vibes_source == "language_markers"


def test_query_meaning_formalization_dedupes_and_is_deterministic():
    from app.services.seo.meaning_extraction import formalize_query_meaning
    from app.services.seo.query_pipeline.diagnostics import ExtractedClusterProfile, QueryProfileMarker

    profile = ExtractedClusterProfile(
        cluster_key="c:2",
        profile_label_candidate="x",
        profile_strength="medium",
        profile_confidence=0.5,
        source_cluster_key="c:2",
        product_type_markers=[
            QueryProfileMarker(value="тарелка", normalized_value="тарелка", support_query_count=2, support_share=0.2, weighted_support=0.2),
            QueryProfileMarker(value="тарелка", normalized_value="тарелка", support_query_count=1, support_share=0.1, weighted_support=0.1),
        ],
        use_case_markers=[
            QueryProfileMarker(value="для супа", normalized_value="для супа", support_query_count=2, support_share=0.2, weighted_support=0.2),
            QueryProfileMarker(value="для супа", normalized_value="для супа", support_query_count=1, support_share=0.1, weighted_support=0.1),
        ],
        attribute_markers=[],
        language_markers=[
            QueryProfileMarker(value="meme", normalized_value="meme", support_query_count=1, support_share=0.1, weighted_support=0.2),
            QueryProfileMarker(value="meme", normalized_value="meme", support_query_count=2, support_share=0.2, weighted_support=0.1),
        ],
    )

    meaning, _flags = formalize_query_meaning(profile, project_id=1, category_id=821, vibe_limit=10)
    payload = meaning.to_dict()

    assert payload["functional"]["product_type"] == "тарелка"
    assert payload["functional"]["use_cases"] == ["для супа"]
    assert payload["expressive"]["vibes"] == ["meme"]

