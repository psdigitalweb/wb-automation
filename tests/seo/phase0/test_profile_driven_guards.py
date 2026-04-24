from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.seo.atoms.v1.guards import apply_query_guards, apply_sku_guards
from app.services.seo.atoms.v1.schemas import QueryAtoms, SkuAtoms
from app.services.seo.category_profile import CategoryProfile


BASELINE_DIR = Path("tests/seo/phase0/baselines/812_pre_phase0")
TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")
GUARDS_PATH = Path("src/app/services/seo/atoms/v1/guards.py")


def _profile() -> CategoryProfile:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return CategoryProfile.from_payload(
        profile_id=1,
        project_id=1,
        category_id=812,
        version="v1.812.test",
        payload=payload,
    )


def _query_atom_labels(atoms: QueryAtoms) -> dict[str, set[str]]:
    def labels(items: list[object]) -> set[str]:
        result: set[str] = set()
        for item in items:
            dump = item.model_dump(mode="json")
            result.add(f"{dump['type']}|{dump['field']}|{dump['operator']}|{dump['value']}")
        return result

    return {
        "required": labels(atoms.required_atoms),
        "preferred": labels(atoms.preferred_atoms),
        "excluded": labels(atoms.excluded_atoms),
        "negative": labels(atoms.negative_fit_atoms),
    }


def _sku_atom_labels(atoms: SkuAtoms) -> dict[str, set[str]]:
    def labels(items: list[object]) -> set[str]:
        result: set[str] = set()
        for item in items:
            dump = item.model_dump(mode="json")
            result.add(f"{dump['type']}|{dump['field']}|{dump['operator']}|{dump['value']}")
        return result

    return {
        "facts": labels(atoms.facts),
        "positive": labels(atoms.positive_atoms),
        "negative": labels(atoms.negative_fit_atoms),
    }


def _baseline_query_ids() -> list[int]:
    manifest = json.loads((BASELINE_DIR / "manifest.json").read_text(encoding="utf-8"))
    return [int(item) for item in manifest["reference_query_ids"]]


def _baseline_sku_ids() -> list[int]:
    manifest = json.loads((BASELINE_DIR / "manifest.json").read_text(encoding="utf-8"))
    return [int(item) for item in manifest["reference_sku_nm_ids"]]


def test_query_guards_read_product_type_detection_from_profile() -> None:
    guarded = apply_query_guards(
        QueryAtoms(genericness="broad"),
        ["термокружка с трубочкой"],
        profile=_profile(),
    )

    labels = _query_atom_labels(guarded)
    assert guarded.product_type == "термокружка"
    assert "compatibility|thermal|equals|True" in labels["required"]


def test_query_guards_read_required_and_excluded_atoms_from_profile() -> None:
    guarded = apply_query_guards(
        QueryAtoms(genericness="broad"),
        ["кружка без рисунка"],
        profile=_profile(),
    )

    labels = _query_atom_labels(guarded)
    assert guarded.product_type == "кружка"
    assert "exclusion|design|excludes|print" in labels["excluded"]


def test_query_guards_keep_expected_sample_results_for_812_profile() -> None:
    profile = _profile()

    thermal = apply_query_guards(QueryAtoms(genericness="broad"), ["термокружка с трубочкой"], profile=profile)
    primary = apply_query_guards(QueryAtoms(genericness="broad"), ["кружка капибара"], profile=profile)
    no_print = apply_query_guards(QueryAtoms(genericness="broad"), ["кружка без рисунка"], profile=profile)

    assert thermal.product_type == "термокружка"
    assert any(atom.field == "thermal" and atom.value is True for atom in thermal.required_atoms)
    assert primary.product_type == "кружка"
    assert no_print.product_type == "кружка"
    assert any(atom.field == "design" and atom.value == "print" for atom in no_print.excluded_atoms)


def test_sku_guards_read_characteristic_mappings_from_profile() -> None:
    guarded = apply_sku_guards(
        SkuAtoms(project_id=1, category_id=812, nm_id=1),
        evidence={
            "product": {
                "characteristics": [
                    {"name": "Объем (мл)", "value": "375"},
                    {"name": "Цвет", "value": "светло-фиолетовый"},
                    {"name": "Материал посуды", "value": "керамика"},
                    {"name": "Рисунок", "value": "капибара"},
                    {"name": "Особенности кружки", "value": "использование в СВЧ; использование в посудомоечной машине"},
                ]
            }
        },
        meaning_payload={"functional": {"product_type": "Кружки"}},
        profile=_profile(),
    )

    labels = _sku_atom_labels(guarded)
    assert "numeric|volume_ml|equals|375" in labels["facts"]
    assert "attribute|color|equals|светло-фиолетовый" in labels["facts"]
    assert "attribute|material|equals|керамика" in labels["facts"]
    assert "visual|design|equals|print" in labels["facts"]
    assert "compatibility|compatibility|equals|microwave" in labels["facts"]
    assert "compatibility|compatibility|equals|dishwasher" in labels["facts"]


def test_sku_guards_read_functional_token_mappings_from_profile() -> None:
    guarded = apply_sku_guards(
        SkuAtoms(project_id=1, category_id=812, nm_id=2),
        meaning_payload={
            "functional": {
                "product_type": "термокружка",
                "attributes": ["термокружка дорожная"],
                "use_cases": ["использование в СВЧ"],
            }
        },
        profile=_profile(),
    )

    labels = _sku_atom_labels(guarded)
    assert "compatibility|thermal|equals|True" in labels["facts"]
    assert "compatibility|compatibility|equals|microwave" in labels["facts"]


def test_no_category_literals_remain_in_guards_py() -> None:
    source = GUARDS_PATH.read_text(encoding="utf-8")
    for literal in ("термокруж", "круж", "пивн", "кофемаш", "в машину", "без крыш", "без рисун", "без принт"):
        assert literal not in source, f"{literal!r} leaked into guards.py"


@pytest.mark.parametrize("query_id", _baseline_query_ids())
def test_query_guard_baseline_reference_inputs_remain_stable(query_id: int) -> None:
    payload = json.loads((BASELINE_DIR / f"query_atoms_{query_id}.json").read_text(encoding="utf-8"))
    expected = QueryAtoms.model_validate(payload["atoms"])
    actual = apply_query_guards(QueryAtoms(), [payload["normalized_query_text"]], profile=_profile())

    assert actual.product_type == expected.product_type
    assert _query_atom_labels(actual) == _query_atom_labels(expected)


@pytest.mark.parametrize("nm_id", _baseline_sku_ids())
def test_sku_guard_baseline_reference_inputs_remain_stable(nm_id: int) -> None:
    payload = json.loads((BASELINE_DIR / f"sku_atoms_{nm_id}.json").read_text(encoding="utf-8"))
    expected = SkuAtoms.model_validate(payload["atoms"])
    actual = apply_sku_guards(
        SkuAtoms(
            project_id=expected.project_id,
            category_id=expected.category_id,
            nm_id=expected.nm_id,
            product_type=expected.product_type,
        ),
        meaning_payload=payload["meaning_payload"],
        profile=_profile(),
    )

    assert actual.product_type == expected.product_type
    assert _sku_atom_labels(actual) == _sku_atom_labels(expected)
