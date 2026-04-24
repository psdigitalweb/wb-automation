#!/usr/bin/env python3
"""Standalone multi-category validation spike for buyer-meaning retrieval."""

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
_SCRIPT_ENV_FLAG = "ECOMCORE_MULTI_CATEGORY_BUYER_MEANING_VALIDATION_IN_DOCKER"
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_LLM_MODEL = "openai/gpt-4.1-mini"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_BUYER_CLASSES = {"aesthetic", "gift", "fun_meme", "self_treat", "serving_photo"}
_BUYER_MAIN_CLASSES = {"aesthetic", "gift", "fun_meme", "self_treat"}
_EXCLUDED_CLASSES = {"decor_interior", "event_holiday", "garbage"}
_LOWER_PRIORITY_CLASSES = {"generic", "functional", "format_set", "size"}
_ALLOWED_CLASSES = {
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
_SKU_SYSTEM_PROMPT = """Ты определяешь СМЫСЛ ПОКУПКИ товара.

Выбери:
- MAIN (обязательный)
- SECONDARY (0-2)

Классы:
- aesthetic
- gift
- fun_meme
- self_treat
- serving_photo
- decor_interior
- event_holiday
- functional
- format_set
- size
- audience_kids
- generic
- garbage

Правила:
- не выдумывай смысл, если его нет
- MAIN должен показывать, ЧЕРЕЗ ЧТО товар продается в первую очередь.
- functional как MAIN допустим только если товар описан в основном через утилитарное назначение, а buyer-meaning сигнал слабый или отсутствует.
- Не ставь functional как MAIN, если в описании/отзывах явно есть сильные buyer-meaning сигналы: милый / cute / kawaii / красивый / стильный / aesthetic / pinterest / принт / рисунок / персонаж / котик / зайчик / ушки / надпись / мем / прикол / funny / joke / подарок / подарочная коробка / отличный подарок / радует / настроение / vibe / уют / любовь / восторг.
- если товар "про красивое/вайб" -> aesthetic
- если "в подарок" -> gift
- если "надпись/прикол" -> fun_meme
- если buyer-meaning выражен явно, он должен стать MAIN, а functional может быть только SECONDARY.
- "для дома", "для кухни", "для стола" сами по себе не делают товар buyer-meaning.

Примеры:
Example A
Товар: керамическая тарелка с котиком, ушками, надписью, подарок для друзей
Правильно: main=aesthetic; secondary=[gift, fun_meme]
Неправильно: main=functional

Example B
Товар: кружка с мемной надписью, отличный подарок, котик, юмор
Правильно: main=fun_meme; secondary=[gift, aesthetic]
Неправильно: main=functional

Example C
Товар: тетрадь с милым принтом, стильная, эстетичная, радуйте себя
Правильно: main=aesthetic; secondary=[self_treat, functional]
Неправильно: main=functional

Example D
Товар: ланчбокс для микроволновки, герметичный, контейнер для еды, отделения
Правильно: main=functional; secondary=[]

Верни JSON:
{
  "main": "...",
  "secondary": ["..."],
  "confidence": 0.0,
  "reason": "..."
}"""
_CATEGORY_CONFIGS = [
    {
        "slug": "plates",
        "display_name": "тарелки",
        "category_id": 821,
        "label_source": "outputs/query_llm_meaning_labels_v2.json",
        "query_sample_limit": None,
        "product_type_terms": ("тарел",),
        "preferred_nm_ids": (321128388, 38802116),
    },
    {
        "slug": "cups",
        "display_name": "кружки",
        "category_id": 812,
        "label_source": "outputs/query_llm_meaning_labels_cups_812_v2.json",
        "query_sample_limit": 300,
        "product_type_terms": ("круж",),
        "preferred_nm_ids": (535441194, 346641415, 291861314, 291861312, 545238388, 170572952),
    },
    {
        "slug": "lunchboxes",
        "display_name": "ланчбоксы",
        "category_id": 2841,
        "label_source": "outputs/query_llm_meaning_labels_lunchboxes_2841_v2.json",
        "query_sample_limit": 300,
        "product_type_terms": ("ланч", "бокс", "контейнер"),
        "preferred_nm_ids": (10533815, 10533819, 10533818, 10533814),
    },
    {
        "slug": "notebooks",
        "display_name": "тетради",
        "category_id": 745,
        "label_source": "outputs/query_llm_meaning_labels_notebooks_745_v2.json",
        "query_sample_limit": 300,
        "product_type_terms": ("тетрад",),
        "preferred_nm_ids": (39437397, 39438530, 66988643, 117249798),
    },
]
_BUYER_HINTS = (
    "красив",
    "мил",
    "cute",
    "vibe",
    "подар",
    "прикол",
    "мем",
    "надпис",
    "стиль",
    "pinterest",
    "кот",
    "лапуш",
    "серд",
    "love",
    "mood",
    "princess",
    "эстет",
    "fun",
)
_GENERIC_LEAK_PATTERNS = (
    "для дома",
    "для кухни",
    "для стола",
    "набор",
    "комплект",
    "см",
    "шт",
    "суп",
    "микровол",
    "свч",
)
_BUYER_QUERY_PATTERNS = (
    "pinterest",
    "эстет",
    "красив",
    "мил",
    "стиль",
    "подар",
    "прикол",
    "мем",
    "надпис",
    "cute",
    "vibe",
    "кот",
    "love",
)
_LOW_VALUE_QUERY_STOPWORDS = {
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
}
_SUPPRESS_REGEX_WEIGHTS: tuple[tuple[str, float, str], ...] = (
    (r"\b\d+\s*мл\b", 0.18, "volume_ml"),
    (r"\b\d+\s*л\b", 0.18, "volume_l"),
    (r"\b\d+\s*см\b", 0.18, "size_cm"),
    (r"\b\d+\s*шт\b", 0.18, "count_units"),
    (r"\b\d+\s*лист", 0.18, "count_sheets"),
    (r"\bнабор\b", 0.18, "set"),
    (r"\bкомплект\b", 0.18, "set"),
    (r"\b50\s*штук\b", 0.2, "bulk_count"),
    (r"\b20\s*штук\b", 0.2, "bulk_count"),
    (r"\b12\s*штук\b", 0.2, "bulk_count"),
    (r"\bбумаг", 0.25, "accessory_paper"),
    (r"\bлист(?:ы|ов|а)?\b", 0.25, "accessory_sheets"),
    (r"\bразделител", 0.25, "accessory_dividers"),
    (r"\bобложк", 0.22, "accessory_cover"),
    (r"\bсменн(?:ый|ые)? блок", 0.28, "accessory_refill"),
    (r"\bкольц", 0.25, "accessory_rings"),
    (r"\bдля микроволновки\b", 0.18, "utilitarian_microwave"),
    (r"\bс подогревом\b", 0.22, "utilitarian_heating"),
    (r"\bгерметичн", 0.18, "utilitarian_sealed"),
    (r"\bдля супа\b", 0.18, "utilitarian_soup"),
    (r"\bна работу\b", 0.18, "utilitarian_work"),
    (r"\bдля еды\b", 0.16, "utilitarian_food"),
    (r"\bс отделениями\b", 0.18, "utilitarian_sections"),
    (r"\bдля дома\b", 0.15, "generic_home"),
    (r"\bдля кухни\b", 0.15, "generic_kitchen"),
    (r"\bдля стола\b", 0.15, "generic_table"),
)
_MOTIF_BUCKETS: dict[str, tuple[str, ...]] = {
    "animal_cute": ("котик", "кот", "кошк", "ушк", "зайч"),
    "aesthetic": ("pinterest", "эстет", "стиль", "красив"),
    "inscription_meme": ("надпис", "прикол", "мем", "смешн", "funny", "joke"),
    "gift": ("подар", "подарочн"),
    "spoon_mug": ("ложк", "стич", "блюдц"),
    "notebook_expression": ("пиши", "запис", "чернил", "котик", "принт"),
}
_AESTHETIC_PRIORITY_CUES = (
    "мил",
    "cute",
    "kawaii",
    "красив",
    "стиль",
    "aesthetic",
    "pinterest",
    "принт",
    "рисунк",
    "персонаж",
    "котик",
    "зайчик",
    "ушки",
    "vibe",
    "уют",
    "настроен",
    "любов",
    "восторг",
    "дизайн",
    "вайб",
    "шарм",
    "эстет",
)
_GIFT_PRIORITY_CUES = (
    "подар",
    "подарочн",
    "отличный подарок",
)
_FUN_PRIORITY_CUES = (
    "надпис",
    "мем",
    "прикол",
    "funny",
    "joke",
    "забав",
    "смешн",
    "юмор",
)
_SELF_TREAT_PRIORITY_CUES = (
    "пораду",
    "для себя",
    "хочу себе",
    "себя любим",
    "настроен",
    "уют",
    "радует",
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
    exec_command.extend(["worker", "python", "scripts/multi_category_buyer_meaning_validation.py", *argv])
    database_host = _declared_database_host() or "postgres"
    print(
        f"DB host '{database_host}' is available only inside docker-compose network. "
        "Re-running multi-category buyer-meaning validation in the worker container...",
        file=sys.stderr,
    )
    ensure_result = subprocess.run(ensure_stack_command, cwd=PROJECT_ROOT)
    if ensure_result.returncode != 0:
        return ensure_result.returncode
    return subprocess.run(exec_command, cwd=PROJECT_ROOT).returncode


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


def _sanitize_label(payload: dict[str, Any]) -> dict[str, Any]:
    main = str(payload.get("main") or "").strip()
    if main not in _ALLOWED_CLASSES:
        raise ValueError(f"Unsupported main class: {main}")
    secondary_raw = payload.get("secondary") or []
    secondary: list[str] = []
    if isinstance(secondary_raw, list):
        for item in secondary_raw[:2]:
            label = str(item or "").strip()
            if label in _ALLOWED_CLASSES and label != main and label not in secondary:
                secondary.append(label)
    confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    reason = str(payload.get("reason") or "").strip()
    return {"main": main, "secondary": secondary, "confidence": round(confidence, 4), "reason": reason}


def _matching_cues(text_value: str, cues: tuple[str, ...]) -> set[str]:
    normalized = str(text_value or "").lower()
    return {cue for cue in cues if cue in normalized}


def _apply_sku_meaning_priority_guard(label: dict[str, Any], *, sku_meaning_input: str) -> dict[str, Any]:
    if label.get("main") != "functional":
        return label

    secondary = list(label.get("secondary") or [])
    buyer_secondaries = [item for item in secondary if item in _BUYER_MAIN_CLASSES]
    if not buyer_secondaries:
        return label

    combined_text = " ".join([str(sku_meaning_input or ""), str(label.get("reason") or "")]).lower()
    matched_aesthetic = _matching_cues(combined_text, _AESTHETIC_PRIORITY_CUES)
    matched_gift = _matching_cues(combined_text, _GIFT_PRIORITY_CUES)
    matched_fun = _matching_cues(combined_text, _FUN_PRIORITY_CUES)
    matched_self_treat = _matching_cues(combined_text, _SELF_TREAT_PRIORITY_CUES)
    matched_all = matched_aesthetic | matched_gift | matched_fun | matched_self_treat
    if len(matched_all) < 2:
        return label

    scored_candidates: list[tuple[int, str]] = []
    for candidate in buyer_secondaries:
        if candidate == "fun_meme":
            score = len(matched_fun) * 3
        elif candidate == "gift":
            score = len(matched_gift) * 3
        elif candidate == "aesthetic":
            score = len(matched_aesthetic) * 3
        elif candidate == "self_treat":
            score = len(matched_self_treat) * 3
        else:
            score = 0
        if score > 0:
            scored_candidates.append((score, candidate))

    if scored_candidates:
        scored_candidates.sort(key=lambda item: (-item[0], buyer_secondaries.index(item[1])))
        new_main = scored_candidates[0][1]
    else:
        new_main = buyer_secondaries[0]

    new_secondary: list[str] = []
    for candidate in secondary:
        if candidate != new_main and candidate not in new_secondary:
            new_secondary.append(candidate)
    if "functional" not in new_secondary:
        new_secondary.append("functional")
    new_secondary = new_secondary[:2]

    cue_summary = []
    if matched_aesthetic and new_main == "aesthetic":
        cue_summary.extend(sorted(matched_aesthetic)[:4])
    if matched_gift and new_main == "gift":
        cue_summary.extend(sorted(matched_gift)[:4])
    if matched_fun and new_main == "fun_meme":
        cue_summary.extend(sorted(matched_fun)[:4])
    if matched_self_treat and new_main == "self_treat":
        cue_summary.extend(sorted(matched_self_treat)[:4])
    if not cue_summary:
        cue_summary.extend(sorted(matched_all)[:4])

    reason = str(label.get("reason") or "").strip()
    guard_note = (
        f" Priority override: strong buyer-meaning cues ({', '.join(cue_summary)}) "
        f"promoted `{new_main}` to main; functional kept as secondary."
    )
    return {
        "main": new_main,
        "secondary": new_secondary,
        "confidence": label.get("confidence", 0.0),
        "reason": (reason + guard_note).strip(),
    }


def _classify_sku_meaning(http: Any, *, api_key: str, model_name: str, sku_meaning_input: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local.ecomcore.spike",
        "X-Title": "EcomCore Multi Category Buyer Meaning Validation",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": _SKU_SYSTEM_PROMPT},
            {"role": "user", "content": sku_meaning_input},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = http.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"retryable_status:{response.status_code}:{response.text[:400]}")
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            label = _sanitize_label(_extract_json_object(content))
            return _apply_sku_meaning_priority_guard(label, sku_meaning_input=sku_meaning_input)
        except Exception as exc:
            last_error = exc
            if attempt >= 4:
                break
            time.sleep(min(20, 1.5 * (2 ** attempt)))
    raise RuntimeError(str(last_error) if last_error else "Unknown OpenRouter error")


def _collect_reviews(session: Any, *, project_id: int, nm_id: int, limit: int = 30) -> list[str]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT raw
            FROM wb_feedback_snapshots
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY created_date DESC NULLS LAST, snapshot_at DESC NULLS LAST, id DESC
            LIMIT 100
            """
        ),
        {"project_id": project_id, "nm_id": nm_id},
    ).mappings().all()

    reviews: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        raw = raw or {}
        for field_name in ("text", "pros", "cons"):
            value = str(raw.get(field_name) or "").strip()
            if not value:
                continue
            normalized = value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            reviews.append(value)
            if len(reviews) >= limit:
                return reviews
    return reviews


def _sku_meaning_input(*, title: str, description: str, reviews: list[str]) -> str:
    parts = [title.strip(), description.strip()]
    if reviews:
        parts.append("\n".join(reviews))
    return "\n".join(part for part in parts if part)


def _buyer_hint_score(text: str) -> int:
    normalized = str(text or "").lower()
    return sum(1 for hint in _BUYER_HINTS if hint in normalized)


def _resolve_category_id(session: Any, *, project_id: int, configured_id: int | None, product_type_terms: tuple[str, ...]) -> int | None:
    from sqlalchemy import text

    if configured_id:
        row = session.execute(
            text(
                """
                SELECT COUNT(*) AS sku_count
                FROM products
                WHERE project_id = :project_id
                  AND subject_id = :subject_id
                """
            ),
            {"project_id": project_id, "subject_id": configured_id},
        ).mappings().first()
        if row and int(row["sku_count"] or 0) > 0:
            return int(configured_id)

    pattern_filters = []
    params: dict[str, Any] = {"project_id": project_id}
    for index, term in enumerate(product_type_terms):
        key = f"pattern_{index}"
        params[key] = f"%{term.lower()}%"
        pattern_filters.append(f"LOWER(COALESCE(title, '')) LIKE :{key}")
    if not pattern_filters:
        return None
    rows = session.execute(
        text(
            f"""
            SELECT subject_id, COUNT(*) AS sku_count
            FROM products
            WHERE project_id = :project_id
              AND subject_id IS NOT NULL
              AND ({' OR '.join(pattern_filters)})
            GROUP BY subject_id
            ORDER BY sku_count DESC, subject_id ASC
            LIMIT 10
            """
        ),
        params,
    ).mappings().all()
    if not rows:
        return configured_id
    return int(rows[0]["subject_id"])


def _pick_skus(
    session: Any,
    *,
    project_id: int,
    category_id: int,
    preferred_nm_ids: tuple[int, ...],
    sku_limit: int,
) -> list[dict[str, Any]]:
    from sqlalchemy import text

    selected: list[dict[str, Any]] = []
    seen_nm_ids: set[int] = set()

    if preferred_nm_ids:
        preferred_rows = session.execute(
            text(
                """
                SELECT nm_id, subject_id, title, description, vendor_code, raw, updated_at
                FROM products
                WHERE project_id = :project_id
                  AND subject_id = :category_id
                  AND nm_id = ANY(:nm_ids)
                ORDER BY updated_at DESC NULLS LAST, nm_id ASC
                """
            ),
            {"project_id": project_id, "category_id": category_id, "nm_ids": list(preferred_nm_ids)},
        ).mappings().all()
        for row in sorted(preferred_rows, key=lambda item: preferred_nm_ids.index(int(item["nm_id"]))):
            nm_id = int(row["nm_id"])
            if nm_id in seen_nm_ids:
                continue
            raw = row.get("raw")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            raw = raw or {}
            selected.append(
                {
                    "nm_id": nm_id,
                    "subject_id": row.get("subject_id"),
                    "title": str(row.get("title") or raw.get("title") or "").strip(),
                    "description": str(row.get("description") or raw.get("description") or "").strip(),
                    "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
                }
            )
            seen_nm_ids.add(nm_id)
            if len(selected) >= sku_limit:
                return selected[:sku_limit]

    candidate_rows = session.execute(
        text(
            """
            SELECT nm_id, subject_id, title, description, vendor_code, raw, updated_at
            FROM products
            WHERE project_id = :project_id
              AND subject_id = :category_id
            ORDER BY updated_at DESC NULLS LAST, nm_id DESC
            LIMIT 300
            """
        ),
        {"project_id": project_id, "category_id": category_id},
    ).mappings().all()

    scored_rows: list[tuple[int, int, int, dict[str, Any]]] = []
    for row in candidate_rows:
        nm_id = int(row["nm_id"])
        if nm_id in seen_nm_ids:
            continue
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        raw = raw or {}
        title = str(row.get("title") or raw.get("title") or "").strip()
        description = str(row.get("description") or raw.get("description") or "").strip()
        combined = f"{title}\n{description}"
        scored_rows.append(
            (
                _buyer_hint_score(combined),
                len(description),
                nm_id,
                {
                    "nm_id": nm_id,
                    "subject_id": row.get("subject_id"),
                    "title": title,
                    "description": description,
                    "vendor_code": str(row.get("vendor_code") or raw.get("vendorCode") or "").strip(),
                },
            )
        )
    scored_rows.sort(key=lambda item: (-item[0], -item[1], item[2]))
    for hint_score, _, _, payload in scored_rows:
        if hint_score <= 0 and selected:
            break
        if payload["nm_id"] in seen_nm_ids:
            continue
        selected.append(payload)
        seen_nm_ids.add(payload["nm_id"])
        if len(selected) >= sku_limit:
            break
    return selected[:sku_limit]


def _cluster_meaning_text(cluster: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(cluster.get("profile_label_candidate") or "").strip(),
            f"anchor: {str(cluster.get('anchor_query') or '').strip()}",
            "queries:",
            *[f"- {str(query).strip()}" for query in cluster.get("representative_queries") or []],
        ]
    ).strip()


def _cluster_product_type_guard(cluster: dict[str, Any], *, product_type_terms: tuple[str, ...]) -> bool:
    text_value = " ".join(
        [
            str(cluster.get("profile_label_candidate") or ""),
            str(cluster.get("anchor_query") or ""),
            *[str(query or "") for query in cluster.get("representative_queries") or []],
        ]
    ).lower()
    return any(term in text_value for term in product_type_terms)


def _ensure_query_labels(
    *,
    project_id: int,
    category_id: int,
    category_slug: str,
    label_source: str,
    query_sample_limit: int | None,
) -> tuple[Path, list[dict[str, Any]]]:
    path = PROJECT_ROOT / label_source
    should_rebuild = not path.exists()
    if path.exists():
        try:
            existing_labels = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing_labels = []
        if not existing_labels:
            should_rebuild = True

    if should_rebuild:
        if query_sample_limit is None:
            raise RuntimeError(f"Expected existing query labels at {path}")
        env = os.environ.copy()
        env["OPENROUTER_MODEL"] = env.get("OPENROUTER_MODEL") or _DEFAULT_LLM_MODEL
        suffix = f"{category_slug}_{category_id}_v2"
        command = [
            sys.executable,
            "scripts/query_llm_meaning_spike.py",
            "--project-id",
            str(project_id),
            "--category-id",
            str(category_id),
            "--sample-limit",
            str(query_sample_limit),
            "--output-suffix",
            suffix,
            "--taxonomy-v2",
        ]
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"query_llm_meaning_spike.py failed for category {category_id}")
        path = OUTPUTS_DIR / f"query_llm_meaning_labels_{suffix}.json"
    labels = json.loads(path.read_text(encoding="utf-8"))
    return path, labels


def _adjusted_similarity(*, similarity: float, sku_meaning: dict[str, Any], cluster: dict[str, Any]) -> tuple[float, str]:
    adjusted = similarity
    reasons: list[str] = [f"sim={similarity:.4f}"]
    sku_classes = {sku_meaning["main"], *(sku_meaning.get("secondary") or [])}
    cluster_classes = {cluster["main"], *(cluster.get("secondary") or [])}
    buyer_overlap = sorted(_BUYER_CLASSES.intersection(sku_classes).intersection(cluster_classes))
    if cluster["main"] in _BUYER_CLASSES:
        adjusted += 0.06
        reasons.append(f"buyer_main={cluster['main']}")
    elif cluster_classes.intersection(_BUYER_CLASSES):
        adjusted += 0.03
        reasons.append("buyer_secondary")
    if buyer_overlap:
        adjusted += 0.07
        reasons.append(f"buyer_overlap={','.join(buyer_overlap)}")
    if cluster["main"] == "serving_photo":
        adjusted -= 0.02
        reasons.append("soft_boundary=serving_photo")
    if cluster["main"] in _LOWER_PRIORITY_CLASSES:
        adjusted -= 0.05
        reasons.append(f"lower_priority={cluster['main']}")
    elif cluster_classes.intersection(_LOWER_PRIORITY_CLASSES):
        adjusted -= 0.02
        reasons.append("lower_priority_secondary")
    return round(adjusted, 4), "; ".join(reasons)


def _canonical_query_key(query: str) -> str:
    normalized = str(query or "").casefold().strip()
    normalized = re.sub(r"\b\d+\s*(мл|л|см|шт|лист(?:ов|а)?)\b", r"<num_\1>", normalized)
    normalized = re.sub(r"\b(набор|комплект)\b", "<set>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _light_token_key(token: str) -> str:
    value = str(token or "").lower().replace("ё", "е")
    value = re.sub(r"[^0-9a-zа-я]+", "", value)
    if len(value) <= 3:
        return value
    for suffix in ("ыми", "ими", "ого", "ему", "ому", "ыми", "ими", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ей", "ую", "юю"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    for suffix in ("ами", "ями", "ов", "ев", "ей"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[: -len(suffix)]
    if value.endswith(("ы", "и", "а", "я")) and len(value) >= 5:
        return value[:-1]
    return value


def _query_content_tokens(query: str) -> list[str]:
    normalized = _canonical_query_key(query)
    raw_tokens = [token for token in re.split(r"\s+", normalized) if token]
    return [_light_token_key(token) for token in raw_tokens if token not in _LOW_VALUE_QUERY_STOPWORDS]


def _query_token_set_key(query: str) -> str:
    tokens = sorted(set(_query_content_tokens(query)))
    return " ".join(tokens)


def _query_number_bucket(query: str) -> str:
    normalized = _canonical_query_key(query)
    if re.search(r"\b\d+\s*(мл|л|см|шт|лист(?:ов|а)?)\b", normalized):
        return "numeric"
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    if any(token.endswith(("ые", "ие", "ы", "и")) for token in tokens):
        return "plural"
    if any(token.endswith(("ая", "яя", "ый", "ий", "ое", "ее", "а", "я")) for token in tokens):
        return "singular"
    return "neutral"


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def _query_surface_naturalness(query: str) -> float:
    normalized = _canonical_query_key(query)
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    score = 0.0
    if 2 <= len(tokens) <= 5:
        score += 0.06
    elif len(tokens) >= 7:
        score -= 0.04
    if any(token in {"подарочная", "красивая", "эстетичная", "пинтерест", "прикол"} for token in tokens):
        score += 0.02
    if any(re.search(pattern, normalized) for pattern, _, _ in _SUPPRESS_REGEX_WEIGHTS):
        score -= 0.04
    return score


def _query_motif_buckets(query: str) -> set[str]:
    normalized = _canonical_query_key(query)
    matched: set[str] = set()
    for bucket, patterns in _MOTIF_BUCKETS.items():
        if any(pattern in normalized for pattern in patterns):
            matched.add(bucket)
    return matched


def _query_candidate_rows(*, clusters: list[dict[str, Any]], queries: list[str]) -> list[dict[str, Any]]:
    allowed = {_canonical_query_key(query) for query in queries}
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        family_key = _canonical_query_key(cluster.get("anchor_query") or cluster.get("profile_label_candidate") or cluster.get("cluster_key") or "")
        buyer_origin = str(cluster.get("main") or "")
        for query in [cluster.get("anchor_query") or "", *(cluster.get("representative_queries") or [])]:
            query_value = str(query or "").strip()
            if not query_value:
                continue
            normalized = _canonical_query_key(query_value)
            if normalized not in allowed:
                continue
            rows.append(
                {
                    "query": query_value,
                    "normalized": normalized,
                    "canonical_key": _query_token_set_key(query_value),
                    "token_set": set(_query_content_tokens(query_value)),
                    "number_bucket": _query_number_bucket(query_value),
                    "family_key": family_key,
                    "cluster_key": cluster.get("cluster_key") or "",
                    "cleanup_score": float(cluster.get("cleanup_score") or cluster.get("adjusted_similarity") or 0.0),
                    "naturalness": _query_surface_naturalness(query_value),
                    "motifs": _query_motif_buckets(query_value),
                    "buyer_origin": buyer_origin,
                }
            )
    rows.sort(
        key=lambda item: (
            -(item["cleanup_score"] + item["naturalness"]),
            len(item["query"]),
            item["query"],
        )
    )
    return rows


def _dedupe_queries(top_clusters: list[dict[str, Any]], *, max_queries: int = 50) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for cluster in top_clusters:
        for query in [cluster.get("anchor_query") or "", *(cluster.get("representative_queries") or [])]:
            query_value = str(query or "").strip()
            if not query_value:
                continue
            normalized = _canonical_query_key(query_value)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(query_value)
            if len(result) >= max_queries:
                return result
    return result


def _buyer_overlap_for_cluster(*, sku_meaning: dict[str, Any], cluster: dict[str, Any]) -> list[str]:
    sku_classes = {sku_meaning["main"], *(sku_meaning.get("secondary") or [])}
    cluster_classes = {cluster["main"], *(cluster.get("secondary") or [])}
    return sorted(_BUYER_CLASSES.intersection(sku_classes).intersection(cluster_classes))


def _query_suppress_penalty(query: str) -> tuple[float, list[str]]:
    text_value = str(query or "").lower()
    penalty = 0.0
    hits: list[str] = []
    for pattern, weight, label in _SUPPRESS_REGEX_WEIGHTS:
        if re.search(pattern, text_value):
            penalty += weight
            hits.append(label)
    return min(0.35, round(penalty, 4)), hits


def _cluster_cleanup_metadata(*, cluster: dict[str, Any], sku_meaning: dict[str, Any]) -> dict[str, Any]:
    buyer_overlap = _buyer_overlap_for_cluster(sku_meaning=sku_meaning, cluster=cluster)
    main = str(cluster.get("main") or "")
    secondary = list(cluster.get("secondary") or [])
    if (main in _BUYER_MAIN_CLASSES and buyer_overlap) or (main in _BUYER_MAIN_CLASSES and float(cluster.get("adjusted_similarity") or 0.0) >= 0.58):
        tier = "keep_high"
    elif main in {"serving_photo", "audience_kids"} or buyer_overlap or any(item in _BUYER_MAIN_CLASSES for item in secondary):
        tier = "keep_soft"
    else:
        tier = "fallback_only"

    cluster_queries = [cluster.get("anchor_query") or "", *(cluster.get("representative_queries") or [])]
    per_query_penalties = []
    suppress_hits: set[str] = set()
    for query in cluster_queries:
        penalty, hits = _query_suppress_penalty(str(query or ""))
        if str(query or "").strip():
            per_query_penalties.append(penalty)
        suppress_hits.update(hits)
    suppress_penalty = max(per_query_penalties) if per_query_penalties else 0.0

    cleanup_score = float(cluster.get("adjusted_similarity") or 0.0)
    if main in _BUYER_MAIN_CLASSES:
        cleanup_score += 0.10
    elif main == "serving_photo":
        cleanup_score += 0.02
    if buyer_overlap:
        cleanup_score += 0.05
    if main == "functional":
        cleanup_score -= 0.12
    elif main == "generic":
        cleanup_score -= 0.10
    elif main == "format_set":
        cleanup_score -= 0.15
    elif main == "size":
        cleanup_score -= 0.15
    cleanup_score -= suppress_penalty

    cluster_copy = dict(cluster)
    cluster_copy["buyer_overlap"] = buyer_overlap
    cluster_copy["cleanup_tier"] = tier
    cluster_copy["cleanup_score"] = round(cleanup_score, 4)
    cluster_copy["suppress_penalty"] = suppress_penalty
    cluster_copy["suppress_hits"] = sorted(suppress_hits)
    return cluster_copy


def _cleanup_selected_clusters(*, top_clusters: list[dict[str, Any]], sku_meaning: dict[str, Any]) -> dict[str, Any]:
    before_queries = _dedupe_queries(top_clusters, max_queries=50)
    annotated = [_cluster_cleanup_metadata(cluster=cluster, sku_meaning=sku_meaning) for cluster in top_clusters]
    annotated.sort(
        key=lambda item: (
            {"keep_high": 0, "keep_soft": 1, "fallback_only": 2}[str(item.get("cleanup_tier") or "fallback_only")],
            -float(item.get("cleanup_score") or 0.0),
            -float(item.get("confidence") or 0.0),
            item.get("cluster_key") or "",
        )
    )

    tier1_clusters = [item for item in annotated if item["cleanup_tier"] == "keep_high"]
    tier1_queries = _dedupe_queries(tier1_clusters, max_queries=50)
    buyer_pool_sufficient = len(tier1_clusters) >= 8 or len(tier1_queries) >= 15

    final_clusters: list[dict[str, Any]] = []
    soft_limit = 4 if buyer_pool_sufficient else 8
    fallback_limit = 0 if buyer_pool_sufficient else 8
    soft_used = 0
    fallback_used = 0
    for cluster in annotated:
        tier = cluster["cleanup_tier"]
        if tier == "keep_high":
            final_clusters.append(cluster)
            continue
        if tier == "keep_soft":
            if soft_used >= soft_limit:
                continue
            soft_used += 1
            final_clusters.append(cluster)
            continue
        if fallback_used >= fallback_limit:
            continue
        fallback_used += 1
        final_clusters.append(cluster)

    final_clusters.sort(key=lambda item: (-float(item.get("cleanup_score") or 0.0), -float(item.get("confidence") or 0.0), item.get("cluster_key") or ""))

    result_queries: list[str] = []
    seen: set[str] = set()
    removed_queries: list[str] = []
    soft_query_limit = 10 if buyer_pool_sufficient else 16
    fallback_query_limit = 0 if buyer_pool_sufficient else 12
    soft_query_count = 0
    fallback_query_count = 0

    for cluster in final_clusters:
        tier = cluster["cleanup_tier"]
        for query in [cluster.get("anchor_query") or "", *(cluster.get("representative_queries") or [])]:
            query_value = str(query or "").strip()
            if not query_value:
                continue
            query_penalty, _ = _query_suppress_penalty(query_value)
            if buyer_pool_sufficient and query_penalty >= 0.18:
                removed_queries.append(query_value)
                continue
            if not buyer_pool_sufficient and query_penalty >= 0.25 and len(result_queries) >= 10:
                removed_queries.append(query_value)
                continue
            if tier == "keep_soft" and soft_query_count >= soft_query_limit:
                removed_queries.append(query_value)
                continue
            if tier == "fallback_only" and fallback_query_count >= fallback_query_limit:
                removed_queries.append(query_value)
                continue

            normalized = _canonical_query_key(query_value)
            if normalized in seen:
                removed_queries.append(query_value)
                continue
            seen.add(normalized)
            result_queries.append(query_value)
            if tier == "keep_soft":
                soft_query_count += 1
            elif tier == "fallback_only":
                fallback_query_count += 1
            if len(result_queries) >= 40:
                break
        if len(result_queries) >= 40:
            break

    if buyer_pool_sufficient and soft_query_count <= max(4, len(result_queries) // 3):
        retrieval_quality = "strong_buyer_meaning"
    elif len(tier1_queries) >= 5:
        retrieval_quality = "mixed"
    else:
        retrieval_quality = "functional_fallback"

    return {
        "before_queries": before_queries,
        "final_clusters": final_clusters[:30],
        "final_queries": result_queries,
        "removed_queries": removed_queries[:30],
        "buyer_pool_sufficient": buyer_pool_sufficient,
        "retrieval_quality": retrieval_quality,
        "tier_counts": {
            "keep_high": len(tier1_clusters),
            "keep_soft": sum(1 for item in annotated if item["cleanup_tier"] == "keep_soft"),
            "fallback_only": sum(1 for item in annotated if item["cleanup_tier"] == "fallback_only"),
        },
    }


def _collapse_near_duplicate_queries(*, clusters: list[dict[str, Any]], queries: list[str]) -> dict[str, Any]:
    candidates = _query_candidate_rows(clusters=clusters, queries=queries)

    groups: list[dict[str, Any]] = []
    for candidate in candidates:
        placed = False
        for group in groups:
            group_token_set = group["token_set"]
            same_canonical = candidate["canonical_key"] == group["canonical_key"]
            high_overlap = _jaccard_similarity(candidate["token_set"], group_token_set) >= 0.8
            same_family_pattern = candidate["family_key"] == group["family_key"] and _jaccard_similarity(candidate["token_set"], group_token_set) >= 0.67
            if same_canonical or high_overlap or same_family_pattern:
                group["members"].append(candidate)
                group["token_set"] = group_token_set.union(candidate["token_set"])
                placed = True
                break
        if not placed:
            groups.append(
                {
                    "canonical_key": candidate["canonical_key"],
                    "token_set": set(candidate["token_set"]),
                    "family_key": candidate["family_key"],
                    "members": [candidate],
                }
            )

    selected: list[str] = []
    selected_norms: set[str] = set()
    family_counts: dict[str, int] = {}
    collapsed_groups = 0
    for group in groups:
        members = sorted(
            group["members"],
            key=lambda item: (
                -(item["cleanup_score"] + item["naturalness"]),
                len(item["query"]),
                item["query"],
            ),
        )
        if len(members) > 1:
            collapsed_groups += 1
        chosen: list[dict[str, Any]] = []
        number_buckets_seen: set[str] = set()
        for member in members:
            if member["normalized"] in selected_norms:
                continue
            if family_counts.get(member["family_key"], 0) >= 3:
                continue
            if not chosen:
                chosen.append(member)
                number_buckets_seen.add(member["number_bucket"])
                continue
            if len(chosen) >= 2:
                continue
            if member["number_bucket"] not in number_buckets_seen and member["canonical_key"] != chosen[0]["canonical_key"]:
                chosen.append(member)
                number_buckets_seen.add(member["number_bucket"])
        for member in chosen:
            selected.append(member["query"])
            selected_norms.add(member["normalized"])
            family_counts[member["family_key"]] = family_counts.get(member["family_key"], 0) + 1
            if len(selected) >= 35:
                break
        if len(selected) >= 35:
            break

    return {
        "final_queries": selected,
        "collapsed_group_count": collapsed_groups,
    }


def _collapse_family_level_queries(*, clusters: list[dict[str, Any]], queries: list[str]) -> dict[str, Any]:
    candidates = _query_candidate_rows(clusters=clusters, queries=queries)
    groups: list[dict[str, Any]] = []
    for candidate in candidates:
        placed = False
        for group in groups:
            checks = 0
            if _jaccard_similarity(candidate["token_set"], group["token_set"]) >= 0.55:
                checks += 1
            if candidate["motifs"] and group["motifs"] and candidate["motifs"].intersection(group["motifs"]):
                checks += 1
            if candidate["family_key"] == group["family_key"]:
                checks += 1
            if candidate["buyer_origin"] == group["buyer_origin"]:
                checks += 1
            if candidate["canonical_key"] == group["canonical_key"]:
                checks += 1
            if checks >= 2:
                group["members"].append(candidate)
                group["token_set"] = group["token_set"].union(candidate["token_set"])
                group["motifs"] = group["motifs"].union(candidate["motifs"])
                placed = True
                break
        if not placed:
            groups.append(
                {
                    "canonical_key": candidate["canonical_key"],
                    "family_key": candidate["family_key"],
                    "token_set": set(candidate["token_set"]),
                    "motifs": set(candidate["motifs"]),
                    "buyer_origin": candidate["buyer_origin"],
                    "members": [candidate],
                }
            )

    for group in groups:
        members = group["members"]
        best_score = max(member["cleanup_score"] for member in members)
        diversity_bonus = min(0.06, 0.02 * len({bucket for member in members for bucket in member["motifs"]}))
        buyer_bonus = 0.06 if group["buyer_origin"] in _BUYER_MAIN_CLASSES else 0.02 if group["buyer_origin"] in _BUYER_CLASSES else 0.0
        narrow_penalty = -0.03 if all(len(member["query"].split()) >= 6 for member in members[:2]) else 0.0
        group["family_score"] = round(best_score + diversity_bonus + buyer_bonus + narrow_penalty, 4)

    groups.sort(key=lambda item: (-float(item["family_score"]), len(item["members"]), item["family_key"]))
    selected_queries: list[str] = []
    collapsed_families: list[dict[str, Any]] = []
    family_limit = 12
    for group in groups[:family_limit]:
        members = sorted(
            group["members"],
            key=lambda item: (
                -(item["cleanup_score"] + item["naturalness"]),
                len(item["query"]),
                item["query"],
            ),
        )
        chosen: list[dict[str, Any]] = []
        motif_union: set[str] = set()
        for member in members:
            if not chosen:
                chosen.append(member)
                motif_union = set(member["motifs"])
                continue
            if len(chosen) >= 2:
                continue
            first = chosen[0]
            overlap_with_first = _jaccard_similarity(member["token_set"], first["token_set"])
            if (
                member["motifs"] - motif_union
                or member["number_bucket"] != first["number_bucket"]
                or overlap_with_first < 0.8
            ):
                chosen.append(member)
                motif_union.update(member["motifs"])
        selected_queries.extend(member["query"] for member in chosen)
        collapsed_families.append(
            {
                "family_score": group["family_score"],
                "motifs": sorted(group["motifs"]),
                "members": [member["query"] for member in members[:6]],
                "selected": [member["query"] for member in chosen],
            }
        )
        if len(selected_queries) >= 28:
            break

    return {
        "final_queries": selected_queries[:28],
        "family_count": len(collapsed_families),
        "collapsed_families": collapsed_families,
    }


def _manual_verdict(final_queries: list[str]) -> dict[str, Any]:
    buyer_hits = [query for query in final_queries if any(pattern in query.lower() for pattern in _BUYER_QUERY_PATTERNS)]
    leak_hits = [query for query in final_queries if any(pattern in query.lower() for pattern in _GENERIC_LEAK_PATTERNS)]
    if len(buyer_hits) >= max(5, len(leak_hits) * 2):
        verdict = "looks right"
    elif len(buyer_hits) > len(leak_hits):
        verdict = "mixed"
    else:
        verdict = "mostly wrong"
    return {"verdict": verdict, "what_worked": buyer_hits[:8], "what_leaked": leak_hits[:8]}


def _render_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_report(*, output_path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Multi-Category Buyer-Meaning Validation",
        "",
        f"- project_id: `{payload['project_id']}`",
        f"- llm_model: `{payload['llm_model']}`",
        f"- embedding_model: `{payload['embedding_model']}`",
        "",
    ]
    for category in payload["categories"]:
        lines.extend(
            [
                f"## Category: {category['display_name']}",
                "",
                f"- category_id: `{category['category_id']}`",
                f"- query_cluster_sample_size: `{category['query_cluster_sample_size']}`",
                f"- selected_skus: `{[sku['nm_id'] for sku in category['skus']]}`",
                "",
            ]
        )
        if category.get("diagnostic"):
            lines.extend([f"- diagnostic: {category['diagnostic']}", ""])
        for sku in category["skus"]:
            meaning = sku["sku_meaning"]
            lines.extend(
                [
                    f"### SKU `{sku['nm_id']}`",
                    "",
                    f"- title: {sku['title']}",
                    f"- sku_meaning_main: `{meaning['main']}`",
                    f"- sku_meaning_secondary: `{meaning['secondary']}`",
                    f"- confidence: `{meaning['confidence']:.4f}`",
                    f"- degraded_mode: `{sku['degraded_mode']}`",
                    f"- retrieval_quality: `{sku.get('retrieval_quality', 'mixed')}`",
                    f"- reason: {meaning['reason']}",
                    "",
                    "#### Top semantic clusters",
                    "",
                ]
            )
            for cluster in sku["top_clusters"][:20]:
                lines.append(
                    f"- `{cluster['adjusted_similarity']:.4f}` | {cluster['profile_label_candidate'] or '-'} | anchor: {cluster['anchor_query'] or '-'} | meaning={cluster['main']} | {cluster['selection_reason']}"
                )
            lines.extend(
                [
                    "",
                    "#### Cleanup effect",
                    "",
                    f"- top queries before cleanup: {sku.get('final_queries_before_cleanup', [])[:15]}",
                    f"- top queries after cleanup: {sku.get('final_queries_before_dedup', sku['final_queries'])[:15]}",
                    f"- removed by cleanup: {sku.get('cleanup_removed_queries', [])[:15]}",
                    f"- retrieval_quality: `{sku.get('retrieval_quality', 'mixed')}`",
                    "",
                    "#### Dedup effect",
                    "",
                    f"- final queries before dedup collapse: {sku.get('final_queries_before_dedup', sku['final_queries'])[:15]}",
                    f"- final queries after dedup collapse: {sku.get('final_queries_before_family_compression', sku['final_queries'])[:15]}",
                    f"- collapsed groups: `{sku.get('dedup_collapsed_groups', 0)}`",
                    "",
                    "#### Family compression effect",
                    "",
                    f"- final queries after dedup: {sku.get('final_queries_before_family_compression', sku['final_queries'])[:15]}",
                    f"- final queries after family compression: {sku['final_queries'][:15]}",
                    f"- families left: `{sku.get('family_group_count', 0)}`",
                    f"- collapsed families: {sku.get('family_collapsed_examples', [])[:6]}",
                    "",
                    "#### Final query list",
                    "",
                ]
            )
            lines.extend(f"- {query}" for query in sku["final_queries"][:50])
            manual = sku["manual_verdict"]
            lines.extend(
                [
                    "",
                    "#### Human verdict",
                    "",
                    f"- verdict: `{manual['verdict']}`",
                    f"- what_worked: {manual['what_worked']}",
                    f"- what_leaked: {manual['what_leaked']}",
                    f"- what_missing: {sku['what_missing']}",
                    "",
                ]
            )
    summary = payload["cross_category_summary"]
    lines.extend(
        [
            "## Cross-category summary",
            "",
            f"- best_categories: {summary['best_categories']}",
            f"- weak_categories: {summary['weak_categories']}",
            f"- buyer_meaning_friendly_categories: {summary['buyer_meaning_friendly_categories']}",
            f"- functional_collapse_categories: {summary['functional_collapse_categories']}",
            f"- final_verdict: `{summary['final_verdict']}`",
            "",
        ]
    )
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _run_validation(*, project_id: int, llm_model: str, embedding_model: str, sku_limit_per_category: int) -> dict[str, Any]:
    import numpy as np
    import requests
    from sentence_transformers import SentenceTransformer

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment")
    llm_model = os.getenv("OPENROUTER_MODEL") or llm_model

    from app.db import SessionLocal

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_json_path = OUTPUTS_DIR / "multi_category_buyer_meaning_validation.json"
    output_report_path = OUTPUTS_DIR / "multi_category_buyer_meaning_validation_report.md"

    http = requests.Session()
    embedding_model_instance = SentenceTransformer(embedding_model)
    categories_payload: list[dict[str, Any]] = []

    session = SessionLocal()
    try:
        for config in _CATEGORY_CONFIGS:
            resolved_category_id = _resolve_category_id(
                session,
                project_id=project_id,
                configured_id=config.get("category_id"),
                product_type_terms=tuple(config["product_type_terms"]),
            )
            if not resolved_category_id:
                categories_payload.append(
                    {
                        "slug": config["slug"],
                        "display_name": config["display_name"],
                        "category_id": None,
                        "query_cluster_sample_size": 0,
                        "skus": [],
                        "diagnostic": "category_id not found in products",
                    }
                )
                continue

            skus = _pick_skus(
                session,
                project_id=project_id,
                category_id=resolved_category_id,
                preferred_nm_ids=tuple(config.get("preferred_nm_ids") or ()),
                sku_limit=sku_limit_per_category,
            )
            if not skus:
                categories_payload.append(
                    {
                        "slug": config["slug"],
                        "display_name": config["display_name"],
                        "category_id": resolved_category_id,
                        "query_cluster_sample_size": 0,
                        "skus": [],
                        "diagnostic": "no SKU candidates found in products",
                    }
                )
                continue

            labels_path, query_labels = _ensure_query_labels(
                project_id=project_id,
                category_id=resolved_category_id,
                category_slug=config["slug"],
                label_source=str(config["label_source"]),
                query_sample_limit=config.get("query_sample_limit"),
            )
            candidate_clusters: list[dict[str, Any]] = []
            for cluster in query_labels:
                if not _cluster_product_type_guard(cluster, product_type_terms=tuple(config["product_type_terms"])):
                    continue
                if cluster["main"] in _EXCLUDED_CLASSES:
                    continue
                cluster_copy = dict(cluster)
                cluster_copy["meaning_text"] = _cluster_meaning_text(cluster_copy)
                candidate_clusters.append(cluster_copy)

            if not candidate_clusters:
                categories_payload.append(
                    {
                        "slug": config["slug"],
                        "display_name": config["display_name"],
                        "category_id": resolved_category_id,
                        "query_cluster_sample_size": len(query_labels),
                        "skus": [
                            {
                                "nm_id": sku["nm_id"],
                                "title": sku["title"],
                                "description": sku["description"],
                                "vendor_code": sku["vendor_code"],
                                "reviews": [],
                                "degraded_mode": True,
                                "sku_meaning_input": "",
                                "sku_meaning": {
                                    "main": "generic",
                                    "secondary": [],
                                    "confidence": 0.0,
                                    "reason": "query-side sample for this category is empty, retrieval skipped",
                                },
                                "top_clusters": [],
                                "final_queries": [],
                                "manual_verdict": {"verdict": "mostly wrong", "what_worked": [], "what_leaked": []},
                                "what_missing": ["query-side cluster profiles not available"],
                            }
                            for sku in skus
                        ],
                        "diagnostic": f"no candidate clusters after filter; labels source={labels_path}",
                    }
                )
                continue

            cluster_embeddings = embedding_model_instance.encode(
                [cluster["meaning_text"] for cluster in candidate_clusters],
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            cluster_embeddings = np.asarray(cluster_embeddings, dtype="float32")

            category_result = {
                "slug": config["slug"],
                "display_name": config["display_name"],
                "category_id": resolved_category_id,
                "query_cluster_sample_size": len(query_labels),
                "query_labels_source": str(labels_path),
                "skus": [],
            }

            for sku in skus:
                reviews = _collect_reviews(session, project_id=project_id, nm_id=int(sku["nm_id"]), limit=30)
                meaning_input = _sku_meaning_input(title=sku["title"], description=sku["description"], reviews=reviews)
                sku_meaning = _classify_sku_meaning(http, api_key=api_key, model_name=llm_model, sku_meaning_input=meaning_input)
                sku_embedding = embedding_model_instance.encode(
                    [meaning_input],
                    batch_size=1,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                )
                sku_embedding = np.asarray(sku_embedding, dtype="float32")
                similarities = np.matmul(sku_embedding, cluster_embeddings.T)[0]

                ranked_clusters: list[dict[str, Any]] = []
                for index, cluster in enumerate(candidate_clusters):
                    similarity = float(similarities[index])
                    adjusted, reason = _adjusted_similarity(similarity=similarity, sku_meaning=sku_meaning, cluster=cluster)
                    ranked_clusters.append(
                        {
                            "cluster_key": cluster["cluster_key"],
                            "profile_label_candidate": cluster.get("profile_label_candidate") or "",
                            "anchor_query": cluster.get("anchor_query") or "",
                            "representative_queries": list(cluster.get("representative_queries") or []),
                            "main": cluster["main"],
                            "secondary": list(cluster.get("secondary") or []),
                            "confidence": float(cluster.get("confidence") or 0.0),
                            "similarity": round(similarity, 4),
                            "adjusted_similarity": adjusted,
                            "selection_reason": reason,
                        }
                    )
                ranked_clusters.sort(key=lambda item: (-float(item["adjusted_similarity"]), -float(item["confidence"]), item["cluster_key"]))
                raw_top_clusters = ranked_clusters[:40]
                cleanup_result = _cleanup_selected_clusters(top_clusters=raw_top_clusters, sku_meaning=sku_meaning)
                top_clusters = cleanup_result["final_clusters"]
                final_queries_before_dedup = cleanup_result["final_queries"]
                dedup_result = _collapse_near_duplicate_queries(clusters=top_clusters, queries=final_queries_before_dedup)
                final_queries_before_family_compression = dedup_result["final_queries"]
                family_result = _collapse_family_level_queries(clusters=top_clusters, queries=final_queries_before_family_compression)
                final_queries = family_result["final_queries"]
                manual = _manual_verdict(final_queries)
                what_missing: list[str] = []
                if sku_meaning["main"] == "aesthetic" and not any("pinterest" in query.lower() or "красив" in query.lower() for query in final_queries):
                    what_missing.append("мало aesthetic/pinterest-like queries")
                if sku_meaning["main"] == "gift" and not any("подар" in query.lower() for query in final_queries):
                    what_missing.append("почти нет gift-like queries")
                if sku_meaning["main"] == "fun_meme" and not any("прикол" in query.lower() or "мем" in query.lower() or "надпис" in query.lower() for query in final_queries):
                    what_missing.append("слабый fun_meme слой")
                if not what_missing:
                    what_missing.append("явных missing-patterns не выявлено")

                category_result["skus"].append(
                    {
                        "nm_id": sku["nm_id"],
                        "title": sku["title"],
                        "description": sku["description"],
                        "vendor_code": sku["vendor_code"],
                        "reviews": reviews,
                        "degraded_mode": not bool(reviews),
                        "sku_meaning_input": meaning_input,
                        "sku_meaning": sku_meaning,
                        "raw_top_clusters": raw_top_clusters[:20],
                        "top_clusters": top_clusters,
                        "final_queries_before_cleanup": cleanup_result["before_queries"],
                        "final_queries_before_dedup": final_queries_before_dedup,
                        "final_queries_before_family_compression": final_queries_before_family_compression,
                        "final_queries": final_queries,
                        "cleanup_removed_queries": cleanup_result["removed_queries"],
                        "dedup_collapsed_groups": dedup_result["collapsed_group_count"],
                        "family_group_count": family_result["family_count"],
                        "family_collapsed_examples": family_result["collapsed_families"],
                        "retrieval_quality": cleanup_result["retrieval_quality"],
                        "buyer_pool_sufficient": cleanup_result["buyer_pool_sufficient"],
                        "cleanup_tier_counts": cleanup_result["tier_counts"],
                        "manual_verdict": manual,
                        "what_missing": what_missing,
                    }
                )
            categories_payload.append(category_result)
    finally:
        session.close()

    verdict_counts = Counter(sku["manual_verdict"]["verdict"] for category in categories_payload for sku in category.get("skus", []))
    best_categories = [category["display_name"] for category in categories_payload if any(sku["manual_verdict"]["verdict"] == "looks right" for sku in category.get("skus", []))]
    weak_categories = [category["display_name"] for category in categories_payload if category.get("skus") and all(sku["manual_verdict"]["verdict"] != "looks right" for sku in category.get("skus", []))]
    categories_with_queries = sum(1 for category in categories_payload if category.get("query_cluster_sample_size", 0) > 0 and category.get("skus"))
    if categories_with_queries <= 1:
        final_verdict = "category-dependent"
    elif verdict_counts["looks right"] >= 4:
        final_verdict = "transferable"
    elif verdict_counts["looks right"] >= 2:
        final_verdict = "partially transferable"
    elif verdict_counts["mixed"] > 0:
        final_verdict = "category-dependent"
    else:
        final_verdict = "not transferable"

    payload = {
        "project_id": project_id,
        "llm_model": llm_model,
        "embedding_model": embedding_model,
        "categories": categories_payload,
        "cross_category_summary": {
            "best_categories": best_categories,
            "weak_categories": weak_categories,
            "buyer_meaning_friendly_categories": best_categories,
            "functional_collapse_categories": [
                category["display_name"]
                for category in categories_payload
                if any(
                    query
                    for sku in category.get("skus", [])
                    for query in sku["manual_verdict"]["what_leaked"]
                    if any(pattern in query.lower() for pattern in ("суп", "набор", "шт", "см"))
                )
            ],
            "verdict_counts": dict(verdict_counts),
            "final_verdict": final_verdict,
        },
    }
    _render_json(OUTPUTS_DIR / "multi_category_buyer_meaning_validation.json", payload)
    _build_report(output_path=OUTPUTS_DIR / "multi_category_buyer_meaning_validation_report.md", payload=payload)
    return {
        "output_json_path": str(OUTPUTS_DIR / "multi_category_buyer_meaning_validation.json"),
        "output_report_path": str(OUTPUTS_DIR / "multi_category_buyer_meaning_validation_report.md"),
        "final_verdict": final_verdict,
    }


def main() -> int:
    if _should_reroute_to_docker():
        return _rerun_in_worker_container(sys.argv[1:])
    sys.path.insert(0, str(SRC_ROOT))
    parser = argparse.ArgumentParser(description="Multi-category buyer-meaning validation spike")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--llm-model", default=_DEFAULT_LLM_MODEL, help="OpenRouter model for SKU meaning")
    parser.add_argument("--embedding-model", default=_DEFAULT_EMBEDDING_MODEL, help="Sentence embedding model")
    parser.add_argument("--sku-limit-per-category", type=int, default=2, help="How many SKU samples per category")
    args = parser.parse_args()
    summary = _run_validation(
        project_id=args.project_id,
        llm_model=str(args.llm_model),
        embedding_model=str(args.embedding_model),
        sku_limit_per_category=max(1, min(2, int(args.sku_limit_per_category))),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
