from __future__ import annotations

from pathlib import Path

from app.services.seo.expressive_llm.storage import CategoryExpressiveCacheKey, CategoryExpressiveStore


def test_category_expressive_store_key_is_stable_and_cache_hit(tmp_path: Path):
    store = CategoryExpressiveStore(root_dir=tmp_path)
    key = CategoryExpressiveCacheKey(
        project_id=1,
        category_id=821,
        model="openai/gpt-4.1-mini",
        prompt_version="v1",
        input_hash="abc123",
    )

    assert store.get(key=key) is None

    artifact = store.put(
        key=key,
        raw_response={"usage": {"cost": 0.1}},
        parsed={"vibes": []},
        validation={"evidence_quality": 1.0},
    )
    assert artifact.key == key.normalized()
    assert (artifact.artifact_dir / "meta.json").exists()
    assert (artifact.artifact_dir / "raw_response.json").exists()
    assert (artifact.artifact_dir / "parsed.json").exists()
    assert (artifact.artifact_dir / "validation.json").exists()

    loaded = store.get(key=key)
    assert loaded is not None
    assert loaded.key == key.normalized()
    assert loaded.parsed == {"vibes": []}
    assert loaded.validation == {"evidence_quality": 1.0}

    # Cache hit: put again without overwrite must not change the artifact path.
    artifact2 = store.put(
        key=key,
        raw_response={"usage": {"cost": 0.2}},
        parsed={"vibes": ["new"]},
        validation={"evidence_quality": 0.0},
        overwrite=False,
    )
    assert artifact2.artifact_dir == artifact.artifact_dir
    loaded2 = store.get(key=key)
    assert loaded2 is not None
    # Original content preserved because overwrite=False.
    assert loaded2.parsed == {"vibes": []}


def test_model_id_is_sanitized_in_path(tmp_path: Path):
    store = CategoryExpressiveStore(root_dir=tmp_path)
    key = CategoryExpressiveCacheKey(
        project_id=1,
        category_id=1,
        model="google/gemini-2.5-pro:latest",
        prompt_version="v1",
        input_hash="h",
    )
    artifact_dir = store._artifact_dir(key)  # intentionally testing path stability
    assert "m_google__gemini-2.5-pro_latest" in str(artifact_dir).replace("\\", "/")
