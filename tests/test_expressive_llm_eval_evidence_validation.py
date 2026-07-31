def test_evidence_validation_marks_missing_span_as_hallucination():
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.expressive_llm_eval import Vibe, _validate_vibes

    vibes = [
        Vibe(label="aesthetic", label_raw="aesthetic", confidence=0.9, evidence_spans=["not present"], notes=""),
        Vibe(label="giftable", label_raw="giftable", confidence=0.5, evidence_spans=["Present"], notes=""),
    ]
    result = _validate_vibes(vibes=vibes, evidence_text="This text has Present span.")
    items = result["vibes"]
    assert items[0]["hallucinated"] is True
    assert items[0]["evidence_valid"] is False
    assert items[1]["hallucinated"] is False
    assert items[1]["evidence_valid"] is True


def test_evidence_validation_marks_missing_evidence_list_as_hallucination():
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.expressive_llm_eval import Vibe, _validate_vibes

    vibes = [
        Vibe(label="other", label_raw="", confidence=0.2, evidence_spans=[], notes=""),
    ]
    result = _validate_vibes(vibes=vibes, evidence_text="any")
    items = result["vibes"]
    assert items[0]["hallucinated"] is True
    assert items[0]["evidence_valid"] is False
