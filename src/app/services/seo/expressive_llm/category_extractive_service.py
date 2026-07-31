"""Offline category expressive extraction service (single-category, cache-first)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.seo.expressive_llm.category_input_builder import CategoryExpressiveInput, build_category_expressive_input
from app.services.seo.expressive_llm.category_output_parser import parse_and_validate_category_expressive_output
from app.services.seo.expressive_llm.reviews_source import fetch_category_review_scope
from app.services.seo.expressive_llm.storage import (
    CategoryExpressiveCacheKey,
    CategoryExpressiveStore,
    StoredCategoryExpressiveArtifact,
)
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse
from app.services.seo.providers.openrouter import OpenRouterProvider


SYSTEM_PROMPT_V1 = (
    "Ты извлекаешь expressive meaning (vibes) категории из отзывов покупателей.\n"
    "Работай строго по evidence.\n"
    "Запрещено:\n"
    "- возвращать generic labels: \"positive\", \"good\", \"quality\"\n"
    "- возвращать функциональные признаки (тип товара, материал, объём и т.п.)\n"
    "Если сигналов нет — верни пустой список.\n"
    "Ответ только валидный JSON.\n"
)

SYSTEM_PROMPT_V2 = (
    "Ты извлекаешь expressive meaning (vibes) категории из отзывов покупателей.\n"
    "Работай строго по evidence.\n"
    "Запрещено:\n"
    "- возвращать generic labels: \"positive\", \"good\", \"quality\"\n"
    "- возвращать функциональные признаки (тип товара, материал, объём и т.п.)\n"
    "- объединять разные стили/эстетики в один vibe\n"
    "Если сигналов недостаточно — верни меньше vibes (не выдумывай).\n"
    "Ответ только валидный JSON.\n"
)

SYSTEM_PROMPT_V3 = (
    "Ты извлекаешь expressive meaning (vibes) категории из отзывов покупателей.\n"
    "Работай строго по evidence.\n"
    "\n"
    "КРИТИЧНО: evidence_spans должны быть ТОЧНЫМИ подстроками из reviews[] (copy-paste).\n"
    "Если ты не можешь подобрать 2–3 точные цитаты из reviews[] для vibe — НЕ возвращай этот vibe.\n"
    "\n"
    "Запрещено:\n"
    "- возвращать generic labels: \"positive\", \"good\", \"quality\"\n"
    "- возвращать функциональные признаки (тип товара, материал, объём и т.п.)\n"
    "- объединять разные стили/эстетики в один vibe\n"
    "- опираться на упаковку/доставку/сколы/брак/возвраты как на \"vibe\"\n"
    "\n"
    "Если сигналов недостаточно — верни меньше vibes (не выдумывай).\n"
    "Ответ только валидный JSON.\n"
)


def _user_prompt_v1(*, payload: dict[str, Any]) -> str:
    # Keep prompt compact; payload is JSON-dumped without pretty indent to reduce tokens.
    return (
        "Вход:\n"
        "- category_name\n"
        "- reviews[] (основной источник)\n"
        "- titles[] (вторичный контекст, если присутствует)\n\n"
        "Задача:\n"
        "Верни 3–5 выразительных (perceptual) vibes категории.\n\n"
        "Требования:\n"
        "- Используй только тексты отзывов как источник (reviews primary)\n"
        "- titles — вторичный контекст; выводы не могут основываться только на titles\n"
        "- Каждый vibe должен иметь:\n"
        "  - label (короткое имя)\n"
        "  - confidence (0–1)\n"
        "  - evidence_spans (РОВНО 2–3 короткие цитаты из отзывов, ≤80 символов)\n"
        "- Не более 5 vibes\n"
        "- Если недостаточно данных — возвращай меньше vibes или пустой список\n\n"
        "Схема ответа:\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        '  "category_name": "<CATEGORY_NAME>",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "...",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["...", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "summary": ""\n'
        "}\n\n"
        "INPUT_JSON:\n"
        + __import__("json").dumps(payload, ensure_ascii=False)
    )

def _user_prompt_v2(*, payload: dict[str, Any]) -> str:
    return (
        "Вход:\n"
        "- category_name\n"
        "- reviews[] (основной источник)\n"
        "- titles[] (вторичный контекст, если присутствует)\n\n"
        "Задача:\n"
        "Верни expressive vibes категории.\n\n"
        "Требования:\n"
        "- Используй только тексты отзывов как источник (reviews primary)\n"
        "- titles — вторичный контекст; выводы не могут основываться только на titles\n"
        "- Запрещены generic labels: \"positive\", \"good\", \"quality\"\n"
        "- Не объединяй разные стили в один vibe\n"
        "- Количество vibes: от 3 до 8, но если недостаточно сигналов — верни меньше (не выдумывай)\n"
        "- Каждый vibe должен иметь:\n"
        "  - label (короткое имя)\n"
        "  - confidence (0–1)\n"
        "  - evidence_spans (РОВНО 2–3 короткие цитаты из отзывов, ≤80 символов)\n\n"
        "Схема ответа:\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        '  "category_name": "<CATEGORY_NAME>",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "...",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["...", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "summary": ""\n'
        "}\n\n"
        "INPUT_JSON:\n"
        + __import__("json").dumps(payload, ensure_ascii=False)
    )

def _user_prompt_v3(*, payload: dict[str, Any]) -> str:
    return (
        "Вход:\n"
        "- category_name\n"
        "- reviews[] (основной источник)\n"
        "- titles[] (вторичный контекст, если присутствует)\n\n"
        "Задача:\n"
        "Верни expressive vibes категории.\n\n"
        "Требования:\n"
        "- Используй только reviews[] как источник evidence\n"
        "- titles — вторичный контекст; выводы не могут основываться только на titles\n"
        "- Количество vibes: от 3 до 8; если сигналов достаточно — постарайся вернуть 6–8, но если недостаточно — верни меньше (не выдумывай)\n"
        "- Каждый vibe должен иметь:\n"
        "  - label (короткое, не общее слово/фраза)\n"
        "  - confidence (0–1)\n"
        "  - evidence_spans (РОВНО 2–3 короткие цитаты из reviews[], ≤80 символов)\n"
        "- evidence_spans должны быть ТОЧНЫМИ подстроками из reviews[] (copy-paste, без перефраза)\n"
        "- Не объединяй разные стили/эстетики в один vibe\n"
        "- Запрещены generic labels: \"positive\", \"good\", \"quality\"\n"
        "- Игнорируй упаковку/доставку/сколы/брак/возвраты как самостоятельные vibes\n"
        "\n"
        "Схема ответа (строго JSON):\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        '  "category_name": "<CATEGORY_NAME>",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "...",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["...", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "summary": ""\n'
        "}\n\n"
        "SELF-CHECK BEFORE YOU ANSWER:\n"
        "- Для КАЖДОГО vibe: убедись, что каждый evidence_span встречается в reviews[] дословно.\n"
        "- Если не встречается — удали vibe целиком или замени evidence_spans на найденные.\n\n"
        "INPUT_JSON:\n"
        + __import__("json").dumps(payload, ensure_ascii=False)
    )


def _extract_cost_usd(raw_response: Mapping[str, Any] | None) -> float | None:
    if not isinstance(raw_response, Mapping):
        return None
    usage = raw_response.get("usage")
    if not isinstance(usage, Mapping) and isinstance(raw_response.get("raw_response"), Mapping):
        usage = raw_response.get("raw_response", {}).get("usage")
    if not isinstance(usage, Mapping):
        return None
    cost = usage.get("cost")
    try:
        return float(cost) if cost is not None else None
    except Exception:
        return None


def _write_json(path, payload: Any) -> None:  # noqa: ANN001
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class CategoryExpressiveRunResult:
    cache_hit: bool
    model: str
    latency_ms: int | None
    cost_usd: float | None

    input: CategoryExpressiveInput
    artifact: StoredCategoryExpressiveArtifact

    validation: dict[str, Any]


def _fetch_titles_for_nm_ids(session: Session, *, project_id: int, nm_ids: Sequence[int]) -> list[str]:
    if not nm_ids:
        return []
    sql = (
        text(
        """
        SELECT p.title
        FROM v_wb_product_source p
        WHERE p.project_id = :project_id
          AND p.nm_id IN :nm_ids
          AND p.title IS NOT NULL
        ORDER BY p.nm_id
        """
    )
        .bindparams(bindparam("nm_ids", expanding=True))
    )
    rows = session.execute(sql, {"project_id": int(project_id), "nm_ids": [int(x) for x in nm_ids]}).all()
    return [str(row[0]) for row in rows if row and row[0] is not None]


def _resolve_provider(*, provider: ChatProvider | None, model: str, timeout_seconds: float) -> ChatProvider:
    if provider is not None:
        return provider
    return OpenRouterProvider(chat_model=str(model), timeout_seconds=float(timeout_seconds))


def run_single_category_expressive_extraction(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    model: str = "openai/gpt-4.1-mini",
    prompt_version: str = "v1",
    min_rating: int = 4,
    max_reviews: int = 100,
    include_titles: bool = True,
    temperature: float = 0.0,
    top_p: float = 1.0,
    max_tokens: int = 900,
    timeout_seconds: float = 60.0,
    store: CategoryExpressiveStore | None = None,
    provider: ChatProvider | None = None,
    overwrite_cache: bool = False,
) -> CategoryExpressiveRunResult:
    """Run a single-category offline extraction (cache-first).

    This function MUST NOT be used in runtime hot paths.
    """

    resolved_store = store or CategoryExpressiveStore()

    scope = fetch_category_review_scope(
        session,
        project_id=int(project_id),
        category_id=int(category_id),
        min_rating=int(min_rating),
        limit=5000,
    )

    category_name = scope.category_name or f"category_{int(category_id)}"
    titles: list[str] = []
    if include_titles:
        titles = _fetch_titles_for_nm_ids(session, project_id=int(project_id), nm_ids=scope.nm_ids)

    built = build_category_expressive_input(
        category_name=category_name,
        reviews=scope.review_snippets,
        titles=titles if include_titles else None,
        max_reviews=int(max_reviews),
    )

    key = CategoryExpressiveCacheKey(
        project_id=int(project_id),
        category_id=int(category_id),
        model=str(model),
        prompt_version=str(prompt_version),
        input_hash=str(built.input_hash),
    )

    cached = resolved_store.get(key=key)
    if cached is not None and cached.parsed is not None and cached.validation is not None:
        return CategoryExpressiveRunResult(
            cache_hit=True,
            model=str(model),
            latency_ms=None,
            cost_usd=_extract_cost_usd(cached.raw_response),
            input=built,
            artifact=cached,
            validation=dict(cached.validation) if isinstance(cached.validation, dict) else {"validation": cached.validation},
        )

    resolved_provider = _resolve_provider(provider=provider, model=str(model), timeout_seconds=float(timeout_seconds))

    resolved_pv = str(prompt_version).strip()
    if resolved_pv == "v3":
        system_prompt = SYSTEM_PROMPT_V3
        user_prompt = _user_prompt_v3(payload=built.payload)
        max_vibes = 8
    elif resolved_pv == "v2":
        system_prompt = SYSTEM_PROMPT_V2
        user_prompt = _user_prompt_v2(payload=built.payload)
        max_vibes = 8
    else:
        system_prompt = SYSTEM_PROMPT_V1
        user_prompt = _user_prompt_v1(payload=built.payload)
        max_vibes = 5

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    # Persist exact input (payload + prompts) for auditability, even if parsing later fails.
    planned_dir = resolved_store.artifact_dir_for_key(key=key)
    _write_json(planned_dir / "input_payload.json", built.payload)
    _write_json(planned_dir / "llm_messages.json", [{"role": m.role, "content": m.content} for m in messages])
    prompt_chars = sum(len(str(m.content or "")) for m in messages)
    prompt_tokens_est = int((prompt_chars + 3) / 4)

    t0 = time.time()
    resp: ChatResponse = resolved_provider.generate_chat(
        messages,
        temperature=float(temperature),
        top_p=float(top_p),
        max_tokens=int(max_tokens),
    )
    latency_ms = int((time.time() - t0) * 1000)

    parsed = parse_and_validate_category_expressive_output(
        content=str(resp.content or ""),
        evidence_text=str(built.evidence_text or ""),
        max_vibes=int(max_vibes),
        strict=False,
    )

    validation_dict = asdict(parsed.validation)
    raw_payload = {
        "model": str(resp.model),
        "latency_ms": int(latency_ms),
        "raw_response": dict(resp.raw_response or {}),
        "content": str(resp.content or ""),
    }

    artifact = resolved_store.put(
        key=key,
        raw_response=raw_payload,
        parsed=dict(parsed.parsed),
        validation=validation_dict,
        overwrite=bool(overwrite_cache),
        extra_meta={
            "category_name": category_name,
            "reviews_count": int(built.reviews_count),
            "titles_count": int(built.titles_count),
            "prompt_chars": int(prompt_chars),
            "prompt_tokens_est": int(prompt_tokens_est),
        },
    )

    return CategoryExpressiveRunResult(
        cache_hit=False,
        model=str(resp.model),
        latency_ms=int(latency_ms),
        cost_usd=_extract_cost_usd(resp.raw_response),
        input=built,
        artifact=artifact,
        validation=validation_dict,
    )
