#!/usr/bin/env python3
"""Standalone benchmark for buyer-meaning semantic retrieval."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DEFAULT_VALIDATION_PATH = OUTPUTS_DIR / "multi_category_buyer_meaning_validation.json"
DEFAULT_GOLDSET_PATH = OUTPUTS_DIR / "buyer_meaning_benchmark_goldset_template.json"
DEFAULT_REPORT_PATH = OUTPUTS_DIR / "buyer_meaning_benchmark_report.md"
DEFAULT_OUTPUT_PATH = OUTPUTS_DIR / "buyer_meaning_benchmark.json"
_STOPWORDS = {
    "для",
    "с",
    "со",
    "и",
    "в",
    "во",
    "на",
    "по",
    "под",
    "от",
    "из",
    "к",
    "ко",
    "у",
    "без",
    "а",
    "но",
    "или",
    "же",
    "ли",
}
_CATEGORY_MOTIFS: dict[str, dict[str, tuple[str, ...]]] = {
    "plates": {
        "pinterest_aesthetic": ("pinterest", "эстет", "красив", "стиль"),
        "cat_cute": ("котик", "кот", "кошк", "ушк", "зайч"),
        "inscription_meme": ("надпис", "прикол", "мем"),
        "soup_deep": ("суп", "глубок", "супов"),
        "serving": ("сервиров", "закуск", "подач"),
    },
    "cups": {
        "mug_aesthetic": ("pinterest", "эстет", "красив", "vibe"),
        "inscription_meme": ("надпис", "прикол", "мем"),
        "gift": ("подар", "подарочн"),
        "spoon": ("ложк", "стич"),
    },
    "notebooks": {
        "notebook_aesthetic": ("эстет", "красив", "pinterest"),
        "cat_cute": ("котик", "кот", "cute"),
        "writing_expression": ("пиши", "запис", "чернил"),
        "ring_notebook": ("кольц", "обложк"),
    },
    "lunchboxes": {
        "cute": ("мил", "красив", "mood", "heartbreaker"),
        "functional": ("микровол", "гермет", "контейнер", "отделен", "ед"),
    },
}


def _normalize(text: str) -> str:
    value = str(text or "").lower().replace("ё", "е")
    value = re.sub(r"[\"'`«»“”„]", " ", value)
    value = re.sub(r"[^0-9a-zа-я\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _light_token(token: str) -> str:
    value = _normalize(token)
    if len(value) <= 3:
        return value
    for suffix in ("ыми", "ими", "ого", "ему", "ому", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ей", "ую", "юю"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    for suffix in ("ами", "ями", "ов", "ев", "ей"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    if value.endswith(("ы", "и", "а", "я")) and len(value) >= 5:
        return value[:-1]
    return value


def _content_tokens(text: str) -> set[str]:
    return {
        _light_token(token)
        for token in _normalize(text).split()
        if token and token not in _STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def _contains_soft_match(candidate: str, gold: str) -> bool:
    candidate_norm = _normalize(candidate)
    gold_norm = _normalize(gold)
    if len(gold_norm) < 6:
        return False
    return gold_norm in candidate_norm or candidate_norm in gold_norm


def _query_matches(candidate: str, gold: str) -> bool:
    candidate_norm = _normalize(candidate)
    gold_norm = _normalize(gold)
    if not candidate_norm or not gold_norm:
        return False
    if candidate_norm == gold_norm:
        return True
    candidate_tokens = _content_tokens(candidate)
    gold_tokens = _content_tokens(gold)
    if candidate_tokens and candidate_tokens == gold_tokens:
        return True
    overlap = _jaccard(candidate_tokens, gold_tokens)
    if overlap >= 0.8:
        return True
    if overlap >= 0.6 and min(len(candidate_tokens), len(gold_tokens)) >= 2:
        return True
    return _contains_soft_match(candidate, gold)


def _query_match_level_v1(candidate: str, gold: str) -> str:
    return "pattern" if _query_matches(candidate, gold) else "none"


def _query_motifs(text: str, *, category_slug: str) -> set[str]:
    normalized = _normalize(text)
    category_rules = _CATEGORY_MOTIFS.get(category_slug, {})
    matched: set[str] = set()
    for bucket, patterns in category_rules.items():
        if any(pattern in normalized for pattern in patterns):
            matched.add(bucket)
    return matched


def _exact_match(candidate: str, gold: str) -> bool:
    return bool(_normalize(candidate) and _normalize(candidate) == _normalize(gold))


def _pattern_match(candidate: str, gold: str) -> bool:
    candidate_norm = _normalize(candidate)
    gold_norm = _normalize(gold)
    if not candidate_norm or not gold_norm:
        return False
    if candidate_norm == gold_norm:
        return True
    candidate_tokens = _content_tokens(candidate)
    gold_tokens = _content_tokens(gold)
    if candidate_tokens and candidate_tokens == gold_tokens:
        return True
    overlap = _jaccard(candidate_tokens, gold_tokens)
    if overlap >= 0.8:
        return True
    if overlap >= 0.6 and min(len(candidate_tokens), len(gold_tokens)) >= 2:
        return True
    return _contains_soft_match(candidate, gold)


def _family_match(candidate: str, gold: str, *, category_slug: str) -> bool:
    candidate_tokens = _content_tokens(candidate)
    gold_tokens = _content_tokens(gold)
    overlap = _jaccard(candidate_tokens, gold_tokens)
    candidate_motifs = _query_motifs(candidate, category_slug=category_slug)
    gold_motifs = _query_motifs(gold, category_slug=category_slug)
    shared_motifs = candidate_motifs.intersection(gold_motifs)
    if not shared_motifs:
        return False
    specific_motifs = {motif for motif in shared_motifs if motif not in {"pinterest_aesthetic", "mug_aesthetic", "notebook_aesthetic"}}
    if specific_motifs and overlap >= 0.15:
        return True
    if shared_motifs and overlap >= 0.34:
        return True
    return False


def _query_match_level_v2(candidate: str, gold: str, *, category_slug: str) -> str:
    if _exact_match(candidate, gold):
        return "exact"
    if _pattern_match(candidate, gold):
        return "pattern"
    if _family_match(candidate, gold, category_slug=category_slug):
        return "family"
    return "none"


def _compactness_bonus(final_query_count: int) -> float:
    if 6 <= final_query_count <= 16:
        return 0.2
    if 4 <= final_query_count <= 20:
        return 0.1
    if final_query_count <= 28:
        return 0.05
    return 0.0


def _family_diversity_bonus(family_count: int) -> float:
    return min(0.2, max(0.0, family_count) * 0.03)


def _benchmark_verdict(
    *,
    good_hits_count: int,
    recall_like_good_coverage: float,
    bad_hits_count: int,
    bad_leak_rate: float,
    retrieval_quality: str,
) -> str:
    if retrieval_quality == "functional_fallback":
        return "weak"
    if good_hits_count >= 3 and recall_like_good_coverage >= 0.5 and bad_hits_count <= 1 and bad_leak_rate <= 0.2:
        return "strong"
    if good_hits_count >= 2 and recall_like_good_coverage >= 0.34 and bad_leak_rate <= 0.5:
        return "acceptable"
    return "weak"


def _benchmark_verdict_v2(
    *,
    semantic_good_hits: int,
    semantic_good_coverage: float,
    semantic_bad_hits: int,
    semantic_bad_leak_rate: float,
    retrieval_quality: str,
) -> str:
    if retrieval_quality == "functional_fallback":
        return "weak"
    if semantic_good_hits >= 3 and semantic_good_coverage >= 0.5 and semantic_bad_hits <= 1 and semantic_bad_leak_rate <= 0.2:
        return "strong"
    if semantic_good_hits >= 2 and semantic_good_coverage >= 0.34 and semantic_bad_leak_rate <= 0.5:
        return "acceptable"
    return "weak"


def _sku_score(
    *,
    good_hits_count: int,
    precision_against_gold_good: float,
    recall_like_good_coverage: float,
    bad_hits_count: int,
    bad_leak_rate: float,
    final_query_count: int,
    family_count: int,
    retrieval_quality: str,
) -> float:
    score = 0.0
    score += good_hits_count * 1.0
    score += precision_against_gold_good * 1.5
    score += recall_like_good_coverage * 2.0
    score += _compactness_bonus(final_query_count)
    score += _family_diversity_bonus(family_count)
    score -= bad_hits_count * 1.0
    score -= bad_leak_rate * 2.0
    if retrieval_quality == "functional_fallback":
        score -= 1.0
    return round(score, 4)


def _category_verdict(summary: dict[str, Any]) -> str:
    strong_or_acceptable = summary["strong_count"] + summary["acceptable_count"]
    if (
        summary["avg_good_hit_rate"] >= 0.5
        and summary["avg_bad_leak_rate"] <= 0.2
        and summary["weak_count"] == 0
        and strong_or_acceptable == summary["sku_count"]
    ):
        return "buyer_meaning_ready"
    if summary["weak_count"] >= max(1, strong_or_acceptable):
        return "functional_fallback"
    return "mixed"


def _category_verdict_v2(summary: dict[str, Any]) -> str:
    strong_or_acceptable = summary["strong_count_v2"] + summary["acceptable_count_v2"]
    if summary["avg_semantic_good_coverage"] >= 0.55 and summary["avg_semantic_bad_leak_rate"] <= 0.2 and summary["weak_count_v2"] == 0:
        return "mixed but promising"
    if strong_or_acceptable >= 1 and summary["avg_semantic_good_coverage"] >= 0.35 and summary["avg_semantic_bad_leak_rate"] <= 0.35:
        return "not stable enough"
    return "weak / functional fallback"


def _benchmark_confidence(*, good_gold_count: int, bad_gold_count: int, semantic_matches: int) -> str:
    total = good_gold_count + bad_gold_count
    if total >= 8 and semantic_matches >= 3:
        return "high"
    if total >= 5 and semantic_matches >= 2:
        return "medium"
    return "low"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_validation_index(validation_payload: dict[str, Any]) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
    index: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for category in validation_payload.get("categories", []):
        for sku in category.get("skus", []):
            index[int(sku["nm_id"])] = (category, sku)
    return index


def _run_benchmark(*, validation_payload: dict[str, Any], goldset: list[dict[str, Any]]) -> dict[str, Any]:
    validation_index = _build_validation_index(validation_payload)
    results: list[dict[str, Any]] = []
    category_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for gold_entry in goldset:
        nm_id = int(gold_entry["nm_id"])
        if nm_id not in validation_index:
            continue
        category, sku = validation_index[nm_id]
        final_queries = list(sku.get("final_queries") or [])
        good_gold = list(gold_entry.get("good_queries") or [])
        bad_gold = list(gold_entry.get("bad_queries") or [])

        matched_good_v1: list[str] = []
        matched_bad_v1: list[str] = []
        matched_final_good_queries_v1: list[str] = []
        matched_final_bad_queries_v1: list[str] = []
        for gold_query in good_gold:
            if any(_query_match_level_v1(candidate, gold_query) != "none" for candidate in final_queries):
                matched_good_v1.append(gold_query)
        for gold_query in bad_gold:
            if any(_query_match_level_v1(candidate, gold_query) != "none" for candidate in final_queries):
                matched_bad_v1.append(gold_query)
        for candidate in final_queries:
            if any(_query_match_level_v1(candidate, gold_query) != "none" for gold_query in good_gold):
                matched_final_good_queries_v1.append(candidate)
            if any(_query_match_level_v1(candidate, gold_query) != "none" for gold_query in bad_gold):
                matched_final_bad_queries_v1.append(candidate)

        good_level_counts = {"exact": 0, "pattern": 0, "family": 0}
        bad_level_counts = {"exact": 0, "pattern": 0, "family": 0}
        matched_good_v2: list[str] = []
        matched_bad_v2: list[str] = []
        matched_final_good_queries_v2: list[str] = []
        matched_final_bad_queries_v2: list[str] = []

        for gold_query in good_gold:
            best_level = "none"
            for candidate in final_queries:
                level = _query_match_level_v2(candidate, gold_query, category_slug=gold_entry["category_slug"])
                if level == "exact":
                    best_level = "exact"
                    break
                if level == "pattern" and best_level != "exact":
                    best_level = "pattern"
                elif level == "family" and best_level not in {"exact", "pattern"}:
                    best_level = "family"
            if best_level != "none":
                matched_good_v2.append(gold_query)
                good_level_counts[best_level] += 1

        for gold_query in bad_gold:
            best_level = "none"
            for candidate in final_queries:
                level = _query_match_level_v2(candidate, gold_query, category_slug=gold_entry["category_slug"])
                if level == "exact":
                    best_level = "exact"
                    break
                if level == "pattern" and best_level != "exact":
                    best_level = "pattern"
                elif level == "family" and best_level not in {"exact", "pattern"}:
                    best_level = "family"
            if best_level != "none":
                matched_bad_v2.append(gold_query)
                bad_level_counts[best_level] += 1

        for candidate in final_queries:
            best_good = "none"
            for gold_query in good_gold:
                level = _query_match_level_v2(candidate, gold_query, category_slug=gold_entry["category_slug"])
                if level == "exact":
                    best_good = "exact"
                    break
                if level == "pattern" and best_good != "exact":
                    best_good = "pattern"
                elif level == "family" and best_good not in {"exact", "pattern"}:
                    best_good = "family"
            if best_good != "none":
                matched_final_good_queries_v2.append(candidate)

            best_bad = "none"
            for gold_query in bad_gold:
                level = _query_match_level_v2(candidate, gold_query, category_slug=gold_entry["category_slug"])
                if level == "exact":
                    best_bad = "exact"
                    break
                if level == "pattern" and best_bad != "exact":
                    best_bad = "pattern"
                elif level == "family" and best_bad not in {"exact", "pattern"}:
                    best_bad = "family"
            if best_bad != "none":
                matched_final_bad_queries_v2.append(candidate)

        good_hits_count = len(matched_good_v1)
        bad_hits_count = len(matched_bad_v1)
        final_query_count = len(final_queries)
        family_count = int(sku.get("family_group_count") or 0)
        precision_against_gold_good = round(len(set(matched_final_good_queries_v1)) / final_query_count, 4) if final_query_count else 0.0
        recall_like_good_coverage = round(good_hits_count / len(good_gold), 4) if good_gold else 0.0
        bad_leak_rate = round(bad_hits_count / len(bad_gold), 4) if bad_gold else 0.0
        retrieval_quality = str(sku.get("retrieval_quality") or "mixed")
        human_verdict = str((sku.get("manual_verdict") or {}).get("verdict") or "")
        benchmark_score_v1 = _sku_score(
            good_hits_count=good_hits_count,
            precision_against_gold_good=precision_against_gold_good,
            recall_like_good_coverage=recall_like_good_coverage,
            bad_hits_count=bad_hits_count,
            bad_leak_rate=bad_leak_rate,
            final_query_count=final_query_count,
            family_count=family_count,
            retrieval_quality=retrieval_quality,
        )
        benchmark_verdict_v1 = _benchmark_verdict(
            good_hits_count=good_hits_count,
            recall_like_good_coverage=recall_like_good_coverage,
            bad_hits_count=bad_hits_count,
            bad_leak_rate=bad_leak_rate,
            retrieval_quality=retrieval_quality,
        )

        semantic_good_hits = sum(good_level_counts.values())
        semantic_bad_hits = sum(bad_level_counts.values())
        semantic_good_coverage = round(semantic_good_hits / len(good_gold), 4) if good_gold else 0.0
        semantic_bad_leak_rate = round(semantic_bad_hits / len(bad_gold), 4) if bad_gold else 0.0
        precision_against_gold_good_v2 = round(len(set(matched_final_good_queries_v2)) / final_query_count, 4) if final_query_count else 0.0
        benchmark_score_v2 = _sku_score(
            good_hits_count=semantic_good_hits,
            precision_against_gold_good=precision_against_gold_good_v2,
            recall_like_good_coverage=semantic_good_coverage,
            bad_hits_count=semantic_bad_hits,
            bad_leak_rate=semantic_bad_leak_rate,
            final_query_count=final_query_count,
            family_count=family_count,
            retrieval_quality=retrieval_quality,
        )
        benchmark_verdict_v2 = _benchmark_verdict_v2(
            semantic_good_hits=semantic_good_hits,
            semantic_good_coverage=semantic_good_coverage,
            semantic_bad_hits=semantic_bad_hits,
            semantic_bad_leak_rate=semantic_bad_leak_rate,
            retrieval_quality=retrieval_quality,
        )
        benchmark_confidence = _benchmark_confidence(
            good_gold_count=len(good_gold),
            bad_gold_count=len(bad_gold),
            semantic_matches=semantic_good_hits + semantic_bad_hits,
        )

        result = {
            "version": "v2",
            "category_slug": gold_entry["category_slug"],
            "category_id": int(gold_entry["category_id"]),
            "category_display_name": category.get("display_name"),
            "nm_id": nm_id,
            "title": sku.get("title") or gold_entry.get("title") or "",
            "final_query_count": final_query_count,
            "family_count": family_count,
            "retrieval_quality": retrieval_quality,
            "human_verdict": human_verdict,
            "good_gold_queries": good_gold,
            "bad_gold_queries": bad_gold,
            "matched_good_queries_v1": matched_good_v1,
            "matched_bad_queries_v1": matched_bad_v1,
            "matched_final_good_queries_v1": sorted(set(matched_final_good_queries_v1)),
            "matched_final_bad_queries_v1": sorted(set(matched_final_bad_queries_v1)),
            "good_hits_count_v1": good_hits_count,
            "bad_hits_count_v1": bad_hits_count,
            "precision_against_gold_good_v1": precision_against_gold_good,
            "recall_like_good_coverage_v1": recall_like_good_coverage,
            "bad_leak_rate_v1": bad_leak_rate,
            "benchmark_score_v1": benchmark_score_v1,
            "benchmark_verdict_v1": benchmark_verdict_v1,
            "matched_good_queries_v2": matched_good_v2,
            "matched_bad_queries_v2": matched_bad_v2,
            "matched_final_good_queries_v2": sorted(set(matched_final_good_queries_v2)),
            "matched_final_bad_queries_v2": sorted(set(matched_final_bad_queries_v2)),
            "good_hits_exact": good_level_counts["exact"],
            "good_hits_pattern": good_level_counts["pattern"],
            "good_hits_family": good_level_counts["family"],
            "bad_hits_exact": bad_level_counts["exact"],
            "bad_hits_pattern": bad_level_counts["pattern"],
            "bad_hits_family": bad_level_counts["family"],
            "semantic_good_coverage": semantic_good_coverage,
            "semantic_bad_leak_rate": semantic_bad_leak_rate,
            "precision_against_gold_good_v2": precision_against_gold_good_v2,
            "benchmark_score_v2": benchmark_score_v2,
            "benchmark_verdict_v2": benchmark_verdict_v2,
            "benchmark_confidence": benchmark_confidence,
            "final_queries": final_queries,
            "notes": str(gold_entry.get("notes") or ""),
            "human_vs_benchmark_match": human_verdict in {"looks right", "mixed", "mostly wrong"}
            and (
                (human_verdict == "looks right" and benchmark_verdict_v2 in {"strong", "acceptable"})
                or (human_verdict == "mixed" and benchmark_verdict_v2 == "acceptable")
                or (human_verdict == "mostly wrong" and benchmark_verdict_v2 == "weak")
            ),
        }
        results.append(result)
        category_buckets[str(gold_entry["category_slug"])].append(result)

    per_category: list[dict[str, Any]] = []
    for category_slug, items in category_buckets.items():
        avg_good_hit_rate = round(sum(item["recall_like_good_coverage_v1"] for item in items) / len(items), 4)
        avg_bad_leak_rate = round(sum(item["bad_leak_rate_v1"] for item in items) / len(items), 4)
        avg_semantic_good_coverage = round(sum(item["semantic_good_coverage"] for item in items) / len(items), 4)
        avg_semantic_bad_leak_rate = round(sum(item["semantic_bad_leak_rate"] for item in items) / len(items), 4)
        avg_final_query_count = round(sum(item["final_query_count"] for item in items) / len(items), 2)
        avg_family_count = round(sum(item["family_count"] for item in items) / len(items), 2)
        strong_count = sum(1 for item in items if item["benchmark_verdict_v1"] == "strong")
        acceptable_count = sum(1 for item in items if item["benchmark_verdict_v1"] == "acceptable")
        weak_count = sum(1 for item in items if item["benchmark_verdict_v1"] == "weak")
        strong_count_v2 = sum(1 for item in items if item["benchmark_verdict_v2"] == "strong")
        acceptable_count_v2 = sum(1 for item in items if item["benchmark_verdict_v2"] == "acceptable")
        weak_count_v2 = sum(1 for item in items if item["benchmark_verdict_v2"] == "weak")
        strongest = max(items, key=lambda item: item["benchmark_score_v2"])
        weakest = min(items, key=lambda item: item["benchmark_score_v2"])
        summary = {
            "category_slug": category_slug,
            "category_id": items[0]["category_id"],
            "category_display_name": items[0]["category_display_name"],
            "sku_count": len(items),
            "avg_good_hit_rate": avg_good_hit_rate,
            "avg_bad_leak_rate": avg_bad_leak_rate,
            "avg_semantic_good_coverage": avg_semantic_good_coverage,
            "avg_semantic_bad_leak_rate": avg_semantic_bad_leak_rate,
            "avg_final_query_count": avg_final_query_count,
            "avg_family_count": avg_family_count,
            "strong_count": strong_count,
            "acceptable_count": acceptable_count,
            "weak_count": weak_count,
            "strong_count_v2": strong_count_v2,
            "acceptable_count_v2": acceptable_count_v2,
            "weak_count_v2": weak_count_v2,
            "strongest_sku": {"nm_id": strongest["nm_id"], "title": strongest["title"], "score": strongest["benchmark_score_v2"]},
            "weakest_sku": {"nm_id": weakest["nm_id"], "title": weakest["title"], "score": weakest["benchmark_score_v2"]},
        }
        summary["category_verdict_v1"] = _category_verdict(summary)
        summary["category_verdict_v2"] = _category_verdict_v2(summary)
        per_category.append(summary)

    per_category.sort(key=lambda item: (item["category_id"], item["category_slug"]))
    dataset_coverage = {
        "goldset_entries_total": len(goldset),
        "goldset_entries_covered": len(results),
        "category_count_covered": len(per_category),
        "categories": [item["category_slug"] for item in per_category],
    }

    overall = {
        "old_category_verdicts": {item["category_slug"]: item["category_verdict_v1"] for item in per_category},
        "new_category_verdicts": {item["category_slug"]: item["category_verdict_v2"] for item in per_category},
        "strong_categories_v2": [item["category_slug"] for item in per_category if item["category_verdict_v2"] == "mixed but promising"],
        "mixed_categories_v2": [item["category_slug"] for item in per_category if item["category_verdict_v2"] == "not stable enough"],
        "weak_categories_v2": [item["category_slug"] for item in per_category if item["category_verdict_v2"] == "weak / functional fallback"],
        "human_benchmark_agreement_rate": round(
            sum(1 for item in results if item["human_vs_benchmark_match"]) / len(results),
            4,
        )
        if results
        else 0.0,
    }
    return {
        "version": "v2",
        "dataset_coverage": dataset_coverage,
        "per_sku": results,
        "per_category": per_category,
        "overall": overall,
    }


def _write_report(*, path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Buyer-Meaning Benchmark v2",
        "",
        f"- version: `{payload.get('version', 'v2')}`",
        "",
        "## Benchmark v2 summary",
        "",
        "## Dataset coverage",
        "",
        f"- goldset_entries_total: `{payload['dataset_coverage']['goldset_entries_total']}`",
        f"- goldset_entries_covered: `{payload['dataset_coverage']['goldset_entries_covered']}`",
        f"- category_count_covered: `{payload['dataset_coverage']['category_count_covered']}`",
        f"- categories: `{payload['dataset_coverage']['categories']}`",
        "",
        "## Matching levels explained",
        "",
        "- `exact`: exact / normalized string match",
        "- `pattern`: token-pattern match, word-order / singular-plural / weak-modifier variants",
        "- `family`: lightweight motif-family match without LLM",
        "",
        "## Per-SKU benchmark",
        "",
    ]
    for item in payload["per_sku"]:
        lines.extend(
            [
                f"### SKU `{item['nm_id']}`",
                "",
                f"- title: {item['title']}",
                f"- category: `{item['category_slug']}`",
                f"- final_query_count: `{item['final_query_count']}`",
                f"- family_count: `{item['family_count']}`",
                f"- retrieval_quality: `{item['retrieval_quality']}`",
                f"- human_verdict: `{item['human_verdict']}`",
                f"- benchmark_v1_verdict: `{item['benchmark_verdict_v1']}`",
                f"- benchmark_v2_verdict: `{item['benchmark_verdict_v2']}`",
                f"- benchmark_v2_score: `{item['benchmark_score_v2']}`",
                f"- benchmark_confidence: `{item['benchmark_confidence']}`",
                f"- good_hits exact/pattern/family: `{item['good_hits_exact']} / {item['good_hits_pattern']} / {item['good_hits_family']}`",
                f"- bad_hits exact/pattern/family: `{item['bad_hits_exact']} / {item['bad_hits_pattern']} / {item['bad_hits_family']}`",
                f"- semantic_good_coverage: `{item['semantic_good_coverage']}`",
                f"- semantic_bad_leak_rate: `{item['semantic_bad_leak_rate']}`",
                f"- v1 recall_like_good_coverage: `{item['recall_like_good_coverage_v1']}`",
                f"- v1 bad_leak_rate: `{item['bad_leak_rate_v1']}`",
                f"- good_gold_queries: {item['good_gold_queries']}",
                f"- bad_gold_queries: {item['bad_gold_queries']}",
                f"- matched_good_queries_v2: {item['matched_good_queries_v2']}",
                f"- matched_bad_queries_v2: {item['matched_bad_queries_v2']}",
                f"- final_queries: {item['final_queries']}",
                "",
            ]
        )

    lines.extend(["## Per-category benchmark", ""])
    for item in payload["per_category"]:
        lines.extend(
            [
                f"### {item['category_display_name']}",
                "",
                f"- sku_count: `{item['sku_count']}`",
                f"- old_category_verdict: `{item['category_verdict_v1']}`",
                f"- new_category_verdict: `{item['category_verdict_v2']}`",
                f"- avg_good_hit_rate_v1: `{item['avg_good_hit_rate']}`",
                f"- avg_bad_leak_rate_v1: `{item['avg_bad_leak_rate']}`",
                f"- avg_semantic_good_coverage_v2: `{item['avg_semantic_good_coverage']}`",
                f"- avg_semantic_bad_leak_rate_v2: `{item['avg_semantic_bad_leak_rate']}`",
                f"- avg_final_query_count: `{item['avg_final_query_count']}`",
                f"- avg_family_count: `{item['avg_family_count']}`",
                f"- v1 strong / acceptable / weak: `{item['strong_count']} / {item['acceptable_count']} / {item['weak_count']}`",
                f"- v2 strong / acceptable / weak: `{item['strong_count_v2']} / {item['acceptable_count_v2']} / {item['weak_count_v2']}`",
                f"- strongest_sku: `{item['strongest_sku']}`",
                f"- weakest_sku: `{item['weakest_sku']}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Final benchmark verdict",
            "",
            f"- old_category_verdicts: `{payload['overall']['old_category_verdicts']}`",
            f"- new_category_verdicts: `{payload['overall']['new_category_verdicts']}`",
            f"- strong_categories_v2: `{payload['overall']['strong_categories_v2']}`",
            f"- mixed_categories_v2: `{payload['overall']['mixed_categories_v2']}`",
            f"- weak_categories_v2: `{payload['overall']['weak_categories_v2']}`",
            f"- human_benchmark_agreement_rate: `{payload['overall']['human_benchmark_agreement_rate']}`",
            "- interpretation: v2 is less surface-harsh, but it still does not forgive leakage or category collapse.",
            "",
        ]
    )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Buyer-meaning benchmark over existing validation JSON")
    parser.add_argument("--validation-json", default=str(DEFAULT_VALIDATION_PATH))
    parser.add_argument("--goldset-json", default=str(DEFAULT_GOLDSET_PATH))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    validation_payload = _load_json(Path(args.validation_json))
    goldset = _load_json(Path(args.goldset_json))
    result = _run_benchmark(validation_payload=validation_payload, goldset=goldset)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(path=Path(args.report_md), payload=result)
    print(json.dumps({"covered_sku_count": len(result["per_sku"]), "covered_categories": result["dataset_coverage"]["categories"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
