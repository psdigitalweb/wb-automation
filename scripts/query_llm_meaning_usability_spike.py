#!/usr/bin/env python3
"""Offline usability analysis for query-side buyer-meaning classes based on existing LLM labels."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LABELS_PATH = OUTPUTS_DIR / "query_llm_meaning_labels_v2.json"
REPORT_PATH = OUTPUTS_DIR / "query_llm_meaning_usable_classes_report.md"
SAMPLES_PATH = OUTPUTS_DIR / "query_llm_meaning_usable_classes_samples.json"

TARGET_CLASSES = (
    "aesthetic",
    "gift",
    "fun_meme",
    "serving_photo",
    "decor_interior",
    "event_holiday",
)
PRIMARY_CANDIDATES = ("aesthetic", "gift", "fun_meme", "serving_photo")
BOUNDARY_CLASSES = ("decor_interior", "event_holiday")

CROSS_ENTITY_PATTERNS = (
    "power bank",
    "повербанк",
    "кружк",
    "чай",
    "бокал",
    "салфет",
    "скатерт",
    "стакан",
    "стаканчик",
)
EVENT_PATTERNS = (
    "новогод",
    "пасх",
    "день рождения",
    "праздник",
    "23 февраля",
    "8 марта",
    "14 февраля",
)
GIFT_PATTERNS = (
    "в подарок",
    "подарок",
    "подароч",
    "маме",
    "папе",
    "подруге",
    "девушке",
    "жене",
    "мужу",
    "бабушке",
    "дедушке",
    "сыну",
    "дочке",
    "дочери",
    "мужчине",
    "женщине",
)


def _load_labels() -> list[dict[str, Any]]:
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


def _combined_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("profile_label_candidate") or ""),
            str(item.get("anchor_query") or ""),
            *[str(query or "") for query in item.get("representative_queries") or []],
        ]
    ).lower()


def _has_any(text: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _bucket_item(item: dict[str, Any]) -> tuple[str, list[str]]:
    class_name = item["main"]
    text = _combined_text(item)
    secondary = set(item.get("secondary") or [])
    patterns: list[str] = []

    if class_name == "aesthetic":
        if _has_any(text, ("на стен", "интерьер", "декоратив", "подставк", "держател", "крюч", "мелоч", "украшени", "сувенир")) or "decor_interior" in secondary:
            patterns.append("decor_interior masquerading as aesthetic")
            return "bad", patterns
        if _has_any(text, CROSS_ENTITY_PATTERNS):
            patterns.append("cross-entity contamination inside aesthetic")
            return "boundary", patterns
        if _has_any(text, ("эстет", "pinterest", "пинтерест", "мил", "красив", "стиль", "котик", "зайчик", "сердц")):
            patterns.append("clear aesthetic vibe")
            return "good", patterns
        patterns.append("generic beauty wording without strong buyer-meaning")
        return "boundary", patterns

    if class_name == "gift":
        if _has_any(text, CROSS_ENTITY_PATTERNS) and not _has_any(text, GIFT_PATTERNS):
            patterns.append("cross-entity gift bundle noise")
            return "bad", patterns
        if _has_any(text, EVENT_PATTERNS) or "event_holiday" in secondary:
            patterns.append("holiday/event masquerading as gift")
            return "boundary", patterns
        if _has_any(text, GIFT_PATTERNS):
            patterns.append("explicit recipient or gift motive")
            return "good", patterns
        patterns.append("gift motive not explicit enough")
        return "boundary", patterns

    if class_name == "fun_meme":
        if _has_any(text, ("power bank", "повербанк", "прикорм", "диспансер")) or _has_any(text, CROSS_ENTITY_PATTERNS):
            patterns.append("cross-entity weirdness inside fun_meme")
            return "bad", patterns
        if _has_any(text, ("мем", "надпись", "смеш", "прикол", "прикольн")):
            patterns.append("explicit meme/joke/inscription intent")
            return "good", patterns
        patterns.append("quirky form without explicit meme intent")
        return "boundary", patterns

    if class_name == "serving_photo":
        if _has_any(text, ("салфет", "однораз")) or ("event_holiday" in secondary and not _has_any(text, ("фото", "фотосесс", "завтрак", "бранч"))):
            patterns.append("classic serving or event language masquerading as serving_photo")
            return "bad", patterns
        if _has_any(text, ("фото", "фотосесс", "завтрак", "бранч", "pinterest", "пинтерест")):
            patterns.append("explicit visual presentation / photo intent")
            return "good", patterns
        if _has_any(text, ("сервиров", "для стола", "салат", "закус", "подачи")) or "aesthetic" in secondary or "functional" in secondary:
            patterns.append("classic serving language masquerading as serving_photo")
            return "boundary", patterns
        patterns.append("weak serving-photo signal")
        return "boundary", patterns

    if class_name == "decor_interior":
        if _has_any(text, ("на стен", "интерьер", "декоратив", "подставк", "держател", "крюч", "витрин", "украшени", "мелоч")):
            patterns.append("clear decor/interior/display intent")
            return "good", patterns
        if _has_any(text, ("винтаж", "стиль", "сердц", "цветами")) or "aesthetic" in secondary:
            patterns.append("decor vs aesthetic boundary")
            return "boundary", patterns
        if _has_any(text, ("для супа", "микроволнов", "обеденн", "десертн")):
            patterns.append("functional tableware slipped into decor_interior")
            return "bad", patterns
        patterns.append("likely decor but weak explicitness")
        return "boundary", patterns

    if class_name == "event_holiday":
        if _has_any(text, EVENT_PATTERNS + ("новый год", "пасха")):
            if _has_any(text, GIFT_PATTERNS) or "gift" in secondary:
                patterns.append("gift vs event_holiday overlap")
                return "boundary", patterns
            patterns.append("clear event/holiday motive")
            return "good", patterns
        if _has_any(text, CROSS_ENTITY_PATTERNS) and not _has_any(text, EVENT_PATTERNS):
            patterns.append("cross-entity holiday noise")
            return "bad", patterns
        patterns.append("event wording too weak or mixed")
        return "boundary", patterns

    return "boundary", ["unclassified fallback"]


def _verdict_for_class(class_name: str, counts: Counter[str]) -> str:
    total = max(1, sum(counts.values()))
    good_rate = counts.get("good", 0) / total
    bad_rate = counts.get("bad", 0) / total
    boundary_rate = counts.get("boundary", 0) / total

    if class_name in BOUNDARY_CLASSES:
        if good_rate >= 0.65 and bad_rate <= 0.1:
            return "usable"
        if good_rate >= 0.45 and bad_rate <= 0.2:
            return "usable_with_guardrails"
        return "not_usable_yet"

    if class_name == "aesthetic":
        if good_rate >= 0.8 and bad_rate <= 0.08 and boundary_rate <= 0.2:
            return "usable"
        if good_rate >= 0.55 and bad_rate <= 0.2:
            return "usable_with_guardrails"
        return "not_usable_yet"

    if class_name == "serving_photo":
        if good_rate >= 0.55 and bad_rate <= 0.12 and boundary_rate <= 0.25:
            return "usable"
        if good_rate >= 0.35 and bad_rate <= 0.2 and boundary_rate <= 0.5:
            return "usable_with_guardrails"
        return "not_usable_yet"

    if good_rate >= 0.65 and bad_rate <= 0.12:
        return "usable"
    if good_rate >= 0.4 and bad_rate <= 0.2:
        return "usable_with_guardrails"
    return "not_usable_yet"


def _sample_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (-float(item["confidence"]), item.get("profile_label_candidate") or "", item["cluster_key"])


def main() -> int:
    labels = _load_labels()
    analysis: dict[str, Any] = {
        "source_labels": str(LABELS_PATH),
        "classes": {},
        "confusion_pairs": Counter(),
        "recurrent_failure_patterns": defaultdict(Counter),
    }
    report_lines = [
        "# Query LLM Meaning Usable Classes Report",
        "",
        "## Summary",
        "",
        f"- source_labels: `{LABELS_PATH.name}`",
        f"- analyzed_classes: `{', '.join(TARGET_CLASSES)}`",
        "",
    ]

    for item in labels:
        for secondary in item.get("secondary") or []:
            pair = tuple(sorted((item["main"], secondary)))
            analysis["confusion_pairs"][f"{pair[0]} <-> {pair[1]}"] += 1

    for class_name in TARGET_CLASSES:
        items = [item for item in labels if item["main"] == class_name]
        confidences = [float(item["confidence"]) for item in items]
        bucketed: dict[str, list[dict[str, Any]]] = {"good": [], "boundary": [], "bad": []}

        for item in items:
            bucket, patterns = _bucket_item(item)
            enriched = {
                **item,
                "bucket": bucket,
                "heuristic_patterns": patterns,
            }
            bucketed[bucket].append(enriched)
            for pattern in patterns:
                analysis["recurrent_failure_patterns"][class_name][pattern] += 1

        for bucket_name in bucketed:
            bucketed[bucket_name] = sorted(bucketed[bucket_name], key=_sample_sort_key)[:20]

        counts = Counter(entry["bucket"] for entry in [*bucketed["good"], *bucketed["boundary"], *bucketed["bad"]])
        counts["good"] = len([item for item in labels if item["main"] == class_name and _bucket_item(item)[0] == "good"])
        counts["boundary"] = len([item for item in labels if item["main"] == class_name and _bucket_item(item)[0] == "boundary"])
        counts["bad"] = len([item for item in labels if item["main"] == class_name and _bucket_item(item)[0] == "bad"])
        verdict = _verdict_for_class(class_name, counts)

        analysis["classes"][class_name] = {
            "total_count": len(items),
            "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "median_confidence": round(statistics.median(confidences), 4) if confidences else 0.0,
            "good_count": counts["good"],
            "boundary_count": counts["boundary"],
            "bad_count": counts["bad"],
            "verdict": verdict,
            "good_examples": bucketed["good"],
            "boundary_examples": bucketed["boundary"],
            "bad_examples": bucketed["bad"],
        }

        report_lines.extend(
            [
                f"- {class_name}: `{verdict}`",
                "",
                f"## {class_name}",
                "",
                f"- total_count: `{len(items)}`",
                f"- avg_confidence: `{analysis['classes'][class_name]['avg_confidence']}`",
                f"- median_confidence: `{analysis['classes'][class_name]['median_confidence']}`",
                f"- good_examples_count: `{counts['good']}`",
                f"- boundary_examples_count: `{counts['boundary']}`",
                f"- obvious_bad_examples_count: `{counts['bad']}`",
                f"- verdict: `{verdict}`",
                "",
                "### Good examples",
                "",
            ]
        )
        for entry in bucketed["good"] or []:
            report_lines.append(
                f"- `{entry['confidence']:.4f}` | {entry['profile_label_candidate'] or '-'} | anchor: {entry['anchor_query'] or '-'} | {', '.join(entry['heuristic_patterns'])}"
            )
        if not bucketed["good"]:
            report_lines.append("- none")
        report_lines.extend(["", "### Boundary examples", ""])
        for entry in bucketed["boundary"] or []:
            report_lines.append(
                f"- `{entry['confidence']:.4f}` | {entry['profile_label_candidate'] or '-'} | anchor: {entry['anchor_query'] or '-'} | {', '.join(entry['heuristic_patterns'])}"
            )
        if not bucketed["boundary"]:
            report_lines.append("- none")
        report_lines.extend(["", "### Bad examples", ""])
        for entry in bucketed["bad"] or []:
            report_lines.append(
                f"- `{entry['confidence']:.4f}` | {entry['profile_label_candidate'] or '-'} | anchor: {entry['anchor_query'] or '-'} | {', '.join(entry['heuristic_patterns'])}"
            )
        if not bucketed["bad"]:
            report_lines.append("- none")
        report_lines.append("")

    report_lines.extend(["## Recurrent failure patterns", ""])
    for class_name in TARGET_CLASSES:
        report_lines.extend([f"### {class_name}", ""])
        patterns = analysis["recurrent_failure_patterns"][class_name].most_common(6)
        for pattern, count in patterns:
            report_lines.append(f"- {pattern}: `{count}`")
        if not patterns:
            report_lines.append("- none")
        report_lines.append("")

    report_lines.extend(["## Class confusion", ""])
    for pair, count in analysis["confusion_pairs"].most_common(12):
        report_lines.append(f"- {pair}: `{count}`")
    report_lines.extend(
        [
            "",
            "## Final recommendation",
            "",
            "- Buyer-meaning classes to consider next: `aesthetic`, `gift`, `fun_meme` only with guardrails; `serving_photo` not yet clean enough.",
            "- Boundary / exclusion classes to keep separately: `decor_interior`, `event_holiday`.",
            "- Candidate guardrails for a next step: explicit decor-wall filter for `aesthetic`; holiday-vs-gift split for `gift`; cross-entity weirdness filter for `fun_meme`; explicit photo/brunch/vibe requirement for `serving_photo`.",
        ]
    )

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(report_lines).strip() + "\n"
    REPORT_PATH.write_text(report_text, encoding="utf-8")

    serializable = {
        "source_labels": analysis["source_labels"],
        "classes": analysis["classes"],
        "confusion_pairs": dict(analysis["confusion_pairs"]),
        "recurrent_failure_patterns": {
            class_name: dict(counter)
            for class_name, counter in analysis["recurrent_failure_patterns"].items()
        },
    }
    SAMPLES_PATH.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(REPORT_PATH), "samples_path": str(SAMPLES_PATH)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
