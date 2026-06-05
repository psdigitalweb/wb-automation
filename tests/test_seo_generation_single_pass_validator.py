from app.services.seo.generation.single_pass_validator import (
    validate_blacklist,
    validate_format,
    validate_generation,
    validate_keyword_coverage,
    validate_main_query_in_title,
)


def _parsed(*, title: str = "Кружка капибара", blocks: list[str] | None = None) -> dict:
    description_blocks = blocks or [
        "Кружка капибара стоит на рабочем столе.",
        "Керамика подходит для чая.",
        "Рисунок виден на корпусе.",
        "Форма обычная для домашнего использования.",
        "Текст остается фактическим.",
        "Финальный блок без обещаний.",
    ]
    return {
        "title": title,
        "description": "\n\n".join(description_blocks),
        "description_blocks": description_blocks,
    }


def test_single_pass_format_validator_requires_title_and_six_blocks() -> None:
    errors = validate_format(_parsed(title="", blocks=["one", "", "three"]))

    assert "missing_title" in errors
    assert "wrong_block_count:3" in errors
    assert "empty_block:2" in errors


def test_single_pass_keyword_coverage_is_sentence_scoped() -> None:
    result = validate_keyword_coverage(
        "Кружка стоит на столе. Капибара нарисована отдельно.",
        ["кружка капибара", "стоит столе"],
    )

    assert result["covered"] == ["стоит столе"]
    assert result["missing"] == ["кружка капибара"]


def test_single_pass_blacklist_and_main_query_checks() -> None:
    assert validate_blacklist("Это идеальный выбор и не просто кружка.") == [
        "идеальный выбор",
        "не просто кружка",
    ]
    assert validate_main_query_in_title("Кружка капибара", "кружка капибара") is True
    assert validate_main_query_in_title("Керамическая кружка", "кружка капибара") is False


def test_single_pass_generation_status_payload_passes_clean_result() -> None:
    result = validate_generation(
        _parsed(),
        ["кружка капибара", "керамика подходит"],
        "Кружка капибара",
    )

    assert result == {
        "passed": True,
        "format_errors": [],
        "keyword_coverage": {
            "covered": ["кружка капибара", "керамика подходит"],
            "missing": [],
        },
        "blacklist_hits": [],
        "main_query_in_title": True,
    }
