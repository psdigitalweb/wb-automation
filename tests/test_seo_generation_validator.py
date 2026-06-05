from app.schemas.seo_generation import GeneratedCard, GeneratedCharacteristic
from app.services.seo.generation.service import (
    SEO_RELEVANCE_RETRY_SCORE,
    _apply_main_query,
    _build_messages,
    _human_product_facts,
    _seo_target_items_from_groups,
    build_seo_relevance_report,
    build_seo_relevance_v2_report,
    normalize_generated_card_report,
    validate_generated_card,
)


def _valid_card(*, title: str, description: str, report: dict) -> GeneratedCard:
    return GeneratedCard(
        title=title,
        characteristics=[
            GeneratedCharacteristic(field=f"Поле {index}", value=f"Значение {index}")
            for index in range(1, 9)
        ],
        description=description,
        report=report,
    )


def _six_blocks(*blocks: str) -> str:
    assert len(blocks) == 6
    return "\n\n".join(blocks)


def _brief(*, selected: list[str] | None = None, rejected: list[str] | None = None) -> dict:
    return {
        "query_set": {
            "primary": [{"display_query": query} for query in (selected or [])],
            "secondary": [],
            "broad_context": [],
            "rejected": [{"display_query": query} for query in (rejected or [])],
            "excluded": [],
        }
    }


def _issue_names(card: GeneratedCard, brief: dict) -> list[tuple[str, str]]:
    return [(issue.check_name, issue.severity) for issue in validate_generated_card(card, brief)]


def test_used_query_report_mismatch_is_warning_not_generation_error() -> None:
    card = _valid_card(
        title="Кружка подруге керамическая",
        description=_six_blocks(
            "Кружка подруге подойдет для рабочего стола.",
            "Керамика держит тепло напитка.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Можно выбрать как спокойный бытовой подарок.",
            "Финальный текст без лишних обещаний.",
        ),
        report={"использованные_запросы": ["термокружка туристическая"]},
    )

    issues = _issue_names(card, _brief(selected=["термокружка туристическая"]))

    assert ("used_query_not_found", "warning") in issues
    assert all(severity != "error" for _, severity in issues)


def test_blocked_query_requires_phrase_like_match_not_scattered_words() -> None:
    card = _valid_card(
        title="Кружка для чая подруге",
        description=_six_blocks(
            "Кружка подходит для чая дома и в офисе.",
            "Керамическая поверхность легко моется.",
            "Кофе упомянут только как другой напиток, без SEO-фразы.",
            "Комплектация соответствует карточке.",
            "Можно использовать утром или вечером.",
            "Финал спокойный и фактический.",
        ),
        report={"использованные_запросы": []},
    )

    issues = _issue_names(card, _brief(selected=["кружка для чая"], rejected=["кружка для кофе"]))

    assert ("blocked_query_used", "error") not in issues


def test_blocked_query_phrase_still_fails_generation() -> None:
    card = _valid_card(
        title="Кружка для чая подруге",
        description=_six_blocks(
            "Кружка для кофе и чая стоит на рабочем столе.",
            "Керамическая поверхность легко моется.",
            "Параметры берутся из фактов товара.",
            "Комплектация соответствует карточке.",
            "Можно использовать утром или вечером.",
            "Финал спокойный и фактический.",
        ),
        report={"использованные_запросы": []},
    )

    issues = _issue_names(card, _brief(selected=["кружка для чая"], rejected=["кружка для кофе"]))

    assert ("blocked_query_used", "error") in issues


def test_generation_report_keeps_only_used_selected_queries() -> None:
    card = _valid_card(
        title="Кружка подруге керамическая",
        description=_six_blocks(
            "Кружка подруге подходит для ежедневного чая.",
            "Керамика держит тепло напитка.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Можно выбрать как спокойный бытовой подарок.",
            "Финальный текст без лишних обещаний.",
        ),
        report={
            "охват_запросов": 3,
            "использованные_запросы": [
                "кружка подруге",
                "кружка для кофе",
                "несуществующий запрос",
            ],
        },
    )

    normalized = normalize_generated_card_report(
        card,
        _brief(selected=["кружка подруге", "кружка для кофе"]),
    )

    assert normalized.report["использованные_запросы"] == ["кружка подруге"]
    assert normalized.report["охват_запросов"] == 1


def test_main_query_can_be_promoted_from_secondary() -> None:
    groups = {
        "primary": [{"display_query": "кружка керамическая", "bucket": "primary"}],
        "secondary": [{"display_query": "кружка подруге", "bucket": "secondary"}],
        "broad_context": [],
        "rejected": [],
        "excluded": [],
    }

    resolved = _apply_main_query(groups, "кружка подруге")

    assert resolved == "кружка подруге"
    assert groups["primary"][0]["display_query"] == "кружка подруге"
    assert groups["primary"][0]["bucket"] == "primary"
    assert groups["secondary"] == []


def test_seo_targets_prioritize_promoted_main_query() -> None:
    groups = {
        "primary": [
            {"display_query": "кружка подруге", "bucket": "primary", "score": 1.0},
            {"display_query": "кружка милая подруге", "bucket": "primary", "score": 0.9},
        ],
        "secondary": [{"display_query": "кружка на день рождения", "bucket": "secondary", "score": 0.5}],
        "broad_context": [{"display_query": "кружка керамическая", "bucket": "broad", "score": 0.4}],
    }

    targets = _seo_target_items_from_groups(groups)

    assert targets[0]["query"] == "кружка подруге"
    assert targets[0]["priority"] == 1
    assert {item["query"] for item in targets} >= {"кружка милая подруге", "кружка на день рождения"}


def test_product_facts_drop_conflicting_visual_motif_characteristic() -> None:
    facts = _human_product_facts(
        {
            "title": 'Кружка керамическая "И что?"',
            "description": "Керамическая кружка с забавным принтом кота и милым котиком на боку.",
            "characteristics": [
                {"name": "Рисунок", "value": ["капибара"]},
                {"name": "Цвет", "value": ["розовый"]},
                {"name": "Хрупкость", "value": ["хрупкое"]},
            ],
        }
    )

    assert "Рисунок: капибара" not in facts
    assert "Рисунок: кот" in facts
    assert "Цвет: розовый" in facts
    assert "Хрупкость: хрупкое" not in facts


def test_seo_relevance_report_scores_query_coverage() -> None:
    card = _valid_card(
        title="Кружка подруге керамическая",
        description=_six_blocks(
            "Кружка подруге подходит для ежедневного чая.",
            "Керамика держит тепло напитка.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Можно выбрать как спокойный бытовой подарок.",
            "Финальный текст без лишних обещаний.",
        ),
        report={"использованные_запросы": ["кружка подруге"]},
    )
    brief = {
        "query_set": {
            "main_query_text": "кружка подруге",
            "primary": [{"display_query": "кружка подруге"}],
            "secondary": [{"display_query": "керамическая кружка"}],
            "broad_context": [],
            "rejected": [],
            "excluded": [],
        }
    }

    report = build_seo_relevance_report(card, brief, validate_generated_card(card, brief))

    assert report.main_query_in_title
    assert report.score >= 70
    assert report.covered_queries_count >= 1


def test_seo_relevance_treats_close_russian_forms_as_covered() -> None:
    card = _valid_card(
        title="Кружка керамическая",
        description=_six_blocks(
            "Кружка в коробке подойдет для подруги на праздник.",
            "Керамика держит тепло напитка.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Можно выбрать как спокойный бытовой подарок.",
            "Финальный текст без лишних обещаний.",
        ),
        report={"использованные_запросы": ["кружка подруге"]},
    )
    brief = {
        "query_set": {
            "main_query_text": "кружка подруге",
            "primary": [{"display_query": "кружка подруге"}],
            "secondary": [],
            "broad_context": [],
            "rejected": [],
            "excluded": [],
        }
    }

    report = build_seo_relevance_report(card, brief, validate_generated_card(card, brief))

    assert report.query_coverage[0].found
    assert report.description_queries_count == 1


def test_seo_relevance_v2_scores_semantic_intent_without_exact_phrase() -> None:
    card = _valid_card(
        title="Кружка подруге керамическая",
        description=_six_blocks(
            "Подарок для подруги: керамическая кружка с милым принтом.",
            "Подходит для чая и кофе дома или в офисе.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Текст звучит естественно без списка ключевых фраз.",
            "Финальный блок без лишних обещаний.",
        ),
        report={"использованные_запросы": []},
    )
    brief = {
        "query_set": {
            "main_query_text": "кружка подарочная подруге",
            "primary": [
                {
                    "display_query": "кружка подарочная подруге",
                    "matched_atoms": [
                        "product_type:кружка",
                        "hard_requirement:recipient:recipient:подруга",
                        "soft_signal:occasion:occasion:подарок",
                    ],
                    "missing_atoms": [],
                    "conflict_atoms": [],
                }
            ],
            "secondary": [],
            "broad_context": [],
            "rejected": [],
            "excluded": [],
        }
    }

    report = build_seo_relevance_v2_report(card, brief, validate_generated_card(card, brief))

    assert report.score >= 70
    assert report.intent_fit >= 0.9
    assert report.query_scores[0].unsupported_atoms == []


def test_seo_relevance_v2_penalizes_unsupported_query_intent() -> None:
    card = _valid_card(
        title="Кружка подруге керамическая",
        description=_six_blocks(
            "Керамическая кружка для подруги с милым принтом.",
            "В комплекте один предмет.",
            "Объем и материал указаны в характеристиках.",
            "Комплектация соответствует карточке.",
            "Текст спокойный и фактический.",
            "Финальный блок без лишних обещаний.",
        ),
        report={"использованные_запросы": []},
    )
    brief = {
        "query_set": {
            "main_query_text": "парные кружки для подруг с приколом",
            "primary": [
                {
                    "display_query": "парные кружки для подруг с приколом",
                    "matched_atoms": [
                        "product_type:кружки",
                        "hard_requirement:recipient:recipient:подруга",
                        "soft_signal:expressive:expressive:смешная",
                    ],
                    "missing_atoms": ["missing set_quantity: pair"],
                    "conflict_atoms": [],
                }
            ],
            "secondary": [],
            "broad_context": [],
            "rejected": [],
            "excluded": [],
        }
    }

    report = build_seo_relevance_v2_report(card, brief, validate_generated_card(card, brief))

    assert report.score < 70
    assert "смешная" in report.query_scores[0].unsupported_atoms
    assert report.weak_queries == ["парные кружки для подруг с приколом"]


def test_retry_message_mentions_low_seo_score() -> None:
    messages = _build_messages(
        {"query_set": {"main_query_text": "кружка подруге"}},
        retry_errors=[f"SEO score 40/100 ниже целевого {SEO_RELEVANCE_RETRY_SCORE}."],
    )

    assert "SEO score" in messages[-1].content
    assert "секции из системного промпта" in messages[-1].content
