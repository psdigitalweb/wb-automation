#!/usr/bin/env python3
"""Offline evaluation spike: LLM-based expressive meaning extraction.

This is a research/evaluation path ONLY:
- no runtime integration
- no matcher/scoring changes
- no deterministic extraction rule changes

Runs inside docker-compose `api` container by default (DB + providers available).
"""

from __future__ import annotations

import argparse
import hashlib
import httpx
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.seo.meaning_extraction import build_category_meaning, build_product_projection, formalize_query_meaning
from app.services.seo.providers.base import ChatMessage
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.query_pipeline.clustering import get_query_clusters
from app.services.seo.query_pipeline.profiles import run_query_profile_extraction


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "docs" / "seo-module" / "datasets" / "wb_project_1_expressive_eval_v1.json"
PROMPT_VERSION = "v1"


def _default_outputs_root() -> Path:
    """
    Prefer a persistent docker volume path when available (INTERNAL_DATA_DIR),
    otherwise fall back to repo-local outputs/.
    """
    internal = os.getenv("INTERNAL_DATA_DIR", "").strip()
    if internal:
        return Path(internal) / "expressive_llm_eval"
    return PROJECT_ROOT / "outputs" / "expressive_llm_eval"


DEFAULT_OUTPUTS_ROOT = _default_outputs_root()


DEFAULT_MODELS = [
    "openai/gpt-5.4",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o-mini",
]


EXPRESSIVE_RE = re.compile(
    r"(подар|подароч|надпись|принт|с\s*принтом|мем|прикол|cute|kawaii|aesthetic|эстет|минимал|minimal|пинтерест|pinterest|аниме|роман|love|сердц|\bмилый\b|\bмилая\b|\bмилое\b|\bмилые\b)",
    re.IGNORECASE,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_model_dir(model_id: str) -> str:
    return str(model_id).replace("/", "__").replace(":", "_")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _approx_tokens_from_chars(chars: int) -> int:
    # Heuristic (safe-ish): ~4 chars per token for mixed RU/EN text.
    return int(math.ceil(max(0, int(chars)) / 4.0))


@dataclass(frozen=True)
class HardGuards:
    max_categories: int
    max_models: int
    max_skus_per_category: int
    max_clusters_per_category: int
    max_requests_total: int
    max_input_chars: int
    max_runtime_minutes: float
    max_cost_usd: float
    stop_on_budget_exceeded: bool


@dataclass
class BudgetState:
    started_ms: int
    requests_made: int = 0
    cost_usd: float = 0.0
    cache_hits: int = 0

    def elapsed_minutes(self) -> float:
        return (_now_ms() - int(self.started_ms)) / 1000.0 / 60.0


@dataclass(frozen=True)
class PromptLimits:
    category_max_sku_titles: int
    category_max_query_examples: int
    category_max_title_chars: int
    category_max_query_chars: int
    sku_max_title_chars: int
    sku_max_description_chars: int
    sku_max_attributes_chars: int
    query_max_member_queries: int
    query_max_query_chars: int
    query_max_label_chars: int


@dataclass(frozen=True)
class Pricing:
    prompt_usd_per_token: float
    completion_usd_per_token: float


def _compute_cost_usd(*, pricing: Pricing | None, usage: dict[str, Any]) -> float | None:
    if pricing is None:
        return None
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return float(prompt_tokens) * pricing.prompt_usd_per_token + float(completion_tokens) * pricing.completion_usd_per_token


def _guard_hard_stop(reason: str) -> None:
    raise RuntimeError(reason)


def _enforce_budgets_before_call(
    *,
    guards: HardGuards,
    budget: BudgetState,
    planned_prompt_chars: int,
    planned_max_completion_tokens: int,
    pricing: Pricing | None,
) -> None:
    if guards.max_runtime_minutes > 0 and budget.elapsed_minutes() >= float(guards.max_runtime_minutes):
        _guard_hard_stop(f"max-runtime-minutes exceeded: {budget.elapsed_minutes():.2f} >= {guards.max_runtime_minutes}")

    # Be conservative: a call may require a repair call too.
    if int(guards.max_requests_total) > 0:
        remaining = int(guards.max_requests_total) - int(budget.requests_made)
        if remaining < 2:
            _guard_hard_stop(f"max-requests-total exceeded/near-exhausted: remaining={remaining} (need >=2 for safe call+repair)")

    if int(guards.max_input_chars) > 0 and int(planned_prompt_chars) > int(guards.max_input_chars):
        _guard_hard_stop(f"max-input-chars exceeded: {planned_prompt_chars} > {guards.max_input_chars}")

    if float(guards.max_cost_usd) > 0 and guards.stop_on_budget_exceeded:
        if pricing is None:
            _guard_hard_stop("max-cost-usd is set but pricing is unavailable (cannot enforce budget safely)")
        est_prompt_tokens = _approx_tokens_from_chars(int(planned_prompt_chars))
        est_cost_upper = (
            float(est_prompt_tokens) * pricing.prompt_usd_per_token
            + float(max(0, int(planned_max_completion_tokens))) * pricing.completion_usd_per_token
        )
        if float(budget.cost_usd) + float(est_cost_upper) > float(guards.max_cost_usd):
            _guard_hard_stop(
                f"max-cost-usd would be exceeded (upper bound): {budget.cost_usd:.6f} + {est_cost_upper:.6f} > {guards.max_cost_usd:.6f}"
            )


def _cache_dir(outputs_root: Path) -> Path:
    return outputs_root / "cache"


def _cache_key_path(
    *,
    outputs_root: Path,
    task: str,
    model_id: str,
    category_id: int,
    item_id: str,
    prompt_version: str,
    input_hash: str,
) -> Path:
    model_dir = _sanitize_model_dir(model_id)
    # Windows-friendly filename sanitizer (avoid ':' and other invalid characters).
    safe_item = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(item_id or "item"))
    safe_item = safe_item.strip("._-") or "item"
    if len(safe_item) > 80:
        safe_item = f"{safe_item[:40]}_{_sha256_text(safe_item)[:16]}"
    return (
        _cache_dir(outputs_root)
        / str(task)
        / model_dir
        / str(category_id)
        / str(safe_item)
        / str(prompt_version)
        / f"{input_hash}.json"
    )


def _load_cached_json(path: Path) -> Any | None:
    try:
        if not path.exists():
            return None
        return _read_json(path)
    except Exception:
        return None


def _save_cached_json(path: Path, payload: Any) -> None:
    _write_json(path, payload)


def _fetch_openrouter_pricing(provider: OpenRouterProvider) -> dict[str, Pricing]:
    """
    Fetch pricing for models from OpenRouter /models endpoint.
    This is NOT an LLM generation call, but it is a network call.
    """
    url = f"{str(provider.base_url).rstrip('/')}/models"
    with httpx.Client(timeout=float(getattr(provider, "timeout_seconds", 30.0))) as client:
        response = client.get(url, headers=provider._build_headers())  # noqa: SLF001 (spike script)
        response.raise_for_status()
        raw = response.json()
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list):
        raise ValueError("OpenRouter /models returned unexpected payload")
    out: dict[str, Pricing] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        # OpenRouter returns numbers-as-strings; keep robust.
        prompt = float(pricing.get("prompt") or 0.0)
        completion = float(pricing.get("completion") or 0.0)
        if model_id:
            out[model_id] = Pricing(prompt_usd_per_token=prompt, completion_usd_per_token=completion)
    return out


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


def _try_extract_json_object(content: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return _extract_json_object(content), None
    except Exception as exc:  # noqa: BLE001 (spike script)
        return None, str(exc)


def _normalize_for_evidence(value: str) -> str:
    text_value = str(value or "").lower().replace("ё", "е")
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value


def _evidence_found(*, evidence: str, haystack: str) -> bool:
    if not str(evidence or "").strip():
        return False
    return _normalize_for_evidence(evidence) in _normalize_for_evidence(haystack)


@dataclass(frozen=True)
class Vibe:
    label: str
    label_raw: str
    confidence: float
    evidence_spans: list[str]
    notes: str

    @classmethod
    def from_obj(cls, obj: Any) -> "Vibe":
        data = obj if isinstance(obj, dict) else {}
        confidence = float(data.get("confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        spans_raw = data.get("evidence_spans") or []
        spans: list[str] = []
        if isinstance(spans_raw, list):
            for item in spans_raw[:5]:
                value = str(item or "").strip()
                if value:
                    spans.append(value)
        return cls(
            label=str(data.get("label") or "other").strip() or "other",
            label_raw=str(data.get("label_raw") or "").strip(),
            confidence=round(confidence, 4),
            evidence_spans=spans,
            notes=str(data.get("notes") or "").strip(),
        )


def _validate_vibes(*, vibes: list[Vibe], evidence_text: str) -> dict[str, Any]:
    hallucinated = 0
    missing_evidence = 0
    validated: list[dict[str, Any]] = []
    for vibe in vibes:
        if not vibe.evidence_spans:
            missing_evidence += 1
            validated.append({**vibe.__dict__, "hallucinated": True, "evidence_valid": False})
            continue
        ok = all(_evidence_found(evidence=span, haystack=evidence_text) for span in vibe.evidence_spans)
        if not ok:
            hallucinated += 1
        validated.append({**vibe.__dict__, "hallucinated": (not ok), "evidence_valid": ok})
    return {
        "vibes": validated,
        "metrics": {
            "vibes_total": len(vibes),
            "vibes_with_missing_evidence": missing_evidence,
            "vibes_hallucinated": hallucinated,
            "evidence_valid_rate": round(
                (len(vibes) - hallucinated - missing_evidence) / max(1, len(vibes)),
                4,
            ),
        },
    }


def _flatten_jsonish(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped[:1] in {"[", "{"}:
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return _flatten_jsonish(decoded)
        return [stripped]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        if "value" in value and len(value) <= 3:
            return _flatten_jsonish(value.get("value"))
        parts: list[str] = []
        for item in value.values():
            parts.extend(_flatten_jsonish(item))
        return parts
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_flatten_jsonish(item))
        return parts
    return [str(value)]


def _truncate(text_value: str, limit: int) -> str:
    value = str(text_value or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, int(limit))].rstrip() + "…"


def _sanitize_llm_text(value: str) -> str:
    """Minimize JSON-breaking characters in prompts/evidence.

    We intentionally replace double quotes to reduce invalid JSON responses
    when models copy evidence spans verbatim.
    """

    text_value = str(value or "")
    text_value = text_value.replace("\r", " ")
    text_value = text_value.replace('"', "'")
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value

def _fetch_latest_product_rows(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_ids: list[int],
) -> dict[int, dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                updated_at,
                nm_id,
                title,
                description,
                characteristics,
                sizes,
                colors,
                dimensions
            FROM products
            WHERE project_id = :project_id
              AND subject_id = :category_id
              AND nm_id = ANY(:nm_ids)
            ORDER BY nm_id ASC, updated_at DESC NULLS LAST, id DESC
            """
        ),
        {"project_id": project_id, "category_id": category_id, "nm_ids": list(nm_ids)},
    ).mappings().all()

    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        nm_id = int(row.get("nm_id") or 0)
        if nm_id <= 0 or nm_id in latest:
            continue
        latest[nm_id] = dict(row)
    return latest


def _sku_evidence_text(row: dict[str, Any]) -> dict[str, str]:
    title = str(row.get("title") or "")
    description = str(row.get("description") or "")
    parts: list[str] = []
    for field in ("characteristics", "sizes", "colors", "dimensions"):
        parts.extend(_flatten_jsonish(row.get(field)))
    attributes_text = " ".join(part.strip() for part in parts if str(part or "").strip())
    return {
        "title": _sanitize_llm_text(_truncate(title, 220)),
        "description": _sanitize_llm_text(_truncate(description, 600)),
        "attributes_text": _sanitize_llm_text(_truncate(attributes_text, 600)),
    }


def _category_input_text(
    *,
    subject_name: str,
    sku_titles: list[str],
    query_examples: list[str],
    limits: PromptLimits,
) -> str:
    lines: list[str] = []
    lines.append(f"subject_name: {_sanitize_llm_text(subject_name)}")
    lines.append("")
    lines.append("sku_title_examples:")
    for title in sku_titles[: max(0, int(limits.category_max_sku_titles))]:
        lines.append(f"- {_sanitize_llm_text(_truncate(title, int(limits.category_max_title_chars)))}")
    lines.append("")
    lines.append("query_examples:")
    for item in query_examples[: max(0, int(limits.category_max_query_examples))]:
        lines.append(f"- {_sanitize_llm_text(_truncate(item, int(limits.category_max_query_chars)))}")
    return "\n".join(lines).strip()


def _sku_batch_input_text(items: list[dict[str, Any]]) -> str:
    lines = []
    lines.append("INPUT ITEMS:")
    for item in items:
        lines.append(f"- nm_id={item['nm_id']}")
        lines.append(f"  title={item['title']}")
        lines.append(f"  description={item['description']}")
        lines.append(f"  attributes_text={item['attributes_text']}")
    return "\n".join(lines).strip()


def _query_batch_input_text(items: list[dict[str, Any]]) -> str:
    lines = []
    lines.append("INPUT CLUSTERS:")
    for item in items:
        lines.append(f"- cluster_key={item['cluster_key']}")
        lines.append(f"  label={item['label']}")
        lines.append("  queries=[" + ", ".join(json.dumps(q, ensure_ascii=False) for q in item["queries"]) + "]")
    return "\n".join(lines).strip()


_SYSTEM_PROMPT = (
    "Ты извлекаешь expressive meaning (вайбы/эстетика/эмоциональное позиционирование) из предоставленного текста.\n"
    "Правила:\n"
    "- Не выдумывай. Если сигналов нет — верни пустой список vibes.\n"
    "- Каждый vibe обязан иметь evidence_spans (точные подстроки из input).\n"
    "- Evidence spans: без переводов строк, без двойных кавычек (\") и длиной <= 80 символов.\n"
    "- Верни только JSON, без Markdown.\n"
)


def _call_llm_json(
    *,
    provider: OpenRouterProvider,
    repair_provider: OpenRouterProvider | None = None,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    def _do_call(sys_text: str, user_text: str, *, max_tokens_value: int) -> dict[str, Any]:
        t0 = _now_ms()
        response = provider.generate_chat(
            [
                ChatMessage(role="system", content=sys_text),
                ChatMessage(role="user", content=user_text),
            ],
            temperature=temperature,
            max_tokens=max(16, int(max_tokens_value)),
        )
        latency_ms = _now_ms() - t0
        raw = dict(response.raw_response or {})
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        return {
            "model": str(response.model),
            "latency_ms": int(latency_ms),
            "usage": usage,
            "content": str(response.content or ""),
            "raw_response": raw,
        }

    primary = _do_call(system_prompt, user_prompt, max_tokens_value=max_tokens)
    parsed, error = _try_extract_json_object(primary["content"])
    if parsed is not None:
        return {**primary, "parsed": parsed, "parse_error": None, "repaired": False}

    # Repair path: ask the same model to output valid JSON only.
    repair_client = repair_provider or provider
    repair_system = (
        "You are a JSON repair assistant.\n"
        "Take the provided text and output a single VALID JSON object.\n"
        "Return JSON only (no markdown, no comments, no trailing text)."
    )
    repair_user = (
        f"Parse error: {error}\n"
        "Fix to valid JSON object:\n"
        "-----\n"
        f"{primary['content']}\n"
        "-----\n"
        "Return only the JSON object."
    )
    # Use repair_client (default cheap model) to avoid repeated expensive retries.
    t0 = _now_ms()
    repair_resp = repair_client.generate_chat(
        [ChatMessage(role="system", content=repair_system), ChatMessage(role="user", content=repair_user)],
        temperature=0.0,
        max_tokens=max(256, int(max_tokens)),
    )
    repaired = {
        "model": str(repair_resp.model),
        "latency_ms": int(_now_ms() - t0),
        "usage": (
            dict(repair_resp.raw_response.get("usage") or {})
            if isinstance(repair_resp.raw_response, dict) and isinstance(repair_resp.raw_response.get("usage"), dict)
            else {}
        ),
        "content": str(repair_resp.content or ""),
        "raw_response": dict(repair_resp.raw_response or {}),
    }
    parsed2, error2 = _try_extract_json_object(repaired["content"])
    if parsed2 is None:
        return {
            **primary,
            "parsed": None,
            "parse_error": str(error or ""),
            "repaired": True,
            "repair_latency_ms": int(repaired["latency_ms"]),
            "repair_usage": repaired.get("usage") or {},
            "repair_content": repaired["content"],
            "repair_raw_response": repaired.get("raw_response") or {},
            "repair_parse_error": str(error2 or ""),
        }
    return {
        **primary,
        "parsed": parsed2,
        "parse_error": str(error or ""),
        "repaired": True,
        "repair_latency_ms": int(repaired["latency_ms"]),
        "repair_usage": repaired.get("usage") or {},
        "repair_content": repaired["content"],
        "repair_raw_response": repaired.get("raw_response") or {},
        "repair_parse_error": None,
    }


def _chunked(values: list[Any], *, chunk_size: int) -> Iterable[list[Any]]:
    size = max(1, int(chunk_size))
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _baseline_query_vibes(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> dict[str, list[str]]:
    # IMPORTANT: keep refresh_hybrid=False to avoid writes during evaluation spike.
    result = run_query_profile_extraction(
        session,
        project_id=project_id,
        category_id=category_id,
        top_limit=50,
        samples_limit=50,
        refresh_hybrid=False,
        persist=False,
    )
    by_key: dict[str, list[str]] = {}
    for profile in result.profiles:
        meaning, _flags = formalize_query_meaning(profile, project_id=project_id, category_id=category_id)
        by_key[str(profile.cluster_key)] = list(meaning.expressive.vibes or [])
    return by_key


def cmd_ping(args: argparse.Namespace) -> int:
    model_id = str(args.model)
    provider = OpenRouterProvider(chat_model=model_id, timeout_seconds=float(args.timeout_seconds))
    payload = _call_llm_json(
        provider=provider,
        system_prompt="You are a ping responder. Return JSON only: {\"ok\": true}.",
        user_prompt="Return JSON: {\"ok\": true}",
        temperature=0.0,
        max_tokens=max(16, int(args.max_tokens)),
    )
    print(json.dumps({"status": "ok", "model": payload["model"], "latency_ms": payload["latency_ms"]}, ensure_ascii=False))
    return 0


def _cmd_run_unsafe_legacy(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    dataset = _read_json(dataset_path)
    project_id = int(dataset.get("project_id") or args.project_id)
    models = [item.strip() for item in str(args.models).split(",") if item.strip()]
    outputs_root = Path(args.outputs_root)
    _ensure_dir(outputs_root)
    repair_provider = OpenRouterProvider(chat_model=str(args.repair_model), timeout_seconds=float(args.timeout_seconds))

    with SessionLocal() as session:
        for cat in dataset.get("categories") or []:
            category_id = int(cat["category_id"])
            subject_name = str(cat.get("subject_name") or category_id)
            nm_ids = [int(x) for x in (cat.get("sku_nm_ids") or [])]
            cluster_keys = [str(x) for x in (cat.get("cluster_keys") or [])]

            # Load product evidence
            latest_rows = _fetch_latest_product_rows(
                session,
                project_id=project_id,
                category_id=category_id,
                nm_ids=nm_ids,
            )
            sku_evidence_items = []
            for nm_id in nm_ids:
                row = latest_rows.get(int(nm_id))
                if not row:
                    continue
                ev = _sku_evidence_text(row)
                sku_evidence_items.append({"nm_id": int(nm_id), **ev})

            # Load query clusters (persisted) and pick requested ones
            cluster_views = get_query_clusters(session, project_id=project_id, category_id=category_id)
            cluster_by_key = {str(view.cluster_key): view for view in cluster_views}
            query_items = []
            query_examples_for_category = []
            for key in cluster_keys:
                view = cluster_by_key.get(str(key))
                if not view:
                    continue
                member_queries = [
                    _sanitize_llm_text(str(m.display_query or m.normalized_query_text))
                    for m in view.members[:8]
                ]
                label = _sanitize_llm_text(str(view.cluster_label_candidate))
                query_items.append(
                    {
                        "cluster_key": str(view.cluster_key),
                        "label": label,
                        "queries": member_queries,
                        "query_count": int(view.query_count or 0),
                    }
                )
                if label:
                    query_examples_for_category.append(label)
                query_examples_for_category.extend(member_queries[:3])

            # Baseline snapshots (deterministic/proxy) for report comparison
            category_meaning = build_category_meaning(session, project_id=project_id, category_id=category_id)
            baseline_sku = {}
            for nm_id in nm_ids:
                try:
                    proj, _flags = build_product_projection(
                        session,
                        project_id=project_id,
                        category_id=category_id,
                        nm_id=int(nm_id),
                        category_meaning=category_meaning,
                    )
                    baseline_sku[str(nm_id)] = list(proj.expressive.vibes or [])
                except Exception:
                    baseline_sku[str(nm_id)] = []
            baseline_query = _baseline_query_vibes(session, project_id=project_id, category_id=category_id)

            baseline_dir = outputs_root / str(category_id) / "baseline"
            baseline_path = baseline_dir / "baseline.json"
            if not (bool(getattr(args, "resume", False)) and baseline_path.exists()):
                _write_json(
                    baseline_path,
                    {
                        "project_id": project_id,
                        "category_id": category_id,
                        "subject_name": subject_name,
                        "category_vibes": list(category_meaning.expressive.vibes or []),
                        "sku_vibes": baseline_sku,
                        "query_vibes": {k: baseline_query.get(k, []) for k in cluster_keys},
                        "notes": {
                            "query_baseline_refresh_hybrid": False,
                            "query_baseline_persist": False,
                        },
                    },
                )

            sku_titles = [str(item["title"]) for item in sku_evidence_items]
            category_input = _category_input_text(
                subject_name=subject_name,
                sku_titles=sku_titles,
                query_examples=query_examples_for_category,
            )

            for model_id in models:
                model_dir = outputs_root / str(category_id) / _sanitize_model_dir(model_id)
                _ensure_dir(model_dir)
                provider = OpenRouterProvider(chat_model=model_id, timeout_seconds=float(args.timeout_seconds))

                # --- Category ---
                category_out = model_dir / "category.json"
                category_raw_out = model_dir / "category.raw.json"
                skip_category = bool(getattr(args, "resume", False)) and category_out.exists() and category_raw_out.exists()
                if not skip_category:
                    cat_user_prompt = (
                        "TASK=category_expressive\n"
                        "Return JSON:\n"
                        "{\n"
                        '  "version": "v1",\n'
                        '  "task": "category",\n'
                        '  "vibes": [\n'
                        "    {\n"
                        '      "label": "other",\n'
                        '      "label_raw": "",\n'
                        '      "confidence": 0.0,\n'
                        '      "evidence_spans": ["..."],\n'
                        '      "notes": ""\n'
                        "    }\n"
                        "  ],\n"
                        '  "summary": "",\n'
                        '  "warnings": []\n'
                        "}\n\n"
                        "INPUT:\n"
                        f"{category_input}\n"
                    )
                    cat_raw = _call_llm_json(
                        provider=provider,
                        repair_provider=repair_provider,
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=cat_user_prompt,
                        temperature=float(args.temperature),
                        max_tokens=max(16, int(args.max_tokens_category)),
                    )
                    _write_json(category_raw_out, cat_raw)
                    cat_parsed = cat_raw.get("parsed")
                    if not isinstance(cat_parsed, dict):
                        _write_json(
                            category_out,
                            {
                                "project_id": project_id,
                                "category_id": category_id,
                                "subject_name": subject_name,
                                "model_id": model_id,
                                "error": "category_json_parse_failed",
                                "parse_error": cat_raw.get("parse_error") or "",
                                "repair_parse_error": cat_raw.get("repair_parse_error") or "",
                            },
                        )
                        continue

                    cat_vibes = [Vibe.from_obj(obj) for obj in (cat_parsed.get("vibes") or [])]
                    cat_valid = _validate_vibes(vibes=cat_vibes, evidence_text=category_input)
                    _write_json(
                        category_out,
                        {
                            "project_id": project_id,
                            "category_id": category_id,
                            "subject_name": subject_name,
                            "model_id": model_id,
                            "latency_ms": cat_raw["latency_ms"],
                            "usage": cat_raw.get("usage") or {},
                            "result": {
                                "version": cat_parsed.get("version", "v1"),
                                "task": "category",
                                "vibes": cat_valid["vibes"],
                                "summary": str(cat_parsed.get("summary") or "").strip(),
                                "warnings": cat_parsed.get("warnings") or [],
                            },
                            "validation_metrics": cat_valid["metrics"],
                        },
                    )

                # --- SKU batch (chunked) ---
                sku_out = model_dir / "sku.json"
                sku_raw_out = model_dir / "sku.raw.json"
                skip_sku = bool(getattr(args, "resume", False)) and sku_out.exists() and sku_raw_out.exists()
                if not skip_sku:
                    sku_outputs = []
                    sku_validation = []
                    sku_raw_chunks = []
                    for chunk in _chunked(sku_evidence_items, chunk_size=int(args.sku_chunk_size)):
                        user_prompt = (
                            "TASK=sku_expressive_batch\n"
                            "Return JSON:\n"
                            "{\n"
                            '  "version": "v1",\n'
                            '  "task": "sku_batch",\n'
                            '  "items": [\n'
                            "    {\n"
                            '      "nm_id": 0,\n'
                            '      "vibes": [\n'
                            "        {\n"
                            '          "label": "other",\n'
                            '          "label_raw": "",\n'
                            '          "confidence": 0.0,\n'
                            '          "evidence_spans": ["..."],\n'
                            '          "notes": ""\n'
                            "        }\n"
                            "      ],\n"
                            '      "summary": "",\n'
                            '      "warnings": []\n'
                            "    }\n"
                            "  ]\n"
                            "}\n\n"
                            + _sku_batch_input_text(chunk)
                        )
                        raw = _call_llm_json(
                            provider=provider,
                            repair_provider=repair_provider,
                            system_prompt=_SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                            temperature=float(args.temperature),
                            max_tokens=max(16, int(args.max_tokens_sku)),
                        )
                        sku_raw_chunks.append(raw)
                        parsed = raw["parsed"] if isinstance(raw.get("parsed"), dict) else {}
                        items = parsed.get("items") or []
                        if not isinstance(items, list):
                            items = []
                        by_nm = {int(it["nm_id"]): it for it in chunk}
                        for obj in items:
                            if not isinstance(obj, dict):
                                continue
                            nm_id = int(obj.get("nm_id") or 0)
                            ev = by_nm.get(nm_id)
                            if not ev:
                                continue
                            evidence_text = "\n".join([ev["title"], ev["description"], ev["attributes_text"]]).strip()
                            vibes = [Vibe.from_obj(v) for v in (obj.get("vibes") or [])]
                            valid = _validate_vibes(vibes=vibes, evidence_text=evidence_text)
                            sku_outputs.append(
                                {
                                    "nm_id": nm_id,
                                    "vibes": valid["vibes"],
                                    "summary": str(obj.get("summary") or "").strip(),
                                    "warnings": obj.get("warnings") or [],
                                }
                            )
                            sku_validation.append({**valid["metrics"], "nm_id": nm_id})

                    _write_json(sku_raw_out, {"chunks": sku_raw_chunks})
                    _write_json(
                        sku_out,
                        {
                            "project_id": project_id,
                            "category_id": category_id,
                            "subject_name": subject_name,
                            "model_id": model_id,
                            "result": {
                                "version": "v1",
                                "task": "sku_batch",
                                "items": sorted(sku_outputs, key=lambda it: int(it["nm_id"])),
                            },
                            "validation_metrics": {
                                "items_total": len(sku_outputs),
                                "avg_evidence_valid_rate": round(
                                    sum(float(m.get("evidence_valid_rate") or 0.0) for m in sku_validation)
                                    / max(1, len(sku_validation)),
                                    4,
                                ),
                            },
                        },
                    )

                # --- Query batch (chunked) ---
                query_out = model_dir / "query.json"
                query_raw_out = model_dir / "query.raw.json"
                if bool(getattr(args, "resume", False)) and query_out.exists() and query_raw_out.exists():
                    continue
                query_outputs: list[dict[str, Any]] = []
                query_validation = []
                query_raw_chunks: list[dict[str, Any]] = []
                for chunk in _chunked(query_items, chunk_size=int(args.query_chunk_size)):
                    user_prompt = (
                        "TASK=query_expressive_batch\n"
                        "Return JSON:\n"
                        "{\n"
                        '  "version": "v1",\n'
                        '  "task": "query_batch",\n'
                        '  "items": [\n'
                        "    {\n"
                        '      "cluster_key": "",\n'
                        '      "expressive_intent": true,\n'
                        '      "vibes": [\n'
                        "        {\n"
                        '          "label": "other",\n'
                        '          "label_raw": "",\n'
                        '          "confidence": 0.0,\n'
                        '          "evidence_spans": ["..."],\n'
                        '          "notes": ""\n'
                        "        }\n"
                        "      ],\n"
                        '      "summary": "",\n'
                        '      "warnings": []\n'
                        "    }\n"
                        "  ]\n"
                        "}\n\n"
                        + _query_batch_input_text(chunk)
                    )
                    raw = _call_llm_json(
                        provider=provider,
                        repair_provider=repair_provider,
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        temperature=float(args.temperature),
                        max_tokens=max(16, int(args.max_tokens_query)),
                    )
                    query_raw_chunks.append(raw)
                    parsed = raw["parsed"] if isinstance(raw.get("parsed"), dict) else {}
                    items = parsed.get("items") or []
                    if not isinstance(items, list):
                        items = []
                    by_key = {str(it["cluster_key"]): it for it in chunk}
                    for obj in items:
                        if not isinstance(obj, dict):
                            continue
                        cluster_key = str(obj.get("cluster_key") or "").strip()
                        ev = by_key.get(cluster_key)
                        if not ev:
                            continue
                        evidence_text = "\n".join([ev["label"], *list(ev["queries"])]).strip()
                        vibes = [Vibe.from_obj(v) for v in (obj.get("vibes") or [])]
                        valid = _validate_vibes(vibes=vibes, evidence_text=evidence_text)
                        query_outputs.append(
                            {
                                "cluster_key": cluster_key,
                                "expressive_intent": bool(obj.get("expressive_intent")),
                                "vibes": valid["vibes"],
                                "summary": str(obj.get("summary") or "").strip(),
                                "warnings": obj.get("warnings") or [],
                                "query_count": int(ev.get("query_count") or 0),
                                "label": str(ev.get("label") or ""),
                            }
                        )
                        query_validation.append({**valid["metrics"], "cluster_key": cluster_key})

                _write_json(query_raw_out, {"chunks": query_raw_chunks})
                _write_json(
                    query_out,
                    {
                        "project_id": project_id,
                        "category_id": category_id,
                        "subject_name": subject_name,
                        "model_id": model_id,
                        "result": {
                            "version": "v1",
                            "task": "query_batch",
                            "items": sorted(query_outputs, key=lambda it: str(it["cluster_key"])),
                        },
                        "validation_metrics": {
                            "items_total": len(query_outputs),
                            "avg_evidence_valid_rate": round(
                                sum(float(m.get("evidence_valid_rate") or 0.0) for m in query_validation)
                                / max(1, len(query_validation)),
                                4,
                            ),
                        },
                    },
                )

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """
    Safe staged runner:
    - dry-run: no LLM calls
    - micro-run: minimal sanity with strict guards
    - controlled-batch: bounded run with strict guards
    - full-eval: explicit opt-in + explicit budgets required
    """
    dataset_path = Path(args.dataset)
    dataset = _read_json(dataset_path)
    project_id = int(dataset.get("project_id") or args.project_id)

    # --- Mode selection (safe default: dry-run) ---
    mode_dry = bool(getattr(args, "dry_run", False))
    mode_micro = bool(getattr(args, "micro_run", False))
    mode_batch = bool(getattr(args, "controlled_batch", False))
    mode_full = bool(getattr(args, "full_eval", False))
    if sum(1 for v in (mode_dry, mode_micro, mode_batch, mode_full) if v) == 0:
        mode_dry = True
    if sum(1 for v in (mode_dry, mode_micro, mode_batch, mode_full) if v) != 1:
        _guard_hard_stop("Exactly one mode flag must be set: --dry-run | --micro-run | --controlled-batch | --full-eval")

    mode_name = "dry-run" if mode_dry else "micro-run" if mode_micro else "controlled-batch" if mode_batch else "full-eval"

    outputs_root = Path(str(getattr(args, "outputs_root", "") or str(DEFAULT_OUTPUTS_ROOT)))
    _ensure_dir(outputs_root)

    # Requested models
    requested_models = [m.strip() for m in str(args.models or "").split(",") if m.strip()]
    if not requested_models:
        requested_models = ["openai/gpt-4o-mini"]

    # micro-run and controlled-batch override model list to safe defaults (unless user explicitly runs full-eval).
    if mode_micro:
        requested_models = ["openai/gpt-4o-mini"]
    if mode_batch:
        requested_models = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini"]

    # --- Mode defaults (safe staged execution) ---
    # NOTE: args values may be None; treat None as "not specified".
    if mode_micro:
        if getattr(args, "max_categories", None) is None:
            args.max_categories = 1
        if getattr(args, "max_models", None) is None:
            args.max_models = 1
        if getattr(args, "max_skus_per_category", None) is None:
            args.max_skus_per_category = 3
        if getattr(args, "max_clusters_per_category", None) is None:
            args.max_clusters_per_category = 5
        if getattr(args, "max_requests_total", None) is None:
            args.max_requests_total = 12
        if getattr(args, "max_runtime_minutes", None) is None:
            args.max_runtime_minutes = 10.0
        if getattr(args, "max_cost_usd", None) is None:
            args.max_cost_usd = 0.25
        # keep prompts smaller in micro-run
        args.max_tokens_category = min(int(args.max_tokens_category), 300)
        args.max_tokens_sku = min(int(args.max_tokens_sku), 500)
        args.max_tokens_query = min(int(args.max_tokens_query), 500)

        args.category_max_sku_titles = min(int(args.category_max_sku_titles), 10)
        args.category_max_query_examples = min(int(args.category_max_query_examples), 15)
        args.query_max_member_queries = min(int(args.query_max_member_queries), 5)

    if mode_batch:
        if getattr(args, "max_categories", None) is None:
            args.max_categories = 1
        if getattr(args, "max_models", None) is None:
            args.max_models = 2
        if getattr(args, "max_skus_per_category", None) is None:
            args.max_skus_per_category = 10
        if getattr(args, "max_clusters_per_category", None) is None:
            args.max_clusters_per_category = 15
        if getattr(args, "max_requests_total", None) is None:
            args.max_requests_total = 50
        if getattr(args, "max_runtime_minutes", None) is None:
            args.max_runtime_minutes = 30.0
        if getattr(args, "max_cost_usd", None) is None:
            args.max_cost_usd = 1.0

    if mode_full:
        # full eval requires explicit opt-in and explicit budgets (no unbounded spending).
        if not bool(getattr(args, "full_eval", False)):
            _guard_hard_stop("full-eval requires explicit --full-eval flag")
        for required in ("max_requests_total", "max_runtime_minutes", "max_cost_usd"):
            if getattr(args, required, None) is None:
                _guard_hard_stop(f"--full-eval requires explicit --{required.replace('_','-')}")

    guards = HardGuards(
        max_categories=int(getattr(args, "max_categories", 0) or 0),
        max_models=int(getattr(args, "max_models", 0) or 0),
        max_skus_per_category=int(getattr(args, "max_skus_per_category", 0) or 0),
        max_clusters_per_category=int(getattr(args, "max_clusters_per_category", 0) or 0),
        max_requests_total=int(getattr(args, "max_requests_total", 0) or 0),
        max_input_chars=int(getattr(args, "max_input_chars", 0) or 0),
        max_runtime_minutes=float(getattr(args, "max_runtime_minutes", 0.0) or 0.0),
        max_cost_usd=float(getattr(args, "max_cost_usd", 0.0) or 0.0),
        stop_on_budget_exceeded=bool(getattr(args, "stop_on_budget_exceeded", True)),
    )

    limits = PromptLimits(
        category_max_sku_titles=int(getattr(args, "category_max_sku_titles", 15) or 15),
        category_max_query_examples=int(getattr(args, "category_max_query_examples", 50) or 50),
        category_max_title_chars=int(getattr(args, "category_max_title_chars", 120) or 120),
        category_max_query_chars=int(getattr(args, "category_max_query_chars", 80) or 80),
        sku_max_title_chars=int(getattr(args, "sku_max_title_chars", 220) or 220),
        sku_max_description_chars=int(getattr(args, "sku_max_description_chars", 600) or 600),
        sku_max_attributes_chars=int(getattr(args, "sku_max_attributes_chars", 600) or 600),
        query_max_member_queries=int(getattr(args, "query_max_member_queries", 8) or 8),
        query_max_query_chars=int(getattr(args, "query_max_query_chars", 80) or 80),
        query_max_label_chars=int(getattr(args, "query_max_label_chars", 120) or 120),
    )

    models = list(requested_models)
    if int(guards.max_models) > 0:
        models = models[: int(guards.max_models)]

    # Providers for OpenRouter (LLM calls are only after run_plan.json is persisted).
    repair_provider = OpenRouterProvider(chat_model=str(args.repair_model), timeout_seconds=float(args.timeout_seconds))

    # Categories selection (cap)
    cats = list(dataset.get("categories") or [])
    if int(guards.max_categories) > 0:
        cats = cats[: int(guards.max_categories)]

    # --- Pre-run plan (no LLM calls) ---
    planned_calls_by_task = {"category": 0, "sku": 0, "query": 0}
    planned_calls_total = 0
    planned_calls_total_worst_with_repair = 0
    prompt_chars_samples: dict[str, list[int]] = {"category": [], "sku": [], "query": []}
    selected: list[dict[str, Any]] = []

    with SessionLocal() as session:
        for cat in cats:
            category_id = int(cat["category_id"])
            subject_name = str(cat.get("subject_name") or category_id)
            nm_ids = [int(x) for x in (cat.get("sku_nm_ids") or [])]
            cluster_keys = [str(x) for x in (cat.get("cluster_keys") or [])]
            if int(guards.max_skus_per_category) > 0:
                nm_ids = nm_ids[: int(guards.max_skus_per_category)]
            if int(guards.max_clusters_per_category) > 0:
                cluster_keys = cluster_keys[: int(guards.max_clusters_per_category)]

            latest_rows = _fetch_latest_product_rows(session, project_id=project_id, category_id=category_id, nm_ids=nm_ids)
            sku_evidence_items: list[dict[str, Any]] = []
            for nm_id in nm_ids:
                row = latest_rows.get(int(nm_id))
                if not row:
                    continue
                ev = _sku_evidence_text(row)
                sku_evidence_items.append(
                    {
                        "nm_id": int(nm_id),
                        "title": _sanitize_llm_text(_truncate(ev["title"], int(limits.sku_max_title_chars))),
                        "description": _sanitize_llm_text(_truncate(ev["description"], int(limits.sku_max_description_chars))),
                        "attributes_text": _sanitize_llm_text(_truncate(ev["attributes_text"], int(limits.sku_max_attributes_chars))),
                    }
                )

            cluster_views = get_query_clusters(session, project_id=project_id, category_id=category_id)
            cluster_by_key = {str(view.cluster_key): view for view in cluster_views}
            query_items: list[dict[str, Any]] = []
            query_examples_for_category: list[str] = []
            for key in cluster_keys:
                view = cluster_by_key.get(str(key))
                if not view:
                    continue
                member_queries = [
                    _sanitize_llm_text(_truncate(str(m.display_query or m.normalized_query_text), int(limits.query_max_query_chars)))
                    for m in view.members[: max(0, int(limits.query_max_member_queries))]
                ]
                label = _sanitize_llm_text(_truncate(str(view.cluster_label_candidate), int(limits.query_max_label_chars)))
                query_items.append({"cluster_key": str(view.cluster_key), "label": label, "queries": member_queries, "query_count": int(view.query_count or 0)})
                if label:
                    query_examples_for_category.append(label)
                query_examples_for_category.extend(member_queries[:3])

            category_input = _category_input_text(
                subject_name=subject_name,
                sku_titles=[str(i["title"]) for i in sku_evidence_items],
                query_examples=query_examples_for_category,
                limits=limits,
            )

            # Build representative prompts to estimate sizes.
            category_user_prompt = "INPUT:\n" + category_input + "\n"
            sku_chunks = list(_chunked(sku_evidence_items, chunk_size=int(args.sku_chunk_size)))
            query_chunks = list(_chunked(query_items, chunk_size=int(args.query_chunk_size)))

            per_model_calls = 1 + len(sku_chunks) + len(query_chunks)
            planned_calls_by_task["category"] += len(models)
            planned_calls_by_task["sku"] += len(models) * len(sku_chunks)
            planned_calls_by_task["query"] += len(models) * len(query_chunks)
            planned_calls_total += len(models) * per_model_calls
            planned_calls_total_worst_with_repair += 2 * len(models) * per_model_calls

            prompt_chars_samples["category"].append(len(_SYSTEM_PROMPT) + len(category_user_prompt))
            for ch in sku_chunks:
                prompt_chars_samples["sku"].append(len(_SYSTEM_PROMPT) + len(_sku_batch_input_text(ch)))
            for ch in query_chunks:
                prompt_chars_samples["query"].append(len(_SYSTEM_PROMPT) + len(_query_batch_input_text(ch)))

            selected.append(
                {
                    "category_id": category_id,
                    "subject_name": subject_name,
                    "sku_nm_ids": [int(x["nm_id"]) for x in sku_evidence_items],
                    "cluster_keys": [str(x["cluster_key"]) for x in query_items],
                }
            )

        run_plan = {
            "version": "v1",
            "prompt_version": PROMPT_VERSION,
            "mode": mode_name,
            "project_id": project_id,
            "dataset_path": str(dataset_path),
            "outputs_root": str(outputs_root),
            "selected": {"categories": selected, "models": models},
            "guards": {
                "max_categories": guards.max_categories,
                "max_models": guards.max_models,
                "max_skus_per_category": guards.max_skus_per_category,
                "max_clusters_per_category": guards.max_clusters_per_category,
                "max_requests_total": guards.max_requests_total,
                "max_input_chars": guards.max_input_chars,
                "max_runtime_minutes": guards.max_runtime_minutes,
                "max_cost_usd": guards.max_cost_usd,
                "stop_on_budget_exceeded": guards.stop_on_budget_exceeded,
            },
            "planned_calls": {
                "total": planned_calls_total,
                "total_worst_with_repair": planned_calls_total_worst_with_repair,
                "by_task": planned_calls_by_task,
                "note": "planned calls are computed before cache hits; 'worst_with_repair' assumes 1 repair call per request",
            },
            "prompt_size_chars": {
                key: {
                    "samples": len(values),
                    "max": max(values or [0]),
                    "avg": round(sum(values or [0]) / max(1, len(values)), 2),
                }
                for key, values in prompt_chars_samples.items()
            },
            "limits": limits.__dict__,
            "cache": {
                "enabled": True,
                "dir": str(_cache_dir(outputs_root)),
                "category_key": "(category_id, model, prompt_version, input_hash)",
                "sku_key": "(task=sku_item, category_id, nm_id, model, prompt_version, input_hash)",
                "query_key": "(task=query_item, category_id, cluster_key, model, prompt_version, input_hash)",
            },
        }

        run_plan_path = outputs_root / "run_plan.json"
        _write_json(run_plan_path, run_plan)
        print(
            json.dumps(
                {
                    "mode": mode_name,
                    "selected_categories": [c["category_id"] for c in selected],
                    "selected_models": models,
                    "planned_calls_total": planned_calls_total,
                    "planned_calls_total_worst_with_repair": planned_calls_total_worst_with_repair,
                    "planned_calls_by_task": planned_calls_by_task,
                    "outputs_root": str(outputs_root),
                    "run_plan_path": str(run_plan_path),
                },
                ensure_ascii=False,
            )
        )

        if mode_dry:
            return 0

        # Preflight hard stops before any LLM call.
        if int(guards.max_requests_total) > 0 and int(planned_calls_total_worst_with_repair) > int(guards.max_requests_total):
            _guard_hard_stop(
                f"planned calls (worst with repair) exceed max-requests-total: {planned_calls_total_worst_with_repair} > {guards.max_requests_total}"
            )

        pricing_table: dict[str, Pricing] | None = None
        if float(guards.max_cost_usd) > 0:
            pricing_table = _fetch_openrouter_pricing(repair_provider)

        budget = BudgetState(started_ms=_now_ms())

        # --- Execution ---
        for cat in selected:
            category_id = int(cat["category_id"])
            subject_name = str(cat["subject_name"])
            nm_ids = [int(x) for x in (cat.get("sku_nm_ids") or [])]
            cluster_keys = [str(x) for x in (cat.get("cluster_keys") or [])]

            # Baseline is intentionally skipped in micro-run (faster, no report logic).
            if not mode_micro:
                category_meaning = build_category_meaning(session, project_id=project_id, category_id=category_id)
                baseline_sku = {}
                for nm_id in nm_ids:
                    try:
                        proj, _flags = build_product_projection(
                            session,
                            project_id=project_id,
                            category_id=category_id,
                            nm_id=int(nm_id),
                            category_meaning=category_meaning,
                        )
                        baseline_sku[str(nm_id)] = list(proj.expressive.vibes or [])
                    except Exception:
                        baseline_sku[str(nm_id)] = []
                baseline_query = _baseline_query_vibes(session, project_id=project_id, category_id=category_id)
                baseline_dir = outputs_root / str(category_id) / "baseline"
                baseline_path = baseline_dir / "baseline.json"
                if not (bool(getattr(args, "resume", False)) and baseline_path.exists()):
                    _write_json(
                        baseline_path,
                        {
                            "project_id": project_id,
                            "category_id": category_id,
                            "subject_name": subject_name,
                            "category_vibes": list(category_meaning.expressive.vibes or []),
                            "sku_vibes": baseline_sku,
                            "query_vibes": {k: baseline_query.get(k, []) for k in cluster_keys},
                            "notes": {"query_baseline_refresh_hybrid": False, "query_baseline_persist": False},
                        },
                    )

            latest_rows = _fetch_latest_product_rows(session, project_id=project_id, category_id=category_id, nm_ids=nm_ids)
            sku_evidence_items: list[dict[str, Any]] = []
            for nm_id in nm_ids:
                row = latest_rows.get(int(nm_id))
                if not row:
                    continue
                ev = _sku_evidence_text(row)
                sku_evidence_items.append(
                    {
                        "nm_id": int(nm_id),
                        "title": _sanitize_llm_text(_truncate(ev["title"], int(limits.sku_max_title_chars))),
                        "description": _sanitize_llm_text(_truncate(ev["description"], int(limits.sku_max_description_chars))),
                        "attributes_text": _sanitize_llm_text(_truncate(ev["attributes_text"], int(limits.sku_max_attributes_chars))),
                    }
                )

            cluster_views = get_query_clusters(session, project_id=project_id, category_id=category_id)
            cluster_by_key = {str(view.cluster_key): view for view in cluster_views}
            query_items: list[dict[str, Any]] = []
            query_examples_for_category: list[str] = []
            for key in cluster_keys:
                view = cluster_by_key.get(str(key))
                if not view:
                    continue
                member_queries = [
                    _sanitize_llm_text(_truncate(str(m.display_query or m.normalized_query_text), int(limits.query_max_query_chars)))
                    for m in view.members[: max(0, int(limits.query_max_member_queries))]
                ]
                label = _sanitize_llm_text(_truncate(str(view.cluster_label_candidate), int(limits.query_max_label_chars)))
                query_items.append({"cluster_key": str(view.cluster_key), "label": label, "queries": member_queries, "query_count": int(view.query_count or 0)})
                if label:
                    query_examples_for_category.append(label)
                query_examples_for_category.extend(member_queries[:3])

            category_input = _category_input_text(
                subject_name=subject_name,
                sku_titles=[str(i["title"]) for i in sku_evidence_items],
                query_examples=query_examples_for_category,
                limits=limits,
            )

            for model_id in models:
                model_dir = outputs_root / str(category_id) / _sanitize_model_dir(model_id)
                _ensure_dir(model_dir)
                provider = OpenRouterProvider(chat_model=model_id, timeout_seconds=float(args.timeout_seconds))

                print(
                    json.dumps(
                        {
                            "stage": "start_model",
                            "category_id": category_id,
                            "model_id": model_id,
                            "requests_made": budget.requests_made,
                            "cache_hits": budget.cache_hits,
                            "cost_usd": round(budget.cost_usd, 6),
                            "elapsed_min": round(budget.elapsed_minutes(), 2),
                        },
                        ensure_ascii=False,
                    )
                )

                # ---- Category call (dedup/cached) ----
                category_user_prompt = (
                    "TASK=category_expressive\n"
                    "Return JSON:\n"
                    "{\n"
                    '  "version": "v1",\n'
                    '  "task": "category",\n'
                    '  "vibes": [{"label":"other","label_raw":"","confidence":0.0,"evidence_spans":["..."],"notes":""}],\n'
                    '  "summary": "",\n'
                    '  "warnings": []\n'
                    "}\n\n"
                    "INPUT:\n"
                    f"{category_input}\n"
                )
                category_input_hash = _sha256_text(
                    json.dumps(
                        {
                            "task": "category",
                            "prompt_version": PROMPT_VERSION,
                            "model": model_id,
                            "system": _SYSTEM_PROMPT,
                            "user": category_user_prompt,
                            "temperature": float(args.temperature),
                            "max_tokens": int(args.max_tokens_category),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                category_cache_path = _cache_key_path(
                    outputs_root=outputs_root,
                    task="category",
                    model_id=model_id,
                    category_id=category_id,
                    item_id="category",
                    prompt_version=PROMPT_VERSION,
                    input_hash=category_input_hash,
                )
                category_out = model_dir / "category.json"
                category_raw_out = model_dir / "category.raw.json"
                cached_category = _load_cached_json(category_cache_path)
                if cached_category is not None:
                    budget.cache_hits += 1
                    parsed_payload = cached_category.get("parsed_result") if isinstance(cached_category, dict) else cached_category
                    if parsed_payload is not None:
                        _write_json(category_out, parsed_payload)
                    _write_json(category_raw_out, {"cached": True, "cache_path": str(category_cache_path)})
                else:
                    planned_chars = len(_SYSTEM_PROMPT) + len(category_user_prompt)
                    _enforce_budgets_before_call(
                        guards=guards,
                        budget=budget,
                        planned_prompt_chars=planned_chars,
                        planned_max_completion_tokens=int(args.max_tokens_category),
                        pricing=(pricing_table or {}).get(model_id) if pricing_table else None,
                    )
                    cat_raw = _call_llm_json(
                        provider=provider,
                        repair_provider=repair_provider,
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=category_user_prompt,
                        temperature=float(args.temperature),
                        max_tokens=max(16, int(args.max_tokens_category)),
                    )
                    budget.requests_made += 1
                    primary_cost = _compute_cost_usd(
                        pricing=(pricing_table or {}).get(cat_raw["model"]) if pricing_table else None, usage=cat_raw.get("usage") or {}
                    )
                    if primary_cost is not None:
                        budget.cost_usd += float(primary_cost)
                    if bool(cat_raw.get("repaired")):
                        budget.requests_made += 1
                        repair_usage = cat_raw.get("repair_usage") or {}
                        repair_model = str(cat_raw.get("repair_raw_response", {}).get("model") or args.repair_model)
                        repair_cost = _compute_cost_usd(pricing=(pricing_table or {}).get(repair_model) if pricing_table else None, usage=repair_usage)
                        if repair_cost is not None:
                            budget.cost_usd += float(repair_cost)
                    _write_json(category_raw_out, cat_raw)
                    cat_parsed = cat_raw.get("parsed")
                    if not isinstance(cat_parsed, dict):
                        _write_json(
                            category_out,
                            {
                                "project_id": project_id,
                                "category_id": category_id,
                                "subject_name": subject_name,
                                "model_id": model_id,
                                "error": "category_json_parse_failed",
                                "parse_error": cat_raw.get("parse_error") or "",
                                "repair_parse_error": cat_raw.get("repair_parse_error") or "",
                            },
                        )
                        continue
                    cat_vibes = [Vibe.from_obj(obj) for obj in (cat_parsed.get("vibes") or [])]
                    cat_valid = _validate_vibes(vibes=cat_vibes, evidence_text=category_input)
                    parsed_payload = {
                        "project_id": project_id,
                        "category_id": category_id,
                        "subject_name": subject_name,
                        "model_id": model_id,
                        "result": {
                            "version": "v1",
                            "task": "category",
                            "vibes": cat_valid["vibes"],
                            "summary": str(cat_parsed.get("summary") or "").strip(),
                            "warnings": cat_parsed.get("warnings") or [],
                        },
                        "validation_metrics": cat_valid["metrics"],
                    }
                    _write_json(category_out, parsed_payload)
                    _save_cached_json(category_cache_path, {"parsed_result": parsed_payload, "cached_at_ms": _now_ms()})

                # ---- SKU batch (cache per SKU item) ----
                sku_out = model_dir / "sku.json"
                sku_raw_out = model_dir / "sku.raw.json"
                sku_outputs: list[dict[str, Any]] = []
                sku_validation: list[dict[str, Any]] = []
                sku_raw_chunks: list[dict[str, Any]] = []
                uncached_sku_items: list[dict[str, Any]] = []
                sku_item_hashes: dict[int, str] = {}
                for item in sku_evidence_items:
                    nm_id = int(item["nm_id"])
                    item_hash = _sha256_text(
                        json.dumps(
                            {
                                "task": "sku_item",
                                "prompt_version": PROMPT_VERSION,
                                "schema_id": "sku_batch_schema_v1_multiline",
                                "model": model_id,
                                "system": _SYSTEM_PROMPT,
                                "temperature": float(args.temperature),
                                "max_tokens": int(args.max_tokens_sku),
                                "nm_id": nm_id,
                                "title": item["title"],
                                "description": item["description"],
                                "attributes_text": item["attributes_text"],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    sku_item_hashes[nm_id] = item_hash
                    cache_path = _cache_key_path(
                        outputs_root=outputs_root,
                        task="sku_item",
                        model_id=model_id,
                        category_id=category_id,
                        item_id=str(nm_id),
                        prompt_version=PROMPT_VERSION,
                        input_hash=item_hash,
                    )
                    cached = _load_cached_json(cache_path)
                    if cached is not None:
                        budget.cache_hits += 1
                        obj = cached.get("item") if isinstance(cached, dict) else cached
                        if isinstance(obj, dict):
                            sku_outputs.append(obj)
                        continue
                    uncached_sku_items.append(item)

                for chunk in _chunked(uncached_sku_items, chunk_size=int(args.sku_chunk_size)):
                    if not chunk:
                        continue
                    user_prompt = (
                        "TASK=sku_expressive_batch\n"
                        "Return JSON:\n"
                        "{\n"
                        '  "version": "v1",\n'
                        '  "task": "sku_batch",\n'
                        '  "items": [\n'
                        "    {\n"
                        '      "nm_id": 0,\n'
                        '      "vibes": [\n'
                        "        {\n"
                        '          "label": "other",\n'
                        '          "label_raw": "",\n'
                        '          "confidence": 0.0,\n'
                        '          "evidence_spans": ["..."],\n'
                        '          "notes": ""\n'
                        "        }\n"
                        "      ],\n"
                        '      "summary": "",\n'
                        '      "warnings": []\n'
                        "    }\n"
                        "  ]\n"
                        "}\n\n"
                        f"{_sku_batch_input_text(chunk)}\n"
                    )
                    planned_chars = len(_SYSTEM_PROMPT) + len(user_prompt)
                    _enforce_budgets_before_call(
                        guards=guards,
                        budget=budget,
                        planned_prompt_chars=planned_chars,
                        planned_max_completion_tokens=int(args.max_tokens_sku),
                        pricing=(pricing_table or {}).get(model_id) if pricing_table else None,
                    )
                    raw = _call_llm_json(
                        provider=provider,
                        repair_provider=repair_provider,
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        temperature=float(args.temperature),
                        max_tokens=max(16, int(args.max_tokens_sku)),
                    )
                    budget.requests_made += 1
                    primary_cost = _compute_cost_usd(
                        pricing=(pricing_table or {}).get(raw["model"]) if pricing_table else None, usage=raw.get("usage") or {}
                    )
                    if primary_cost is not None:
                        budget.cost_usd += float(primary_cost)
                    if bool(raw.get("repaired")):
                        budget.requests_made += 1
                        repair_usage = raw.get("repair_usage") or {}
                        repair_model = str(raw.get("repair_raw_response", {}).get("model") or args.repair_model)
                        repair_cost = _compute_cost_usd(pricing=(pricing_table or {}).get(repair_model) if pricing_table else None, usage=repair_usage)
                        if repair_cost is not None:
                            budget.cost_usd += float(repair_cost)

                    sku_raw_chunks.append(raw)
                    parsed = raw["parsed"] if isinstance(raw.get("parsed"), dict) else {}
                    items = parsed.get("items") or []
                    if not isinstance(items, list):
                        items = []
                    by_id = {int(it["nm_id"]): it for it in chunk}
                    for obj in items:
                        if not isinstance(obj, dict):
                            continue
                        nm_id = int(obj.get("nm_id") or 0)
                        ev = by_id.get(nm_id)
                        if not ev:
                            continue
                        evidence_text = "\n".join([ev["title"], ev["description"], ev["attributes_text"]]).strip()
                        vibes = [Vibe.from_obj(v) for v in (obj.get("vibes") or [])]
                        valid = _validate_vibes(vibes=vibes, evidence_text=evidence_text)
                        item_out = {
                            "nm_id": int(nm_id),
                            "vibes": valid["vibes"],
                            "summary": str(obj.get("summary") or "").strip(),
                            "warnings": obj.get("warnings") or [],
                            "expressive_hit_proxy": bool(EXPRESSIVE_RE.search(evidence_text)),
                        }
                        sku_outputs.append(item_out)
                        sku_validation.append({**valid["metrics"], "nm_id": int(nm_id)})
                        item_hash = sku_item_hashes.get(int(nm_id)) or _sha256_text(evidence_text)
                        cache_path = _cache_key_path(
                            outputs_root=outputs_root,
                            task="sku_item",
                            model_id=model_id,
                            category_id=category_id,
                            item_id=str(nm_id),
                            prompt_version=PROMPT_VERSION,
                            input_hash=item_hash,
                        )
                        _save_cached_json(cache_path, {"item": item_out, "cached_at_ms": _now_ms()})

                _write_json(sku_raw_out, {"chunks": sku_raw_chunks, "cache_hits": budget.cache_hits})
                _write_json(
                    sku_out,
                    {
                        "project_id": project_id,
                        "category_id": category_id,
                        "subject_name": subject_name,
                        "model_id": model_id,
                        "result": {"version": "v1", "task": "sku_batch", "items": sorted(sku_outputs, key=lambda it: int(it["nm_id"]))},
                        "validation_metrics": {
                            "items_total": len(sku_outputs),
                            "avg_evidence_valid_rate": round(
                                sum(float(m.get("evidence_valid_rate") or 0.0) for m in sku_validation) / max(1, len(sku_validation)),
                                4,
                            ),
                        },
                    },
                )

                # ---- Query batch (cache per cluster) ----
                query_out = model_dir / "query.json"
                query_raw_out = model_dir / "query.raw.json"
                query_outputs: list[dict[str, Any]] = []
                query_validation: list[dict[str, Any]] = []
                query_raw_chunks: list[dict[str, Any]] = []
                uncached_query_items: list[dict[str, Any]] = []
                query_item_hashes: dict[str, str] = {}
                for item in query_items:
                    cluster_key = str(item["cluster_key"])
                    item_hash = _sha256_text(
                        json.dumps(
                            {
                                "task": "query_item",
                                "prompt_version": PROMPT_VERSION,
                                "schema_id": "query_batch_schema_v1_minimal",
                                "model": model_id,
                                "system": _SYSTEM_PROMPT,
                                "temperature": float(args.temperature),
                                "max_tokens": int(args.max_tokens_query),
                                "cluster_key": cluster_key,
                                "label": item["label"],
                                "queries": item["queries"],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    query_item_hashes[cluster_key] = item_hash
                    cache_path = _cache_key_path(
                        outputs_root=outputs_root,
                        task="query_item",
                        model_id=model_id,
                        category_id=category_id,
                        item_id=cluster_key,
                        prompt_version=PROMPT_VERSION,
                        input_hash=item_hash,
                    )
                    cached = _load_cached_json(cache_path)
                    if cached is not None:
                        budget.cache_hits += 1
                        obj = cached.get("item") if isinstance(cached, dict) else cached
                        if isinstance(obj, dict):
                            query_outputs.append(obj)
                        continue
                    uncached_query_items.append(item)

                for chunk in _chunked(uncached_query_items, chunk_size=int(args.query_chunk_size)):
                    if not chunk:
                        continue
                    user_prompt = (
                        "TASK=query_expressive_batch\n"
                        "Return JSON:\n"
                        "{\n"
                        '  "version": "v1",\n'
                        '  "task": "query_batch",\n'
                        '  "items": [{"cluster_key":"","expressive_intent":false,"vibes":[{"label":"other","label_raw":"","confidence":0.0,"evidence_spans":["..."],"notes":""}],"summary":"","warnings":[]}]\n'
                        "}\n\n"
                        f"{_query_batch_input_text(chunk)}\n"
                    )
                    planned_chars = len(_SYSTEM_PROMPT) + len(user_prompt)
                    _enforce_budgets_before_call(
                        guards=guards,
                        budget=budget,
                        planned_prompt_chars=planned_chars,
                        planned_max_completion_tokens=int(args.max_tokens_query),
                        pricing=(pricing_table or {}).get(model_id) if pricing_table else None,
                    )
                    raw = _call_llm_json(
                        provider=provider,
                        repair_provider=repair_provider,
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        temperature=float(args.temperature),
                        max_tokens=max(16, int(args.max_tokens_query)),
                    )
                    budget.requests_made += 1
                    primary_cost = _compute_cost_usd(
                        pricing=(pricing_table or {}).get(raw["model"]) if pricing_table else None, usage=raw.get("usage") or {}
                    )
                    if primary_cost is not None:
                        budget.cost_usd += float(primary_cost)
                    if bool(raw.get("repaired")):
                        budget.requests_made += 1
                        repair_usage = raw.get("repair_usage") or {}
                        repair_model = str(raw.get("repair_raw_response", {}).get("model") or args.repair_model)
                        repair_cost = _compute_cost_usd(pricing=(pricing_table or {}).get(repair_model) if pricing_table else None, usage=repair_usage)
                        if repair_cost is not None:
                            budget.cost_usd += float(repair_cost)

                    query_raw_chunks.append(raw)
                    parsed = raw["parsed"] if isinstance(raw.get("parsed"), dict) else {}
                    items = parsed.get("items") or []
                    if not isinstance(items, list):
                        items = []
                    by_key = {str(it["cluster_key"]): it for it in chunk}
                    for obj in items:
                        if not isinstance(obj, dict):
                            continue
                        cluster_key = str(obj.get("cluster_key") or "").strip()
                        ev = by_key.get(cluster_key)
                        if not ev:
                            continue
                        evidence_text = "\n".join([ev["label"], *list(ev["queries"])]).strip()
                        vibes = [Vibe.from_obj(v) for v in (obj.get("vibes") or [])]
                        valid = _validate_vibes(vibes=vibes, evidence_text=evidence_text)
                        item_out = {
                            "cluster_key": cluster_key,
                            "expressive_intent": bool(obj.get("expressive_intent")),
                            "vibes": valid["vibes"],
                            "summary": str(obj.get("summary") or "").strip(),
                            "warnings": obj.get("warnings") or [],
                            "query_count": int(ev.get("query_count") or 0),
                            "label": str(ev.get("label") or ""),
                        }
                        query_outputs.append(item_out)
                        query_validation.append({**valid["metrics"], "cluster_key": cluster_key})
                        item_hash = query_item_hashes.get(str(cluster_key)) or _sha256_text(evidence_text)
                        cache_path = _cache_key_path(
                            outputs_root=outputs_root,
                            task="query_item",
                            model_id=model_id,
                            category_id=category_id,
                            item_id=str(cluster_key),
                            prompt_version=PROMPT_VERSION,
                            input_hash=item_hash,
                        )
                        _save_cached_json(cache_path, {"item": item_out, "cached_at_ms": _now_ms()})

                _write_json(query_raw_out, {"chunks": query_raw_chunks, "cache_hits": budget.cache_hits})
                _write_json(
                    query_out,
                    {
                        "project_id": project_id,
                        "category_id": category_id,
                        "subject_name": subject_name,
                        "model_id": model_id,
                        "result": {"version": "v1", "task": "query_batch", "items": sorted(query_outputs, key=lambda it: str(it["cluster_key"]))},
                        "validation_metrics": {
                            "items_total": len(query_outputs),
                            "avg_evidence_valid_rate": round(
                                sum(float(m.get("evidence_valid_rate") or 0.0) for m in query_validation) / max(1, len(query_validation)),
                                4,
                            ),
                        },
                    },
                )

                # Post-call hard stop (actual budgets)
                if float(guards.max_cost_usd) > 0 and float(budget.cost_usd) > float(guards.max_cost_usd) and guards.stop_on_budget_exceeded:
                    _guard_hard_stop(f"max-cost-usd exceeded: {budget.cost_usd:.6f} > {guards.max_cost_usd:.6f}")
                if int(guards.max_requests_total) > 0 and int(budget.requests_made) > int(guards.max_requests_total):
                    _guard_hard_stop(f"max-requests-total exceeded: {budget.requests_made} > {guards.max_requests_total}")

        print(
            json.dumps(
                {
                    "status": "done",
                    "mode": mode_name,
                    "requests_made": budget.requests_made,
                    "cache_hits": budget.cache_hits,
                    "cost_usd": round(budget.cost_usd, 6),
                    "elapsed_min": round(budget.elapsed_minutes(), 2),
                    "outputs_root": str(outputs_root),
                },
                ensure_ascii=False,
            )
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expressive meaning LLM evaluation spike (offline).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ping = sub.add_parser("ping-openrouter", help="Minimal ping request to verify OpenRouter access.")
    ping.add_argument("--model", default="openai/gpt-4o-mini")
    ping.add_argument("--timeout-seconds", type=float, default=30.0)
    ping.add_argument("--max-tokens", type=int, default=16)
    ping.set_defaults(func=cmd_ping)

    run = sub.add_parser("run", help="Run evaluation for dataset + models and write outputs.")
    run.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    run.add_argument("--project-id", type=int, default=1)
    run.add_argument("--models", default=",".join(DEFAULT_MODELS))
    run.add_argument("--outputs-root", default=str(DEFAULT_OUTPUTS_ROOT))
    run.add_argument("--timeout-seconds", type=float, default=30.0)
    run.add_argument("--repair-model", default="openai/gpt-4o-mini")
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens-category", type=int, default=400)
    run.add_argument("--max-tokens-sku", type=int, default=900)
    run.add_argument("--max-tokens-query", type=int, default=900)
    run.add_argument("--sku-chunk-size", type=int, default=8)
    run.add_argument("--query-chunk-size", type=int, default=10)

    # Staged safe execution modes (safe default: dry-run if not specified)
    mode = run.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", help="Plan only: no LLM calls.")
    mode.add_argument("--micro-run", dest="micro_run", action="store_true", help="Safe minimal sanity run.")
    mode.add_argument(
        "--controlled-batch",
        dest="controlled_batch",
        action="store_true",
        help="Bounded batch run with strict guards.",
    )
    mode.add_argument("--full-eval", dest="full_eval", action="store_true", help="Allow full eval (explicit opt-in).")

    # Hard guards (hard stop, not warning)
    run.add_argument("--max-categories", type=int, default=None)
    run.add_argument("--max-models", type=int, default=None)
    run.add_argument("--max-skus-per-category", type=int, default=None)
    run.add_argument("--max-clusters-per-category", type=int, default=None)
    run.add_argument("--max-requests-total", type=int, default=None)
    run.add_argument("--max-input-chars", type=int, default=20000)
    run.add_argument("--max-runtime-minutes", type=float, default=None)
    run.add_argument("--max-cost-usd", type=float, default=None)
    run.add_argument("--stop-on-budget-exceeded", action="store_true", default=True)

    # Prompt size control (explicit limits; truncation happens before prompt build)
    run.add_argument("--category-max-sku-titles", dest="category_max_sku_titles", type=int, default=15)
    run.add_argument("--category-max-query-examples", dest="category_max_query_examples", type=int, default=50)
    run.add_argument("--category-max-title-chars", dest="category_max_title_chars", type=int, default=120)
    run.add_argument("--category-max-query-chars", dest="category_max_query_chars", type=int, default=80)
    run.add_argument("--sku-max-title-chars", dest="sku_max_title_chars", type=int, default=220)
    run.add_argument("--sku-max-description-chars", dest="sku_max_description_chars", type=int, default=600)
    run.add_argument("--sku-max-attributes-chars", dest="sku_max_attributes_chars", type=int, default=600)
    run.add_argument("--query-max-member-queries", dest="query_max_member_queries", type=int, default=8)
    run.add_argument("--query-max-query-chars", dest="query_max_query_chars", type=int, default=80)
    run.add_argument("--query-max-label-chars", dest="query_max_label_chars", type=int, default=120)

    run.add_argument(
        "--resume",
        action="store_true",
        help="Skip category/sku/query items when both parsed + raw outputs already exist.",
    )
    run.set_defaults(func=cmd_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
