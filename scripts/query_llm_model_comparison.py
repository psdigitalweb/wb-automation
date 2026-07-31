#!/usr/bin/env python3
"""Offline comparison report for query-side LLM buyer-meaning classification models."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REPORT_PATH = OUTPUTS_DIR / "query_llm_model_comparison_report.md"
MODEL_FILES = {
    "gpt-4o-mini": OUTPUTS_DIR / "query_llm_meaning_labels_4o_mini.json",
    "gpt-4.1-mini": OUTPUTS_DIR / "query_llm_meaning_labels_4_1_mini.json",
    "gemini-flash": OUTPUTS_DIR / "query_llm_meaning_labels_gemini_flash.json",
}
TARGET_DIST_CLASSES = (
    "aesthetic",
    "gift",
    "fun_meme",
    "decor_interior",
    "event_holiday",
    "functional",
    "generic",
)
BUYER_CLASSES = ("aesthetic", "gift", "fun_meme")


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


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


DECOR_PATTERNS = ("на стен", "интерьер", "декоратив", "подставк", "держател", "крюч", "мелоч", "украшени", "сувенир")
EVENT_PATTERNS = ("новогод", "пасх", "день рождения", "праздник", "23 февраля", "8 марта", "14 февраля")
GIFT_PATTERNS = ("в подарок", "подарок", "подароч", "маме", "папе", "подруге", "девушке", "жене", "мужу", "бабушке", "дедушке", "сыну", "дочке", "дочери", "мужчине", "женщине")
FUN_PATTERNS = ("мем", "надпись", "смеш", "прикол", "прикольн")
FUN_BAD_PATTERNS = ("power bank", "повербанк", "прикорм", "диспансер", "стакан", "бокал")
SERVING_PATTERNS = ("сервиров", "для стола", "салат", "закус", "подачи")
SERVING_PHOTO_PATTERNS = ("фото", "фотосесс", "завтрак", "бранч", "pinterest", "пинтерест")


def _buyer_bucket(class_name: str, item: dict[str, Any]) -> str:
    text = _combined_text(item)
    secondary = set(item.get("secondary") or [])
    if class_name == "aesthetic":
        if _has_any(text, DECOR_PATTERNS) or "decor_interior" in secondary:
            return "noisy"
        if _has_any(text, ("эстет", "pinterest", "пинтерест", "мил", "красив", "стиль", "котик", "зайчик", "сердц")):
            return "clean"
        return "mixed"
    if class_name == "gift":
        if _has_any(text, ("бокал", "стакан", "чай")) and not _has_any(text, GIFT_PATTERNS):
            return "noisy"
        if _has_any(text, EVENT_PATTERNS) or "event_holiday" in secondary:
            return "mixed"
        if _has_any(text, GIFT_PATTERNS):
            return "clean"
        return "mixed"
    if class_name == "fun_meme":
        if _has_any(text, FUN_BAD_PATTERNS) or "garbage" in secondary:
            return "noisy"
        if _has_any(text, FUN_PATTERNS):
            return "clean"
        return "mixed"
    return "mixed"


def _purity_label(clean_count: int, mixed_count: int, noisy_count: int) -> str:
    total = max(1, clean_count + mixed_count + noisy_count)
    clean_rate = clean_count / total
    noisy_rate = noisy_count / total
    if clean_rate >= 0.65 and noisy_rate <= 0.15:
        return "clean"
    if clean_rate >= 0.3 and noisy_rate <= 0.35:
        return "mixed"
    return "noisy"


def _confidence_stats(items: list[dict[str, Any]]) -> tuple[float, float]:
    values = [float(item["confidence"]) for item in items]
    if not values:
        return 0.0, 0.0
    return round(sum(values) / len(values), 4), round(float(statistics.median(values)), 4)


def _confusion_examples(items: list[dict[str, Any]], *, predicate) -> list[dict[str, Any]]:
    return sorted([item for item in items if predicate(item)], key=lambda item: (-float(item["confidence"]), item["cluster_key"]))[:10]


def _manual_scores(model_name: str, buyer_summary: dict[str, dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, int]:
    coverage_quality = []
    for class_name in BUYER_CLASSES:
        summary = buyer_summary[class_name]
        count = summary["count"]
        clean_rate = summary["clean_count"] / max(1, count)
        coverage_quality.append(clean_rate * min(count, 15))
    separation_signal = sum(coverage_quality) / max(1.0, 15 * len(BUYER_CLASSES))
    if separation_signal >= 0.72:
        separation = 5
    elif separation_signal >= 0.55:
        separation = 4
    elif separation_signal >= 0.38:
        separation = 3
    elif separation_signal >= 0.22:
        separation = 2
    else:
        separation = 1

    noisy_total = sum(summary["noisy_count"] for summary in buyer_summary.values())
    garbage_count = sum(1 for item in items if item["main"] == "garbage")
    noise_burden = noisy_total + (garbage_count * 0.4)
    if noise_burden <= 8:
        noise_level = 5
    elif noise_burden <= 16:
        noise_level = 4
    elif noise_burden <= 26:
        noise_level = 3
    elif noise_burden <= 36:
        noise_level = 2
    else:
        noise_level = 1

    low_conf = sum(1 for item in items if float(item["confidence"]) < 0.8)
    genericish = sum(1 for item in items if item["main"] in {"generic", "garbage"})
    consistency_burden = low_conf + (genericish * 0.5)
    if consistency_burden <= 24:
        consistency = 5
    elif consistency_burden <= 45:
        consistency = 4
    elif consistency_burden <= 70:
        consistency = 3
    elif consistency_burden <= 95:
        consistency = 2
    else:
        consistency = 1
    return {
        "buyer_meaning_separation": min(5, separation),
        "noise_level": noise_level,
        "consistency": consistency,
    }


def _class_quality(summary: dict[str, Any]) -> float:
    count = summary["count"]
    clean_rate = summary["clean_count"] / max(1, count)
    noisy_rate = summary["noisy_count"] / max(1, count)
    return (clean_rate * min(count, 15)) - (noisy_rate * 6)


def main() -> int:
    model_data = {name: _load_json(path) for name, path in MODEL_FILES.items()}
    key_sets = {name: {item["cluster_key"] for item in items} for name, items in model_data.items()}
    shared_keys = set.intersection(*key_sets.values())
    if len(shared_keys) != len(next(iter(key_sets.values()))):
        raise RuntimeError("Model outputs do not share the same cluster sample")

    by_model_key = {
        name: {item["cluster_key"]: item for item in items}
        for name, items in model_data.items()
    }

    report_lines = [
        "# Query LLM Model Comparison Report",
        "",
        "## Distribution comparison",
        "",
    ]

    model_summaries: dict[str, Any] = {}
    for model_name, items in model_data.items():
        counts = Counter(item["main"] for item in items)
        report_lines.extend([f"### {model_name}", "", "| class | count |", "| --- | ---: |"])
        for class_name in TARGET_DIST_CLASSES:
            report_lines.append(f"| {class_name} | {counts.get(class_name, 0)} |")
        report_lines.append("")

        buyer_summary: dict[str, dict[str, Any]] = {}
        for class_name in BUYER_CLASSES:
            class_items = [item for item in items if item["main"] == class_name]
            bucketed = {"clean": [], "mixed": [], "noisy": []}
            for item in class_items:
                bucketed[_buyer_bucket(class_name, item)].append(item)
            for bucket_name in bucketed:
                bucketed[bucket_name] = sorted(bucketed[bucket_name], key=lambda item: (-float(item["confidence"]), item["cluster_key"]))[:15]
            purity = _purity_label(
                sum(1 for item in class_items if _buyer_bucket(class_name, item) == "clean"),
                sum(1 for item in class_items if _buyer_bucket(class_name, item) == "mixed"),
                sum(1 for item in class_items if _buyer_bucket(class_name, item) == "noisy"),
            )
            buyer_summary[class_name] = {
                "count": len(class_items),
                "purity": purity,
                "avg_confidence": _confidence_stats(class_items)[0],
                "median_confidence": _confidence_stats(class_items)[1],
                "clean_count": sum(1 for item in class_items if _buyer_bucket(class_name, item) == "clean"),
                "mixed_count": sum(1 for item in class_items if _buyer_bucket(class_name, item) == "mixed"),
                "noisy_count": sum(1 for item in class_items if _buyer_bucket(class_name, item) == "noisy"),
                "examples": bucketed,
            }
        scores = _manual_scores(model_name, buyer_summary, items)
        model_summaries[model_name] = {"counts": counts, "buyer_summary": buyer_summary, "scores": scores}

    report_lines.extend(["## Buyer-meaning purity", ""])
    for model_name in MODEL_FILES:
        report_lines.extend([f"### {model_name}", ""])
        for class_name in BUYER_CLASSES:
            summary = model_summaries[model_name]["buyer_summary"][class_name]
            report_lines.extend(
                [
                    f"#### {class_name}",
                    "",
                    f"- purity: `{summary['purity']}`",
                    f"- count: `{summary['count']}`",
                    f"- avg_confidence: `{summary['avg_confidence']}`",
                    f"- median_confidence: `{summary['median_confidence']}`",
                    f"- clean/mixed/noisy: `{summary['clean_count']}/{summary['mixed_count']}/{summary['noisy_count']}`",
                    "",
                ]
            )
            for item in summary["examples"]["clean"][:15]:
                report_lines.append(
                    f"- `{item['profile_label_candidate'] or '-'}` | anchor: `{item['anchor_query'] or '-'}` | {item['reason']}"
                )
            if not summary["examples"]["clean"]:
                report_lines.append("- none")
            report_lines.append("")

    report_lines.extend(["## Confusion patterns", ""])
    confusion_specs = {
        "aesthetic ↔ decor_interior": lambda item: item["main"] == "aesthetic" and (_has_any(_combined_text(item), DECOR_PATTERNS) or "decor_interior" in set(item.get("secondary") or [])),
        "gift ↔ event_holiday": lambda item: item["main"] == "gift" and (_has_any(_combined_text(item), EVENT_PATTERNS) or "event_holiday" in set(item.get("secondary") or [])),
        "fun_meme ↔ garbage": lambda item: item["main"] == "fun_meme" and (_has_any(_combined_text(item), FUN_BAD_PATTERNS) or "garbage" in set(item.get("secondary") or [])),
        "functional ↔ serving_photo": lambda item: item["main"] in {"functional", "serving_photo"} and (_has_any(_combined_text(item), SERVING_PATTERNS + SERVING_PHOTO_PATTERNS) or "serving_photo" in set(item.get("secondary") or [])),
    }
    for title, predicate in confusion_specs.items():
        report_lines.extend([f"### {title}", ""])
        for model_name, items in model_data.items():
            examples = _confusion_examples(items, predicate=predicate)
            report_lines.append(f"- {model_name}: `{len(examples)}` sampled examples")
            for item in examples[:5]:
                report_lines.append(
                    f"  - `{item['profile_label_candidate'] or '-'}` | anchor: `{item['anchor_query'] or '-'}` | main=`{item['main']}` secondary=`{item['secondary']}`"
                )
        report_lines.append("")

    disagreement_items = []
    for cluster_key in sorted(shared_keys):
        labels = {model_name: by_model_key[model_name][cluster_key]["main"] for model_name in MODEL_FILES}
        if len(set(labels.values())) <= 1:
            continue
        base_item = by_model_key["gpt-4o-mini"][cluster_key]
        disagreement_items.append(
            (
                tuple(sorted(set(labels.values()))),
                base_item.get("profile_label_candidate") or "",
                cluster_key,
            )
        )
    selected_disagreements = []
    seen_keys: set[str] = set()
    for _labels, _label_name, cluster_key in disagreement_items:
        if cluster_key in seen_keys:
            continue
        seen_keys.add(cluster_key)
        selected_disagreements.append(cluster_key)
        if len(selected_disagreements) >= 20:
            break

    report_lines.extend(["## Side-by-side comparison", ""])
    for cluster_key in selected_disagreements:
        baseline = by_model_key["gpt-4o-mini"][cluster_key]
        report_lines.extend(
            [
                "### cluster",
                f"- label: `{baseline.get('profile_label_candidate') or '-'}`",
                f"- anchor: `{baseline.get('anchor_query') or '-'}`",
                "",
            ]
        )
        for model_name in MODEL_FILES:
            item = by_model_key[model_name][cluster_key]
            report_lines.extend(
                [
                    f"{model_name}:",
                    f"- main: `{item['main']}`",
                    f"- reason: {item['reason']}",
                    "",
                ]
            )

    report_lines.extend(["## Manual evaluation", ""])
    for model_name in MODEL_FILES:
        scores = model_summaries[model_name]["scores"]
        report_lines.extend(
            [
                f"### {model_name}",
                "",
                f"- buyer-meaning separation: `{scores['buyer_meaning_separation']}/5`",
                f"- noise level: `{scores['noise_level']}/5`",
                f"- consistency: `{scores['consistency']}/5`",
                "",
            ]
        )

    best_aesthetic = max(MODEL_FILES, key=lambda name: (_class_quality(model_summaries[name]["buyer_summary"]["aesthetic"]), model_summaries[name]["scores"]["noise_level"]))
    best_gift = max(MODEL_FILES, key=lambda name: (_class_quality(model_summaries[name]["buyer_summary"]["gift"]), model_summaries[name]["scores"]["noise_level"]))
    best_fun = max(MODEL_FILES, key=lambda name: (_class_quality(model_summaries[name]["buyer_summary"]["fun_meme"]), model_summaries[name]["scores"]["noise_level"]))
    best_overall = max(
        MODEL_FILES,
        key=lambda name: (
            model_summaries[name]["scores"]["buyer_meaning_separation"],
            model_summaries[name]["scores"]["noise_level"],
            model_summaries[name]["scores"]["consistency"],
        ),
    )
    report_lines.extend(
        [
            "## Final conclusion",
            "",
            f"- best_for_aesthetic: `{best_aesthetic}`",
            f"- best_for_gift: `{best_gift}`",
            f"- best_for_fun_meme: `{best_fun}`",
            f"- recommended_model: `{best_overall}`",
        ]
    )

    REPORT_PATH.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")
    print(json.dumps({"report_path": str(REPORT_PATH), "recommended_model": best_overall}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
