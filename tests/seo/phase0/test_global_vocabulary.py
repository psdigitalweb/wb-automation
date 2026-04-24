from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.seo.atoms.v1 import guards
from app.services.seo.global_vocabulary import load_global_vocabulary
from app.services.seo.query_meaning_matcher import matcher


VOCABULARY_PATH = Path("config/seo/global_vocabulary.json")
REQUIRED_SECTIONS = (
    "audience_taxonomy",
    "audience_synonyms",
    "expressive_taxonomy",
    "expressive_synonyms",
    "recipient_synonyms",
    "color_taxonomy",
    "color_synonyms",
    "material_taxonomy",
    "material_synonyms",
)


def _read_payload() -> dict[str, object]:
    return json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))


def _expected_expressive_synonyms() -> dict[str, list[str]]:
    expected: dict[str, list[str]] = {}
    for source in (guards._EXPRESSIVE, matcher._EXPRESSIVE_GROUPS):
        for canonical, markers in source.items():
            bucket = expected.setdefault(canonical, [])
            for marker in markers:
                if marker not in bucket:
                    bucket.append(marker)
    return expected


def _expected_material_synonyms() -> dict[str, list[str]]:
    return {
        canonical.split(":", 1)[1]: list(markers)
        for canonical, markers in matcher._MATERIAL_CONSTRAINTS.items()
    }


def _sorted_mapping_of_lists(payload: dict[str, object]) -> dict[str, list[str]]:
    return {
        str(key): sorted(str(item) for item in value)
        for key, value in payload.items()
        if isinstance(value, list)
    }


def test_global_vocabulary_json_exists_and_is_valid() -> None:
    assert VOCABULARY_PATH.exists()
    payload = _read_payload()
    assert payload["schema_version"] == "global_vocabulary_v1"
    for section in REQUIRED_SECTIONS:
        assert section in payload


def test_global_vocabulary_has_no_category_subject_literals() -> None:
    serialized = json.dumps(_read_payload(), ensure_ascii=False).lower()
    for forbidden in ("термокруж", "круж", "пивн", "кофемаш", "рюкзак", "сумка"):
        assert forbidden not in serialized


def test_global_vocabulary_snapshots_current_global_constants() -> None:
    payload = _read_payload()

    assert payload["recipient_synonyms"] == guards._RECIPIENTS
    assert payload["color_synonyms"] == guards._COLORS
    assert payload["color_taxonomy"] == list(dict.fromkeys(guards._COLORS.values()))
    assert _sorted_mapping_of_lists(payload["audience_synonyms"]) == _sorted_mapping_of_lists(
        {canonical: list(markers) for canonical, markers in matcher._AUDIENCE_GROUPS.items()}
    )
    assert _sorted_mapping_of_lists(payload["expressive_synonyms"]) == _sorted_mapping_of_lists(
        _expected_expressive_synonyms()
    )
    assert payload["expressive_taxonomy"] == list(_expected_expressive_synonyms())
    assert _sorted_mapping_of_lists(payload["material_synonyms"]) == _sorted_mapping_of_lists(
        _expected_material_synonyms()
    )
    assert payload["material_taxonomy"] == list(_expected_material_synonyms())


def test_loader_reads_global_vocabulary_successfully() -> None:
    vocabulary = load_global_vocabulary(VOCABULARY_PATH)
    assert vocabulary.schema_version == "global_vocabulary_v1"
    assert vocabulary is load_global_vocabulary(VOCABULARY_PATH)
    assert vocabulary.audience_taxonomy
    assert vocabulary.expressive_taxonomy
    assert vocabulary.color_taxonomy
    assert vocabulary.material_taxonomy


def test_loader_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_global_vocabulary(Path("config/seo/does-not-exist.json"))


def test_loader_rejects_unknown_schema_version(tmp_path: Path) -> None:
    invalid_path = tmp_path / "global_vocabulary.invalid.json"
    invalid_path.write_text(
        json.dumps(
            {
                **_read_payload(),
                "schema_version": "global_vocabulary_v999",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        load_global_vocabulary(invalid_path)
