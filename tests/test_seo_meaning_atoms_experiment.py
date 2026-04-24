from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    SeoQueryAnnotation,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryMeaning,
    SeoSkuMeaningAnnotation,
)
from app.services.seo.atoms.v1.guards import apply_query_guards, apply_sku_guards, atom_matches
from app.services.seo.atoms.v1.llm_extractors import (
    MeaningAtomsExtractionError,
    normalize_query_atoms_v02,
    parse_query_atoms_response,
)
from app.services.seo.atoms.v1.matcher_v1 import match_atoms_v1, normalize_query_atoms_v1, normalize_sku_atoms_v1
from app.services.seo.atoms.v1.schemas import MeaningAtom, QueryAtoms, SkuAtoms
from app.services.seo.atoms.v1.vision import parse_vision_sku_atoms_response
from app.services.seo.experiments.meaning_atoms.comparison import run_comparison
from app.services.seo.experiments.meaning_atoms.error_analysis import build_error_analysis_rows
from app.services.seo.experiments.meaning_atoms.matcher import match_atoms
from app.services.seo.experiments.meaning_atoms.readiness_report import build_matcher_readiness_payload
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_queries_normalized"],
            Base.metadata.tables["seo_query_annotations"],
            Base.metadata.tables["seo_query_clusters"],
            Base.metadata.tables["seo_query_cluster_memberships"],
            Base.metadata.tables["seo_query_meanings"],
            Base.metadata.tables["seo_meaning_embeddings"],
            Base.metadata.tables["seo_category_bootstrap_runs"],
            Base.metadata.tables["seo_category_matching_readiness"],
            Base.metadata.tables["seo_sku_meaning_annotations"],
            Base.metadata.tables["seo_sku_query_judgments"],
        ],
    )
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


class FakeAtomsProvider(ChatProvider):
    chat_model = "fake/atoms"

    def generate_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        del temperature, top_p, max_tokens
        prompt = "\n".join(message.content for message in messages)
        if "SkuAtoms" in prompt:
            payload = {
                "product_type": "кружка",
                "product_identity": "милая керамическая кружка с принтом",
                "facts": [{"type": "product_type", "field": "product_type", "value": "кружка"}],
                "positive_atoms": [{"type": "expressive", "field": "expressive", "value": "милая"}],
                "negative_fit_atoms": [],
            }
        else:
            payload = {
                "product_type": "кружка",
                "buyer_intent": "query intent",
                "required_atoms": [],
                "preferred_atoms": [],
                "excluded_atoms": [],
                "genericness": "specific",
            }
        return ChatResponse(model=self.chat_model, content=json.dumps(payload, ensure_ascii=False), raw_response={})


def test_llm_response_parser_accepts_valid_json_and_rejects_malformed() -> None:
    atoms = parse_query_atoms_response(
        '```json\n{"product_type":"кружка","buyer_intent":"ищет милую кружку"}\n```',
        query="кружка милая",
        cluster_key="c1",
    )
    assert atoms.product_type == "кружка"
    assert atoms.query == "кружка милая"
    with pytest.raises(MeaningAtomsExtractionError):
        parse_query_atoms_response("not json")


def test_vision_parser_accepts_dict_atom_payload() -> None:
    atoms = parse_vision_sku_atoms_response(
        json.dumps(
            {
                "product_type": "mug",
                "product_identity": "test",
                "facts": {"print": "design", "color": "white", "motif": "flowers", "packaging": "gift_box"},
                "positive_atoms": {"expressive": "cute"},
                "negative_fit_atoms": {},
            }
        ),
        project_id=1,
        category_id=812,
        nm_id=1,
    )
    labels = {(item.type, item.field, str(item.value)) for item in atoms.facts}
    assert ("visual", "design", "print") in labels
    assert ("attribute", "color", "white") in labels
    assert ("visual", "motif", "flowers") in labels
    assert ("attribute", "packaging", "gift_box") in labels
    assert any(item.field == "expressive" and item.value == "cute" for item in atoms.positive_atoms)


def test_vision_parser_accepts_list_of_single_key_atom_payload() -> None:
    atoms = parse_vision_sku_atoms_response(
        json.dumps(
            {
                "product_type": "mug",
                "product_identity": "test",
                "facts": [{"color": "pink"}, {"print": "Happy year"}, {"packaging": "gift_box"}],
                "positive_atoms": [{"expressive": "festive"}],
                "negative_fit_atoms": [],
            }
        )
    )
    labels = {(item.type, item.field, str(item.value)) for item in atoms.facts}
    assert ("attribute", "color", "pink") in labels
    assert ("visual", "design", "print") in labels
    assert ("attribute", "packaging", "gift_box") in labels
    assert any(item.field == "expressive" and item.value == "festive" for item in atoms.positive_atoms)


def test_vision_parser_accepts_audience_v1_payload() -> None:
    atoms = parse_vision_sku_atoms_response(
        json.dumps(
            {
                "product_type": "кружка",
                "product_identity": "test",
                "visual_facts": [{"print": "design"}, {"motif": "капибара"}],
                "ocr_text": ["happy birthday"],
                "audience_hypotheses": [{"value": "подруга", "confidence": 0.7}, "девушка"],
                "occasion_hypotheses": ["день рождения"],
                "style_archetypes": ["милая", "pinterest"],
                "supported_query_intents": ["кружка в подарок"],
                "negative_query_intents": ["без рисунка"],
            }
        )
    )
    facts = {(item.type, item.field, str(item.value)) for item in atoms.facts}
    positives = {(item.type, item.field, str(item.value)) for item in atoms.positive_atoms}
    negatives = {(item.type, item.field, str(item.value)) for item in atoms.negative_fit_atoms}
    assert ("visual", "design", "print") in facts
    assert ("visual", "ocr_text", "happy birthday") in facts
    assert ("recipient", "recipient", "подруга") in positives
    assert ("occasion", "occasion", "день рождения") in positives
    assert ("expressive", "expressive", "милая") in positives
    assert ("attribute", "negative", "без рисунка") in negatives


def test_query_guards_preserve_hard_requirements_from_examples() -> None:
    atoms = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка для папы на день рождения 800 мл без рисунка"])
    labels = {(item.type, item.field, str(item.value)) for item in atoms.required_atoms}
    excluded = {(item.field, item.value) for item in atoms.excluded_atoms}
    assert ("recipient", "recipient", "папа") in labels
    assert ("numeric", "volume_ml", "800") in labels
    assert ("design", "print") in excluded


def test_query_guards_keep_hard_constraints_on_primary_query_only() -> None:
    atoms = apply_query_guards(
        QueryAtoms(product_type="кружка"),
        ["кружка милая", "кружка для папы 800 мл", "кружки для кофемашины"],
    )
    labels = {(item.type, item.field, str(item.value)) for item in atoms.required_atoms}
    assert ("recipient", "recipient", "папа") not in labels
    assert ("numeric", "volume_ml", "800") not in labels
    assert ("compatibility", "compatibility", "coffee_machine") not in labels
    assert any(item.field == "expressive" for item in atoms.preferred_atoms)


def test_query_guards_do_not_promote_cluster_variant_expressive_terms() -> None:
    atoms = apply_query_guards(
        QueryAtoms(product_type="кружка", genericness="broad"),
        ["кружка для чая", "кружка для чая прикольная", "кружка для чая эстетичная"],
    )
    assert not any(item.field == "expressive" for item in atoms.preferred_atoms)
    assert atoms.genericness == "broad"


def test_capybara_query_guard_matches_sku_visual_motif() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        positive_atoms=[MeaningAtom(type="visual", field="motif", value="капибары")],
    )
    query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка с капибарой"])

    labels = {(item.type, item.field, str(item.value)) for item in query.required_atoms}
    assert ("visual", "motif", "капибара") in labels
    assert query.genericness == "specific"

    result = match_atoms_v1(sku, query, query_text="кружка с капибарой", ranking_value_used=3202)
    assert result.bucket == "primary"
    assert result.score >= 0.98
    assert any("motif:капибара" in item for item in result.matched_atoms)


def test_visual_motif_guards_are_lexicon_based_not_single_phrase() -> None:
    fox_sku = SkuAtoms(
        product_type="кружка",
        positive_atoms=[MeaningAtom(type="visual", field="motif", value="лисы")],
    )
    fox_query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка с лисой"])
    fox_labels = {(item.type, item.field, str(item.value)) for item in fox_query.required_atoms}
    assert ("visual", "motif", "лиса") in fox_labels
    assert fox_query.genericness == "specific"
    assert match_atoms_v1(fox_sku, fox_query, query_text="кружка с лисой", ranking_value_used=500).bucket == "primary"

    cat_sku = SkuAtoms(
        product_type="кружка",
        positive_atoms=[MeaningAtom(type="visual", field="motif", value="кошки")],
    )
    cat_query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка с котиком"])
    cat_result = match_atoms_v1(cat_sku, cat_query, query_text="кружка с котиком", ranking_value_used=500)
    assert cat_result.bucket == "primary"
    assert any("motif:кот" in item for item in cat_result.matched_atoms)


def test_visual_motif_guards_avoid_common_non_visual_accessories() -> None:
    query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка с крышкой"])
    assert not any(item.field == "motif" for item in query.required_atoms)
    assert query.genericness == "broad"


def test_cute_guard_does_not_match_name_or_unrelated_words() -> None:
    name_query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка людмила"])
    money_query = apply_query_guards(QueryAtoms(product_type="кружка", genericness="broad"), ["кружка школа универ то се миллионер"])

    assert not any(item.field == "expressive" for item in name_query.preferred_atoms)
    assert not any(item.field == "expressive" for item in money_query.preferred_atoms)
    assert name_query.genericness == "broad"
    assert money_query.genericness == "broad"


def test_recipient_field_family_matches_audience_and_softens_broad_audience() -> None:
    query_recipient = MeaningAtom(type="recipient", field="audience", value="подруге", importance="hard")
    sku_recipient = MeaningAtom(type="recipient", field="recipient", value="подруга")
    assert atom_matches(query_recipient, sku_recipient)

    normalized = normalize_query_atoms_v02(
        QueryAtoms(
            product_type="кружка",
            required_atoms=[MeaningAtom(type="recipient", field="audience", value="женская", importance="hard")],
        ),
        primary_query="кружка женская красивая",
    )
    assert not normalized.required_atoms
    assert normalized.preferred_atoms


def test_vision_english_atoms_match_russian_query_atoms() -> None:
    assert atom_matches(
        MeaningAtom(type="expressive", field="expressive", value="cute"),
        MeaningAtom(type="expressive", field="expressive", value="милая"),
    )
    assert atom_matches(
        MeaningAtom(type="attribute", field="packaging", value="gift_box"),
        MeaningAtom(type="attribute", field="packaging", value="подарочная упаковка"),
    )
    assert atom_matches(
        MeaningAtom(type="visual", field="motif", value="capybara fairy"),
        MeaningAtom(type="visual", field="motif", value="капибара"),
    )


def test_sku_guards_extract_product_facts_from_characteristics() -> None:
    sku = apply_sku_guards(
        SkuAtoms(product_type="кружка"),
        evidence={
            "product": {
                "characteristics": [
                    {"name": "Объем (мл)", "value": 450},
                    {"name": "Цвет", "value": ["белый"]},
                    {"name": "Декоративные элементы", "value": ["принт"]},
                ]
            }
        },
        meaning_payload={"functional": {"product_type": "кружка"}, "expressive": {"vibes": ["Милота и уют"]}},
    )
    facts = {(item.field, str(item.value)) for item in sku.facts}
    assert ("volume_ml", "450") in facts
    assert ("color", "белый") in facts
    assert ("design", "print") in facts
    assert any(item.field == "expressive" for item in sku.positive_atoms)


def test_atoms_matcher_rejects_volume_mismatch_and_no_print_conflict() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[
            MeaningAtom(type="product_type", field="product_type", value="кружка"),
            MeaningAtom(type="numeric", field="volume_ml", value=450),
            MeaningAtom(type="visual", field="design", value="print"),
        ],
    )
    volume_query = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка 800 мл для чая"])
    volume_result = match_atoms(sku, volume_query, query_text="кружка 800 мл для чая")
    assert volume_result.bucket == "rejected"
    assert volume_result.missing_atoms

    no_print_query = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка белая без рисунка"])
    no_print_result = match_atoms(sku, no_print_query, query_text="кружка белая без рисунка")
    assert no_print_result.bucket == "rejected"
    assert no_print_result.conflict_atoms


def test_atoms_matcher_rejects_recipient_mismatch_and_lifts_expressive_match() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="product_type", field="product_type", value="кружка")],
        positive_atoms=[
            MeaningAtom(type="recipient", field="recipient", value="подруга"),
            MeaningAtom(type="expressive", field="expressive", value="милота и уют"),
        ],
    )
    dad_query = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка для папы на день рождения"])
    dad_result = match_atoms(sku, dad_query, query_text="кружка для папы на день рождения")
    assert dad_result.bucket == "rejected"

    cute_query = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка милая"])
    cute_result = match_atoms(sku, cute_query, query_text="кружка милая")
    assert cute_result.bucket == "primary"


def test_atoms_matcher_accepts_matched_recipient_across_field_names() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="product_type", field="product_type", value="кружка")],
        positive_atoms=[
            MeaningAtom(type="recipient", field="recipient", value="подруга"),
            MeaningAtom(type="expressive", field="expressive", value="милая"),
        ],
    )
    query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="recipient", field="audience", value="подруге", importance="hard")],
        preferred_atoms=[MeaningAtom(type="expressive", field="style", value="милая")],
        genericness="specific",
    )
    result = match_atoms(sku, query, query_text="кружка для подруги подарочная")
    assert result.bucket == "primary"


def test_atoms_matcher_rejects_explicit_missing_attribute_but_not_generic_beverage() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="product_type", field="product_type", value="кружка")],
        positive_atoms=[MeaningAtom(type="expressive", field="expressive", value="красивая")],
    )
    large_query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="attribute", field="size", value="большая", importance="hard")],
        preferred_atoms=[MeaningAtom(type="expressive", field="expressive", value="красивая")],
    )
    large_result = match_atoms(sku, large_query, query_text="кружка большая")
    assert large_result.bucket == "rejected"

    tea_query = normalize_query_atoms_v02(
        QueryAtoms(
            product_type="кружка",
            required_atoms=[MeaningAtom(type="attribute", field="attributes", value="чай", importance="hard")],
            preferred_atoms=[MeaningAtom(type="expressive", field="expressive", value="красивая")],
        ),
        primary_query="кружка для чая красивая",
    )
    tea_result = match_atoms(sku, tea_query, query_text="кружка для чая красивая")
    assert tea_result.bucket == "primary"


def test_negative_strict_male_gift_does_not_block_generic_gift() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="product_type", field="product_type", value="кружка")],
        positive_atoms=[MeaningAtom(type="recipient", field="recipient", value="подруга")],
        negative_fit_atoms=[MeaningAtom(type="attribute", field="negative", value="строгий мужской подарок")],
    )
    generic_gift = QueryAtoms(
        product_type="кружка",
        preferred_atoms=[MeaningAtom(type="occasion", field="occasion", value="подарок")],
    )
    generic_result = match_atoms(sku, generic_gift, query_text="кружка для подарка")
    assert generic_result.bucket != "rejected"

    male_gift = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="recipient", field="recipient", value="мужчина", importance="hard")],
        preferred_atoms=[MeaningAtom(type="occasion", field="occasion", value="подарок")],
    )
    male_result = match_atoms(sku, male_gift, query_text="кружка для мужчины подарочная")
    assert male_result.bucket == "rejected"


def test_atoms_v1_normalizer_assigns_roles_and_evidence() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="numeric", field="volume_ml", value=450, source="product_characteristics")],
        positive_atoms=[
            MeaningAtom(type="recipient", field="recipient", value="подруга", source="vision_audience"),
            MeaningAtom(type="expressive", field="expressive", value="милая", source="vision_audience"),
        ],
        negative_fit_atoms=[MeaningAtom(type="attribute", field="negative", value="строгий мужской подарок", source="vision_audience")],
    )
    sku_v1 = normalize_sku_atoms_v1(sku)
    assert any(item.role == "hard_fact" and item.evidence_type == "product_data" for item in sku_v1.hard_facts)
    assert any(item.role == "audience_hypothesis" and item.value == "подруга" for item in sku_v1.audience_hypotheses)
    assert any(item.role == "negative_intent" for item in sku_v1.negative_intents)

    query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="recipient", field="recipient", value="женская", importance="hard")],
        preferred_atoms=[MeaningAtom(type="expressive", field="expressive", value="милая")],
    )
    query_v1 = normalize_query_atoms_v1(query, query_text="кружка женская милая")
    assert not any(item.value == "женская" for item in query_v1.required_atoms)
    assert any(item.value == "женская" for item in query_v1.preferred_atoms)


def test_atoms_v1_matcher_uses_structured_negative_intents() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[MeaningAtom(type="product_type", field="product_type", value="кружка")],
        positive_atoms=[
            MeaningAtom(type="recipient", field="recipient", value="подруга", source="vision_audience"),
            MeaningAtom(type="expressive", field="expressive", value="милая", source="vision_audience"),
        ],
        negative_fit_atoms=[MeaningAtom(type="attribute", field="negative", value="строгий мужской подарок", source="vision_audience")],
    )
    friend_query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="recipient", field="recipient", value="подруга", importance="hard")],
        preferred_atoms=[MeaningAtom(type="occasion", field="occasion", value="подарок")],
    )
    friend_result = match_atoms_v1(sku, friend_query, query_text="кружка для подруги подарочная")
    assert friend_result.bucket in {"primary", "secondary"}

    male_query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="recipient", field="recipient", value="мужчина", importance="hard")],
        preferred_atoms=[MeaningAtom(type="occasion", field="occasion", value="подарок")],
    )
    male_result = match_atoms_v1(sku, male_query, query_text="кружка для мужчины подарочная")
    assert male_result.bucket == "rejected"


def test_atoms_v1_rejects_loved_recipient_and_liter_volume_mismatch() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[
            MeaningAtom(type="product_type", field="product_type", value="кружка"),
            MeaningAtom(type="numeric", field="volume_ml", value=325, source="product_characteristics"),
        ],
        positive_atoms=[MeaningAtom(type="recipient", field="recipient", value="любимая", source="product_characteristics")],
    )

    beloved_male = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка для любимого мужчины"])
    beloved_male_result = match_atoms_v1(sku, beloved_male, query_text="кружка для любимого мужчины")
    assert beloved_male_result.bucket == "rejected"
    assert any("мужчина" in item or "любимый" in item for item in beloved_male_result.missing_atoms)

    grandma = apply_query_guards(QueryAtoms(product_type="кружка"), ["кружка любимой бабушке"])
    grandma_result = match_atoms_v1(sku, grandma, query_text="кружка любимой бабушке")
    assert grandma_result.bucket == "rejected"
    assert any("бабушка" in item for item in grandma_result.missing_atoms)

    liter = apply_query_guards(QueryAtoms(product_type="кружка"), ["литровая кружка для чая"])
    liter_result = match_atoms_v1(sku, liter, query_text="литровая кружка для чая")
    assert liter_result.bucket == "rejected"
    assert any("1000" in item for item in liter_result.missing_atoms)


def test_atoms_v1_1_does_not_promote_cluster_variant_hard_requirements() -> None:
    query = QueryAtoms(
        product_type="кружка",
        required_atoms=[MeaningAtom(type="attribute", field="quantity", value="set", importance="hard")],
        preferred_atoms=[MeaningAtom(type="attribute", field="color", value="белый")],
    )
    query_v1 = normalize_query_atoms_v1(query, query_text="кружка для кофе")
    assert not any(item.field == "quantity" for item in query_v1.required_atoms)
    assert any(item.field == "quantity" for item in query_v1.preferred_atoms)


def test_atoms_v1_1_rejects_accessory_queries_and_caps_color_only() -> None:
    sku = SkuAtoms(
        product_type="кружка",
        facts=[
            MeaningAtom(type="product_type", field="product_type", value="кружка"),
            MeaningAtom(type="attribute", field="color", value="белый"),
        ],
    )
    accessory = match_atoms_v1(SkuAtoms(product_type="кружка"), QueryAtoms(product_type="кружка"), query_text="сеточка для чая в кружку")
    assert accessory.bucket == "rejected"
    assert any("product_type conflict" in item for item in accessory.conflict_atoms)

    color_only = QueryAtoms(
        product_type="кружка",
        preferred_atoms=[MeaningAtom(type="attribute", field="color", value="белый")],
        genericness="specific",
    )
    color_result = match_atoms_v1(sku, color_only, query_text="кружка белая", ranking_value_used=10000)
    assert color_result.bucket == "rejected"


def test_error_analysis_rows_include_user_review_columns() -> None:
    rows = build_error_analysis_rows(
        [
            {
                "nm_id": "1",
                "query": "кружка белая",
                "expected_bucket": "rejected",
                "current_bucket": "primary",
                "atoms_bucket": "secondary",
                "missing_atoms": "",
                "conflict_atoms": "",
                "atoms_reasons": "bucket capped: low-signal-only query",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["review_status"] == "todo"
    assert rows[0]["user_correct_bucket"] == "rejected"
    assert rows[0]["user_error_type"] == ""


def test_matcher_readiness_report_marks_primary_gate_ready(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "labelled_rows": 191,
                "current_primary_precision": 0.2143,
                "atoms_primary_precision": 0.8857,
                "current_bad_primary_count": 88,
                "atoms_bad_primary_count": 4,
                "atoms_bucket_accuracy": 0.6387,
                "target_lift_count": 21,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "error_analysis_v1_2_labelled_only.csv").write_text(
        "auto_issue_type,auto_root_cause\natoms_under_promoted,expressive_fit\n",
        encoding="utf-8-sig",
    )
    payload = build_matcher_readiness_payload(run_dir=run_dir)
    assert payload["checks"]["primary_precision"] is True
    assert payload["checks"]["bad_primary"] is True
    assert payload["status"] == "ready_as_primary_eligibility_layer_not_full_bucket_replacement"


def test_comparison_runner_outputs_files(tmp_path: Path) -> None:
    session = _make_session()
    try:
        cluster = SeoQueryCluster(
            project_id=1,
            category_id=812,
            cluster_key="c_cute",
            label="кружка милая",
            top_query_text="кружка милая",
            status="ready",
            query_count=1,
        )
        session.add(cluster)
        session.flush()
        annotation = SeoQueryAnnotation(
            project_id=1,
            category_id=812,
            normalized_query_text="кружка милая",
            pruning_status="keep",
            annotation_status="done",
            is_kept_for_pipeline=True,
            query_type="mid",
            intent_type="product",
        )
        session.add(annotation)
        session.flush()
        session.add(
            SeoQueryClusterMembership(
                project_id=1,
                category_id=812,
                cluster_id=int(cluster.id),
                annotation_id=int(annotation.id),
                normalized_query_text="кружка милая",
                ranking_value_used=1200,
                membership_reason_code="test",
            )
        )
        session.add(
            SeoQueryMeaning(
                project_id=1,
                category_id=812,
                cluster_id=int(cluster.id),
                cluster_key="c_cute",
                source_query_examples=["кружка милая"],
                meaning_payload={"functional": {"product_type": "кружка"}},
                canonical_text="товар: кружка\nстиль: милая",
                genericness="specific",
                input_hash="hash",
                status="ready",
            )
        )
        session.add(
            SeoSkuMeaningAnnotation(
                project_id=1,
                category_id=812,
                nm_id=292541341,
                status="verified",
                meaning_payload={
                    "functional": {"product_type": "кружка"},
                    "expressive": {"vibes": ["Милота и уют"]},
                    "audience": ["подруга"],
                },
                evidence_hash="test",
            )
        )
        session.commit()
        result = run_comparison(
            session,
            project_id=1,
            category_id=812,
            nm_ids=[292541341],
            query_limit=1,
            output_dir=tmp_path,
            provider=FakeAtomsProvider(),
            include_rejected=True,
        )
        assert result.rows
        output = Path(result.output_dir or "")
        assert (output / "comparison.json").exists()
        assert (output / "comparison.csv").exists()
        assert (output / "report.md").exists()
        assert (output / "metrics.json").exists()
    finally:
        session.close()
