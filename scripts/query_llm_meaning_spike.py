#!/usr/bin/env python3
"""Standalone OpenRouter LLM spike for buyer-meaning classification on query clusters."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCKER_ONLY_DB_HOSTS = {"postgres", "db"}
_SCRIPT_ENV_FLAG = "ECOMCORE_QUERY_LLM_MEANING_SPIKE_IN_DOCKER"
_DEFAULT_MODEL = "openai/gpt-4o-mini"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_ALLOWED_CLASSES_V1 = {
    "aesthetic",
    "gift",
    "fun_meme",
    "self_treat",
    "serving_photo",
    "functional",
    "format_set",
    "size",
    "audience_kids",
    "generic",
    "garbage",
}
_ALLOWED_CLASSES_V2 = {
    "aesthetic",
    "gift",
    "fun_meme",
    "self_treat",
    "serving_photo",
    "decor_interior",
    "event_holiday",
    "functional",
    "format_set",
    "size",
    "audience_kids",
    "generic",
    "garbage",
}
_SYSTEM_PROMPT_V1 = """Ты классифицируешь поисковые query clusters по СМЫСЛУ ПОКУПКИ.

Тебе нельзя ориентироваться только на буквальные слова.
Нужно понять, зачем человек покупает товар.

Классы:
- aesthetic: эстетика, стиль, pinterest, красиво, мило, визуальный вайб
- gift: подарок, подруге, девушке, на праздник
- fun_meme: прикол, мем, надпись, смешная идея
- self_treat: порадовать себя, хочу себе, настроение
- serving_photo: красиво подать, для фото, визуальная подача
- functional: утилитарное использование, для супа, для микроволновки, десертная и т.п.
- format_set: набор, комплект, количество
- size: размеры
- audience_kids: детская аудитория
- generic: слишком общее, без ясного buyer-meaning
- garbage: не та категория / аксессуары / соседние сущности

Правила:
- Верни ровно один MAIN class
- SECONDARY classes: максимум 2
- Если buyer-meaning не выражен явно, не выдумывай его
- "для дома", "для кухни", "для стола" обычно generic, а не gift/aesthetic
- "сервировочная" не всегда serving_photo; если это просто классический тип тарелки без vibe, не завышай
- "декоративная" не всегда aesthetic; если это скорее интерьер/настенная тарелка, смотри осторожно
- Не путай functional с buyer-meaning
- Не путай format/set с buyer-meaning

Верни JSON строго такого вида:
{
  "main": "one_of_allowed_classes",
  "secondary": ["class1", "class2"],
  "confidence": 0.0,
  "reason": "краткое объяснение на русском"
}"""
_SYSTEM_PROMPT_V2 = """Ты классифицируешь поисковые query clusters по СМЫСЛУ ПОКУПКИ.

Тебе нельзя ориентироваться только на буквальные слова.
Нужно понять, зачем человек покупает товар.

Классы:
- aesthetic: эстетика, стиль, pinterest, красиво, мило, визуальный вайб
- gift: подарок конкретному человеку, покупка с gift motive
- fun_meme: прикол, мем, надпись, смешная идея
- self_treat: порадовать себя, хочу себе, настроение
- serving_photo: красиво подать, для фото, brunch vibe, красивый завтрак
- decor_interior: настенная тарелка, интерьер, purely decorative object, display
- event_holiday: новогодние, пасха, день рождения, 8 марта, праздник
- functional: утилитарное использование, для супа, для микроволновки, десертная и т.п.
- format_set: набор, комплект, количество
- size: размеры
- audience_kids: детская аудитория
- generic: слишком общее, без ясного buyer-meaning
- garbage: не та категория / аксессуары / соседние сущности

Правила:
- Верни ровно один MAIN class
- SECONDARY classes: максимум 2
- Если buyer-meaning не выражен явно, не выдумывай его
- "тарелка декоративная на стену" обычно decor_interior, а не aesthetic
- "новогодние тарелки", "на 8 марта", "на пасху" обычно event_holiday, а не gift, если gift motive не выражен явно
- "сервировочная" сама по себе еще не serving_photo; если нет vibe / красивой подачи / визуального контекста, не завышай
- "для дома", "для кухни", "для стола" обычно generic
- Не путай functional с buyer-meaning
- Не путай format_set с buyer-meaning
- Не путай aesthetic с decor_interior
- Не путай gift с event_holiday
- Если это соседняя сущность или аксессуар, скорее garbage

Верни JSON строго такого вида:
{
  "main": "one_of_allowed_classes",
  "secondary": ["class1", "class2"],
  "confidence": 0.0,
  "reason": "краткое объяснение на русском"
}"""
_BUYER_MEANING_CLASSES_V1 = ("aesthetic", "gift", "fun_meme", "self_treat", "serving_photo")
_BUYER_MEANING_CLASSES_V2 = (
    "aesthetic",
    "gift",
    "fun_meme",
    "self_treat",
    "serving_photo",
    "decor_interior",
    "event_holiday",
)
_RICH_SAMPLE_HINTS = (
    "эстет",
    "красив",
    "мил",
    "cute",
    "pretty",
    "pinterest",
    "винтаж",
    "стиль",
    "декор",
    "декоратив",
    "на стен",
    "интерьер",
    "сервиров",
    "завтрак",
    "бранч",
    "фото",
    "вайб",
    "подар",
    "праздн",
    "новогод",
    "рожден",
    "8 март",
    "пасх",
    "прикол",
    "мем",
    "надпис",
    "смеш",
    "сердц",
    "зайчик",
    "ракуш",
    "котик",
    "кошк",
)


def _running_inside_container() -> bool:
    return os.getenv(_SCRIPT_ENV_FLAG) == "1" or Path("/.dockerenv").exists()


def _load_env_defaults(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _declared_database_host() -> str | None:
    env_defaults = _load_env_defaults(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL") or env_defaults.get("DATABASE_URL")
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.hostname:
            return parsed.hostname
    return os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST")


def _should_reroute_to_docker() -> bool:
    if _running_inside_container():
        return False
    database_host = _declared_database_host()
    return bool(database_host and database_host.lower() in DOCKER_ONLY_DB_HOSTS)


def _rerun_in_worker_container(argv: list[str]) -> int:
    compose_file = PROJECT_ROOT / "infra" / "docker" / "docker-compose.yml"
    ensure_stack_command = ["docker", "compose", "-f", str(compose_file), "up", "-d", "postgres", "worker"]
    exec_command = ["docker", "compose", "-f", str(compose_file), "exec", "-T", "-e", f"{_SCRIPT_ENV_FLAG}=1"]
    for env_name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        env_value = os.getenv(env_name)
        if env_value:
            exec_command.extend(["-e", f"{env_name}={env_value}"])
    exec_command.extend(["worker", "python", "scripts/query_llm_meaning_spike.py", *argv])
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running query LLM meaning spike in the worker container...",
        file=sys.stderr,
    )
    ensure_result = subprocess.run(ensure_stack_command, cwd=PROJECT_ROOT)
    if ensure_result.returncode != 0:
        return ensure_result.returncode
    return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode


def _render_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json_object(content: str) -> dict[str, Any]:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value)
        text_value = re.sub(r"\s*```$", "", text_value)
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model response does not contain JSON object")
    return json.loads(text_value[start : end + 1])


def _taxonomy_config(taxonomy_version: str) -> tuple[set[str], str, tuple[str, ...]]:
    if taxonomy_version == "v2":
        return _ALLOWED_CLASSES_V2, _SYSTEM_PROMPT_V2, _BUYER_MEANING_CLASSES_V2
    return _ALLOWED_CLASSES_V1, _SYSTEM_PROMPT_V1, _BUYER_MEANING_CLASSES_V1


def _sanitize_label(payload: dict[str, Any], *, allowed_classes: set[str]) -> dict[str, Any]:
    main = str(payload.get("main") or "").strip()
    if main not in allowed_classes:
        raise ValueError(f"Unsupported main class: {main}")
    secondary_raw = payload.get("secondary") or []
    if not isinstance(secondary_raw, list):
        raise ValueError("secondary must be a list")
    secondary = []
    for item in secondary_raw[:2]:
        label = str(item or "").strip()
        if label in allowed_classes and label != main and label not in secondary:
            secondary.append(label)
    confidence = payload.get("confidence", 0.0)
    confidence_value = max(0.0, min(1.0, float(confidence)))
    reason = str(payload.get("reason") or "").strip()
    return {
        "main": main,
        "secondary": secondary,
        "confidence": round(confidence_value, 4),
        "reason": reason,
    }


def _meaning_input(row: dict[str, Any]) -> str:
    queries_block = "\n".join(f"- {query}" for query in row["representative_queries"]) if row["representative_queries"] else "-"
    return (
        f"{row['profile_label_candidate']}\n"
        f"anchor: {row['anchor_query'] or '-'}\n"
        "queries:\n"
        f"{queries_block}"
    ).strip()


def _hint_score(text: str) -> int:
    normalized = str(text or "").lower()
    return sum(1 for hint in _RICH_SAMPLE_HINTS if hint in normalized)


def _sample_rows(rows: list[dict[str, Any]], *, sample_limit: int) -> tuple[list[dict[str, Any]], str]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -int(row["hint_score"]),
            0 if row["profile_strength"] == "strong" else 1 if row["profile_strength"] == "medium" else 2,
            -len(row["representative_queries"]),
            row["cluster_key"],
        ),
    )
    return ordered[:sample_limit], "hint-boosted sample (buyer-meaning hints + stronger profiles + richer representatives)"


def _classify_one(
    session: Any,
    *,
    api_key: str,
    model_name: str,
    row: dict[str, Any],
    system_prompt: str,
    allowed_classes: set[str],
) -> dict[str, Any]:
    import requests

    prompt = f"Cluster profile:\n{_meaning_input(row)}\n\nКлассифицируй cluster по смыслу покупки."
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local.ecomcore.spike",
        "X-Title": "EcomCore Query LLM Meaning Spike",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = session.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"retryable_status:{response.status_code}:{response.text[:400]}")
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = _sanitize_label(_extract_json_object(content), allowed_classes=allowed_classes)
            return {
                "cluster_key": row["cluster_key"],
                "profile_label_candidate": row["profile_label_candidate"],
                "anchor_query": row["anchor_query"],
                "representative_queries": row["representative_queries"],
                **parsed,
            }
        except Exception as exc:
            last_error = exc
            if attempt >= 4:
                break
            time.sleep(min(20, 1.5 * (2 ** attempt)))
    raise RuntimeError(str(last_error) if last_error else "Unknown OpenRouter error")


def _build_report(
    *,
    output_path: Path,
    project_id: int,
    category_id: int,
    model_name: str,
    taxonomy_version: str,
    total_profiles: int,
    excluded_empty_count: int,
    labels: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    sample_strategy: str,
    previous_labels: list[dict[str, Any]] | None = None,
) -> None:
    allowed_classes, _, buyer_meaning_classes = _taxonomy_config(taxonomy_version)
    labels_sorted = sorted(labels, key=lambda item: (-float(item["confidence"]), item["profile_label_candidate"], item["cluster_key"]))
    counts = Counter(item["main"] for item in labels_sorted)
    by_class: dict[str, list[dict[str, Any]]] = {label: [] for label in sorted(allowed_classes)}
    for item in labels_sorted:
        by_class[item["main"]].append(item)
    low_confidence = sorted(labels_sorted, key=lambda item: (float(item["confidence"]), item["cluster_key"]))[:20]

    aesthetic_vs_decor = [
        item
        for item in labels_sorted
        if item["main"] in {"aesthetic", "decor_interior"}
        or any(cls in {"aesthetic", "decor_interior"} for cls in item["secondary"])
    ][:20]
    gift_vs_event = [
        item
        for item in labels_sorted
        if item["main"] in {"gift", "event_holiday"}
        or any(cls in {"gift", "event_holiday"} for cls in item["secondary"])
    ][:20]
    buyer_low_confidence = [
        item
        for item in sorted(labels_sorted, key=lambda item: (float(item["confidence"]), item["cluster_key"]))
        if item["main"] in buyer_meaning_classes or any(cls in buyer_meaning_classes for cls in item["secondary"])
    ][:20]

    def render_examples(items: list[dict[str, Any]], *, label_limit: int = 20, query_limit: int = 10) -> tuple[list[str], list[str]]:
        labels_block: list[str] = []
        queries_block: list[str] = []
        for item in items:
            label = item["profile_label_candidate"] or "-"
            if label not in labels_block and len(labels_block) < label_limit:
                labels_block.append(label)
            for query in ([item["anchor_query"]] + list(item["representative_queries"])):
                query_value = str(query or "").strip()
                if query_value and query_value not in queries_block and len(queries_block) < query_limit:
                    queries_block.append(query_value)
        return labels_block, queries_block

    def render_share(class_name: str) -> str:
        if not labels_sorted:
            return "0.00%"
        return f"{(counts.get(class_name, 0) / len(labels_sorted)):.2%}"

    focus_classes = (
        "aesthetic",
        "gift",
        "fun_meme",
        "self_treat",
        "serving_photo",
        "decor_interior",
        "event_holiday",
    )
    focus_descriptions = {
        "aesthetic": "визуальный вкус, стиль, cute/pinterest vibe",
        "gift": "явный gift motive для конкретного человека",
        "fun_meme": "ирония, прикол, надписи, шутка",
        "self_treat": "порадовать себя, покупка ради настроения",
        "serving_photo": "визуальная подача, breakfast/brunch/photo vibe",
        "decor_interior": "декор и интерьер, настенное/display использование",
        "event_holiday": "повод и праздник без обязательного gift motive",
    }

    previous_counts = Counter()
    if previous_labels:
        previous_counts = Counter(item["main"] for item in previous_labels)
    comparison_lines = [
        f"- v1_processed: `{len(previous_labels or [])}`",
        f"- v2_processed: `{len(labels_sorted)}`",
        f"- aesthetic_v1_vs_v2: `{previous_counts.get('aesthetic', 0)} -> {counts.get('aesthetic', 0)}`",
        f"- gift_v1_vs_v2: `{previous_counts.get('gift', 0)} -> {counts.get('gift', 0)}`",
        f"- fun_meme_v1_vs_v2: `{previous_counts.get('fun_meme', 0)} -> {counts.get('fun_meme', 0)}`",
        f"- decor_interior_v2: `{counts.get('decor_interior', 0)}`",
        f"- event_holiday_v2: `{counts.get('event_holiday', 0)}`",
        f"- self_treat_v2: `{counts.get('self_treat', 0)}`",
        f"- serving_photo_v2: `{counts.get('serving_photo', 0)}`",
    ]

    lines = [
        "# Query LLM Meaning Report v2",
        "",
        "## Summary",
        "",
        f"- project_id: `{project_id}`",
        f"- category_id: `{category_id}`",
        f"- total_cluster_profiles: `{total_profiles}`",
        f"- excluded_empty_profiles: `{excluded_empty_count}`",
        f"- processed_successfully: `{len(labels_sorted)}`",
        f"- failed_requests_count: `{len(errors)}`",
        f"- model_used: `{model_name}`",
        f"- taxonomy_version: `{taxonomy_version}`",
        f"- sample_strategy_used: `{sample_strategy}`",
        "",
        "## Distribution",
        "",
        "| class | count | share |",
        "| --- | ---: | ---: |",
    ]
    for class_name in sorted(allowed_classes):
        lines.append(f"| {class_name} | {counts.get(class_name, 0)} | {render_share(class_name)} |")

    lines.extend(["", "## Focus classes", ""])
    for class_name in focus_classes:
        items = by_class[class_name]
        labels_block, queries_block = render_examples(items)
        lines.extend(
            [
                f"### {class_name}",
                "",
                f"- count: `{len(items)}`",
                f"- share: `{render_share(class_name)}`",
                f"- interpretation: {focus_descriptions[class_name]}",
                "",
                "**Examples**",
                "",
            ]
        )
        lines.extend(f"- {label}" for label in labels_block or ["-"])
        lines.extend(["", "**Anchor / Representative Queries**", ""])
        lines.extend(f"- {query}" for query in queries_block or ["-"])
        lines.append("")

    lines.extend(["## Confusion analysis", "", "### aesthetic vs decor_interior", ""])
    for item in aesthetic_vs_decor or []:
        lines.append(
            f"- `{item['confidence']:.4f}` | main={item['main']} secondary={item['secondary']} | {item['profile_label_candidate']} | anchor: {item['anchor_query'] or '-'} | {item['reason']}"
        )
    if not aesthetic_vs_decor:
        lines.append("- none")
    lines.extend(["", "### gift vs event_holiday", ""])
    for item in gift_vs_event or []:
        lines.append(
            f"- `{item['confidence']:.4f}` | main={item['main']} secondary={item['secondary']} | {item['profile_label_candidate']} | anchor: {item['anchor_query'] or '-'} | {item['reason']}"
        )
    if not gift_vs_event:
        lines.append("- none")
    lines.extend(["", "### low-confidence buyer-meaning", ""])
    for item in buyer_low_confidence or []:
        lines.append(
            f"- `{item['confidence']:.4f}` | main={item['main']} secondary={item['secondary']} | {item['profile_label_candidate']} | anchor: {item['anchor_query'] or '-'} | {item['reason']}"
        )
    if not buyer_low_confidence:
        lines.append("- none")

    lines.extend(["", "## Low-confidence cases", ""])
    for item in low_confidence:
        lines.append(
            f"- `{item['confidence']:.4f}` | {item['main']} | {item['profile_label_candidate']} | anchor: {item['anchor_query'] or '-'} | {item['reason']}"
        )

    lines.extend(["", "## Comparison vs v1", ""])
    lines.extend(comparison_lines)

    buyer_meaning_total = sum(counts.get(name, 0) for name in buyer_meaning_classes)
    generic_functional_total = sum(counts.get(name, 0) for name in ("generic", "functional", "format_set", "size"))
    if counts.get("decor_interior", 0) > 0 and counts.get("event_holiday", 0) > 0 and buyer_meaning_total >= max(120, generic_functional_total * 0.2):
        conclusion = "improved and promising"
    elif buyer_meaning_total > 0:
        conclusion = "still partially works"
    else:
        conclusion = "did not improve meaningfully"
    lines.extend(
        [
            "",
            "## Final conclusion",
            "",
            f"- verdict: `{conclusion}`",
            f"- buyer_meaning_total: `{buyer_meaning_total}`",
            f"- generic_functional_total: `{generic_functional_total}`",
        ]
    )
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

def _run_spike(
    *,
    project_id: int,
    category_id: int,
    sample_limit: int | None,
    full_run: bool,
    model_name: str,
    output_suffix: str,
    taxonomy_version: str,
) -> dict[str, Any]:
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment")
    model_name = os.getenv("OPENROUTER_MODEL") or model_name
    if not model_name:
        raise RuntimeError("OPENROUTER_MODEL is required or a default model must be available")
    allowed_classes, system_prompt, _ = _taxonomy_config(taxonomy_version)
    from app.db import SessionLocal
    from app.services.seo.query_pipeline import get_query_clusters, run_query_profile_extraction

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{output_suffix}" if output_suffix else ""
    labels_path = OUTPUTS_DIR / f"query_llm_meaning_labels{suffix}.json"
    report_path = OUTPUTS_DIR / f"query_llm_meaning_report{suffix}.md"
    errors_path = OUTPUTS_DIR / f"query_llm_meaning_errors{suffix}.json"
    low_confidence_path = OUTPUTS_DIR / f"query_llm_meaning_low_confidence{suffix}.json"
    previous_labels_path = OUTPUTS_DIR / "query_llm_meaning_labels.json"

    session = SessionLocal()
    try:
        profile_result = run_query_profile_extraction(
            session,
            project_id=project_id,
            category_id=category_id,
            top_limit=40,
            samples_limit=40,
            refresh_hybrid=True,
            persist=False,
        )
        clusters = get_query_clusters(session, project_id=project_id, category_id=category_id)
        cluster_by_key = {cluster.cluster_key: cluster for cluster in clusters}
        total_profiles = len(profile_result.profiles)

        rows: list[dict[str, Any]] = []
        excluded_empty_count = 0
        for profile in profile_result.profiles:
            representative_queries: list[str] = []
            cluster = cluster_by_key.get(profile.cluster_key)
            if cluster is not None:
                for member in cluster.members[:5]:
                    query = str(member.display_query or member.normalized_query_text or "").strip()
                    if query and query not in representative_queries:
                        representative_queries.append(query)
            label = str(profile.profile_label_candidate or "").strip()
            anchor = str(profile.source_anchor_query or "").strip()
            input_text = _meaning_input(
                {
                    "profile_label_candidate": label,
                    "anchor_query": anchor,
                    "representative_queries": representative_queries,
                }
            )
            if profile.profile_strength == "empty" or not input_text.replace("-", "").strip():
                excluded_empty_count += 1
                continue
            hint_text = " ".join([label, anchor, *representative_queries])
            rows.append(
                {
                    "cluster_key": profile.cluster_key,
                    "profile_label_candidate": label,
                    "anchor_query": anchor,
                    "representative_queries": representative_queries,
                    "profile_strength": profile.profile_strength,
                    "meaning_input": input_text,
                    "hint_score": _hint_score(hint_text),
                }
            )

        sample_strategy = "full non-empty run"
        if not full_run:
            limit = max(1, int(sample_limit or 300))
            rows, sample_strategy = _sample_rows(rows, sample_limit=limit)

        existing_labels = []
        if labels_path.exists():
            existing_labels = json.loads(labels_path.read_text(encoding="utf-8"))
        existing_errors = []
        if errors_path.exists():
            existing_errors = json.loads(errors_path.read_text(encoding="utf-8"))
        labels_by_key = {item["cluster_key"]: item for item in existing_labels if item.get("cluster_key")}
        errors_by_key = {item["cluster_key"]: item for item in existing_errors if item.get("cluster_key")}

        http = requests.Session()
        processed = 0
        for row in rows:
            if row["cluster_key"] in labels_by_key:
                continue
            try:
                label = _classify_one(
                    http,
                    api_key=api_key,
                    model_name=model_name,
                    row=row,
                    system_prompt=system_prompt,
                    allowed_classes=allowed_classes,
                )
                labels_by_key[row["cluster_key"]] = label
                errors_by_key.pop(row["cluster_key"], None)
            except Exception as exc:
                errors_by_key[row["cluster_key"]] = {
                    "cluster_key": row["cluster_key"],
                    "profile_label_candidate": row["profile_label_candidate"],
                    "anchor_query": row["anchor_query"],
                    "error": str(exc),
                }
            processed += 1
            if processed % 10 == 0:
                _render_json(labels_path, sorted(labels_by_key.values(), key=lambda item: item["cluster_key"]))
                _render_json(errors_path, sorted(errors_by_key.values(), key=lambda item: item["cluster_key"]))
            time.sleep(0.35)

        labels = sorted(labels_by_key.values(), key=lambda item: item["cluster_key"])
        errors = sorted(errors_by_key.values(), key=lambda item: item["cluster_key"])
        _render_json(labels_path, labels)
        _render_json(errors_path, errors)
        low_confidence = sorted(labels, key=lambda item: (float(item["confidence"]), item["cluster_key"]))[:50]
        _render_json(low_confidence_path, low_confidence)
        previous_labels = []
        if previous_labels_path.exists():
            try:
                previous_labels = json.loads(previous_labels_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous_labels = []
        _build_report(
            output_path=report_path,
            project_id=project_id,
            category_id=category_id,
            model_name=model_name,
            taxonomy_version=taxonomy_version,
            total_profiles=total_profiles,
            excluded_empty_count=excluded_empty_count,
            labels=labels,
            errors=errors,
            sample_strategy=sample_strategy,
            previous_labels=previous_labels,
        )
        counts = Counter(item["main"] for item in labels)
        return {
            "project_id": project_id,
            "category_id": category_id,
            "model_name": model_name,
            "taxonomy_version": taxonomy_version,
            "sample_strategy": sample_strategy,
            "total_profiles": total_profiles,
            "excluded_empty_profiles": excluded_empty_count,
            "processed_successfully": len(labels),
            "failed_requests_count": len(errors),
            "counts_by_main": dict(sorted(counts.items())),
            "labels_path": str(labels_path),
            "report_path": str(report_path),
            "errors_path": str(errors_path),
            "low_confidence_path": str(low_confidence_path),
        }
    finally:
        session.close()


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])
    sys.path.insert(0, str(SRC_ROOT))
    parser = argparse.ArgumentParser(description="Standalone OpenRouter spike for query buyer-meaning classification")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id")
    parser.add_argument("--sample-limit", type=int, default=None, help="Sample size for smoke mode")
    parser.add_argument("--full-run", action="store_true", help="Process all available non-empty profiles")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="Fallback OpenRouter model when env is unset")
    parser.add_argument("--output-suffix", default="", help="Optional suffix for output filenames, e.g. v2")
    parser.add_argument("--taxonomy-v2", action="store_true", help="Use calibrated taxonomy v2")
    args = parser.parse_args()
    summary = _run_spike(
        project_id=args.project_id,
        category_id=args.category_id,
        sample_limit=args.sample_limit,
        full_run=bool(args.full_run),
        model_name=str(args.model),
        output_suffix=str(args.output_suffix or ""),
        taxonomy_version="v2" if args.taxonomy_v2 else "v1",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
