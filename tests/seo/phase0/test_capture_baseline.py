from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.phase0.capture_baseline import _build_manifest, _merge_reference_skus


def test_merge_reference_skus_preserves_seed_order_and_uniqueness() -> None:
    result = _merge_reference_skus((10, 20), (20, 30, 40), limit=4)
    assert result == [10, 20, 30, 40]


def test_merge_reference_skus_honors_limit() -> None:
    result = _merge_reference_skus((1, 2), (3, 4, 5), limit=3)
    assert result == [1, 2, 3]


def test_build_manifest_uses_eval_accuracy_and_ids() -> None:
    manifest = _build_manifest(
        project_id=1,
        category_id=812,
        reference_sku_nm_ids=[101, 202],
        reference_query_ids=[11, 22, 33],
        eval_summary={
            "metrics": {"accuracy": 0.78123},
            "matcher_run_ids": [77, 88],
        },
    )
    assert manifest["project_id"] == 1
    assert manifest["category_id"] == 812
    assert manifest["reference_sku_nm_ids"] == [101, 202]
    assert manifest["reference_query_ids"] == [11, 22, 33]
    assert manifest["matcher_runs_referenced"] == [77, 88]
    assert manifest["eval_accuracy"] == 0.7812
    assert manifest["baseline_git_sha"]
    assert manifest["captured_at"]
