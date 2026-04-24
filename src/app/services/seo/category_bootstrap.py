"""Category bootstrap pipeline for meaning-aware matcher readiness."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import settings
from app.db import SessionLocal
from app.models import (
    SeoCategoryBootstrapRun,
    SeoCategoryMatchingReadiness,
    SeoCategoryMeaningAxes,
    SeoMeaningEmbedding,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryMeaning,
)
from app.schemas.seo_category_bootstrap import (
    CATEGORY_MEANING_AXES_PROMPT_VERSION,
    CATEGORY_MEANING_AXES_SCHEMA_VERSION,
    CategoryBootstrapStatusResponse,
    CategoryMeaningAxesPayload,
)
from app.services.seo.expressive_llm.reviews_source import fetch_category_review_scope
from app.services.seo.meaning_extraction import build_category_meaning
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.meaning_atoms import build_query_atoms_for_category
from app.services.seo.meaning_atoms.storage import count_ready_query_atoms
from app.services.seo.query_meaning_matcher.canonical import stable_hash, unique_strings
from app.services.seo.query_meaning_matcher.embeddings import LocalPreviewEmbeddingProvider, ensure_meaning_embedding
from app.services.seo.query_meaning_matcher.library import build_query_meaning_library
from app.services.seo.query_pipeline import run_query_clustering, run_query_profile_extraction


class CategoryBootstrapError(Exception):
    """Raised when category bootstrap cannot complete."""


class CategoryBootstrapCancelled(Exception):
    """Raised internally when a bootstrap run was cancelled by corpus mutation."""


@dataclass(frozen=True)
class CategoryEvidencePack:
    project_id: int
    category_id: int
    evidence_hash: str
    payload: dict[str, Any]


_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ.]+", re.IGNORECASE)
_STOP_TOKENS = {
    "а",
    "без",
    "в",
    "во",
    "для",
    "до",
    "и",
    "или",
    "из",
    "к",
    "ко",
    "на",
    "не",
    "о",
    "об",
    "от",
    "по",
    "под",
    "при",
    "про",
    "с",
    "со",
    "у",
}
_AUDIENCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("женский", ("женск", "девуш", "девоч", "женщ")),
    ("мужской", ("мужск", "мальчик", "мужчин", "парн")),
    ("подросток", ("подрост",)),
    ("школьник", ("школ", "учеб")),
    ("мама", ("мам",)),
    ("папа", ("пап",)),
    ("подруга", ("подруг",)),
    ("любимая", ("любим",)),
)
_EXPRESSIVE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("милый", ("мил", "милаш", "няш")),
    ("красивый", ("красив",)),
    ("эстетичный", ("эстет", "пинтерест", "pinterest")),
    ("стильный", ("стильн",)),
    ("уютный", ("уют",)),
    ("деловой", ("делов", "офис")),
)
_ATTRIBUTE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("А4", ("а4", "a4")),
    ("15.6", ("15.6", "15", "ноутбук")),
    ("ортопедическая спинка", ("ортопед",)),
    ("вместительный", ("вместит", "объем", "обьем")),
    ("водостойкий", ("водостой", "влагозащит", "непромока")),
    ("легкий", ("легк",)),
    ("керамика", ("керами",)),
    ("стекло", ("стекл",)),
    ("фарфор", ("фарфор",)),
)
_CONSTRAINT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("thermal", ("термо",)),
    ("set", ("набор", "комплект")),
    ("beer_use_case", ("пивн", "пиво")),
    ("material:glass", ("стекл",)),
    ("material:ceramic", ("керами",)),
    ("material:porcelain", ("фарфор",)),
    ("laptop_size", ("15.6", "ноутбук")),
)
_OCCASION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("подарок", ("подар",)),
    ("день рождения", ("день рождения", "др")),
    ("новый год", ("новый год",)),
    ("школа", ("школ", "учеб")),
)


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _artifact_root() -> Path:
    override = os.getenv("SEO_CATEGORY_BOOTSTRAP_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(settings.INTERNAL_DATA_DIR) / "seo_category_bootstrap_cache"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_loads_maybe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped[:1] in {"[", "{"}:
            try:
                return json.loads(stripped)
            except Exception:
                return value
        return value
    return value


def _flatten_jsonish(value: Any) -> list[str]:
    resolved = _json_loads_maybe(value)
    if resolved is None:
        return []
    if isinstance(resolved, str):
        return [resolved]
    if isinstance(resolved, (int, float, bool)):
        return [str(resolved)]
    if isinstance(resolved, dict):
        parts: list[str] = []
        for item in resolved.values():
            parts.extend(_flatten_jsonish(item))
        return parts
    if isinstance(resolved, list):
        parts: list[str] = []
        for item in resolved:
            parts.extend(_flatten_jsonish(item))
        return parts
    return [str(resolved)]


def _tokens(text_value: Any) -> list[str]:
    text_value = str(text_value or "").lower().replace("ё", "е")
    return [token for token in _WORD_RE.findall(text_value) if token and token not in _STOP_TOKENS]


def _text_has_marker(text_value: str, marker: str) -> bool:
    normalized = str(text_value or "").lower().replace("ё", "е")
    return marker in normalized


def _append_rule_matches(target: list[str], text_value: str, rules: Iterable[tuple[str, tuple[str, ...]]]) -> None:
    for label, markers in rules:
        if any(_text_has_marker(text_value, marker) for marker in markers):
            target.append(label)


def _top_values(values: Iterable[str], *, limit: int = 40, min_count: int = 1) -> list[str]:
    counter = Counter(str(item).strip() for item in values if str(item or "").strip())
    items = [(count, value) for value, count in counter.items() if count >= min_count]
    items.sort(key=lambda item: (-item[0], item[1]))
    return [value for _count, value in items[:limit]]


def _canonical_axes_text(payload: CategoryMeaningAxesPayload) -> str:
    return "\n".join(
        [
            f"product_types: {', '.join(payload.product_type_axes)}",
            f"use_cases: {', '.join(payload.use_case_axes)}",
            f"audience: {', '.join(payload.audience_axes)}",
            f"attributes: {', '.join(payload.attribute_axes)}",
            f"expressive: {', '.join(payload.expressive_axes)}",
            f"occasion: {', '.join(payload.occasion_axes)}",
            f"constraints: {', '.join(payload.constraint_axes)}",
            f"negative_constraints: {', '.join(payload.negative_constraint_axes)}",
        ]
    )


def _fetch_product_evidence(session: Session, *, project_id: int, category_id: int, limit: int = 300) -> list[dict[str, Any]]:
    try:
        rows = session.execute(
            text(
                """
                SELECT
                    nm_id,
                    title,
                    brand,
                    subject_name,
                    description,
                    characteristics,
                    sizes,
                    colors,
                    dimensions
                FROM products
                WHERE project_id = :project_id
                  AND subject_id = :category_id
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT :limit
                """
            ),
            {"project_id": int(project_id), "category_id": int(category_id), "limit": int(limit)},
        ).mappings().all()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _fetch_query_cluster_evidence(session: Session, *, project_id: int, category_id: int, limit: int = 500) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(SeoQueryCluster)
        .where(SeoQueryCluster.project_id == int(project_id), SeoQueryCluster.category_id == int(category_id))
        .order_by(SeoQueryCluster.query_count.desc(), SeoQueryCluster.cluster_key.asc())
        .limit(int(limit))
    ).all()
    return [
        {
            "cluster_id": int(row.id),
            "cluster_key": str(row.cluster_key),
            "label": row.label,
            "top_query_text": row.top_query_text,
            "query_count": int(row.query_count or 0),
        }
        for row in rows
    ]


def _fetch_review_evidence(session: Session, *, project_id: int, category_id: int) -> dict[str, Any]:
    evidence: dict[str, Any] = {"positive": [], "negative": [], "warnings": []}
    try:
        positive = fetch_category_review_scope(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            min_rating=4,
            limit=700,
        )
        evidence["positive"] = [
            {"nm_id": item.nm_id, "rating": item.rating, "text": item.text[:500], "created_at": item.created_at.isoformat() if item.created_at else None}
            for item in positive.review_snippets[:150]
        ]
    except Exception as exc:
        evidence["warnings"].append(f"positive_reviews_unavailable:{type(exc).__name__}")

    try:
        rows = session.execute(
            text(
                """
                SELECT fs.nm_id, fs.product_valuation AS rating, fs.raw AS raw, fs.created_date AS created_date
                FROM wb_feedback_snapshots fs
                JOIN products p
                  ON p.project_id = fs.project_id
                 AND p.nm_id = fs.nm_id
                WHERE fs.project_id = :project_id
                  AND p.subject_id = :category_id
                  AND fs.product_valuation IS NOT NULL
                  AND fs.product_valuation <= 3
                ORDER BY fs.created_date DESC NULLS LAST, fs.id DESC
                LIMIT 150
                """
            ),
            {"project_id": int(project_id), "category_id": int(category_id)},
        ).mappings().all()
        for row in rows:
            raw = _json_loads_maybe(row.get("raw"))
            if not isinstance(raw, dict):
                continue
            parts = [str(raw.get(key) or "").strip() for key in ("text", "pros", "cons")]
            text_value = "\n".join(part for part in parts if part).strip()
            if text_value:
                evidence["negative"].append({"nm_id": int(row.get("nm_id") or 0), "rating": row.get("rating"), "text": text_value[:500]})
    except Exception as exc:
        evidence["warnings"].append(f"negative_reviews_unavailable:{type(exc).__name__}")
    return evidence


def build_category_evidence_pack(session: Session, *, project_id: int, category_id: int) -> CategoryEvidencePack:
    query_clusters = _fetch_query_cluster_evidence(session, project_id=project_id, category_id=category_id)
    products = _fetch_product_evidence(session, project_id=project_id, category_id=category_id)
    reviews = _fetch_review_evidence(session, project_id=project_id, category_id=category_id)
    try:
        category_meaning = build_category_meaning(session, project_id=int(project_id), category_id=int(category_id)).to_dict()
    except Exception as exc:
        category_meaning = {"error": f"{type(exc).__name__}: {exc}"}
    payload = {
        "schema_version": "category_evidence_pack_v0",
        "project_id": int(project_id),
        "category_id": int(category_id),
        "query_clusters": query_clusters,
        "products": products,
        "reviews": reviews,
        "category_meaning": category_meaning,
    }
    return CategoryEvidencePack(
        project_id=int(project_id),
        category_id=int(category_id),
        evidence_hash=stable_hash(payload),
        payload=payload,
    )


def _axes_from_evidence(evidence: CategoryEvidencePack) -> CategoryMeaningAxesPayload:
    payload = evidence.payload
    query_texts = " ".join(
        str(item.get("top_query_text") or item.get("label") or "")
        for item in payload.get("query_clusters", [])
        if isinstance(item, dict)
    )
    products = payload.get("products") if isinstance(payload.get("products"), list) else []
    product_texts = " ".join(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("description") or ""),
                " ".join(_flatten_jsonish(item.get("characteristics"))),
                " ".join(_flatten_jsonish(item.get("sizes"))),
                " ".join(_flatten_jsonish(item.get("colors"))),
                " ".join(_flatten_jsonish(item.get("dimensions"))),
            ]
        )
        for item in products
        if isinstance(item, dict)
    )
    reviews = payload.get("reviews") if isinstance(payload.get("reviews"), dict) else {}
    review_texts = " ".join(
        str(item.get("text") or "")
        for group in (reviews.get("positive") or [], reviews.get("negative") or [])
        for item in group
        if isinstance(item, dict)
    )
    all_text = " ".join([query_texts, product_texts, review_texts]).lower().replace("ё", "е")

    category_meaning = payload.get("category_meaning") if isinstance(payload.get("category_meaning"), dict) else {}
    functional = category_meaning.get("functional") if isinstance(category_meaning.get("functional"), dict) else {}
    expressive = category_meaning.get("expressive") if isinstance(category_meaning.get("expressive"), dict) else {}

    product_types: list[str] = []
    product_types.extend(str(item) for item in functional.get("product_types", []) or [])
    for cluster in payload.get("query_clusters", []) or []:
        if not isinstance(cluster, dict):
            continue
        cluster_tokens = _tokens(cluster.get("top_query_text") or cluster.get("label"))
        if cluster_tokens:
            product_types.append(cluster_tokens[0])
    title_tokens: list[str] = []
    for product in products[:100]:
        if isinstance(product, dict):
            title_tokens.extend(_tokens(product.get("title")))
    product_types.extend(token for token in title_tokens if len(token) >= 4 and not token[0].isdigit())

    use_cases: list[str] = []
    use_cases.extend(str(item) for item in functional.get("use_cases", []) or [])
    for marker in ("школ", "учеб", "ноутбук", "путешеств", "поезд", "прогул", "спорт", "трениров", "фитнес", "город"):
        if marker in all_text:
            label = {
                "школ": "школа",
                "учеб": "учеба",
                "ноутбук": "ноутбук",
                "путешеств": "путешествия",
                "поезд": "поездка",
                "прогул": "прогулка",
                "спорт": "спорт",
                "трениров": "тренировка",
                "фитнес": "фитнес",
                "город": "город",
            }[marker]
            use_cases.append(label)

    audience: list[str] = []
    expressive_axes: list[str] = []
    attributes: list[str] = []
    constraints: list[str] = []
    occasions: list[str] = []
    _append_rule_matches(audience, all_text, _AUDIENCE_RULES)
    _append_rule_matches(expressive_axes, all_text, _EXPRESSIVE_RULES)
    _append_rule_matches(attributes, all_text, _ATTRIBUTE_RULES)
    _append_rule_matches(constraints, all_text, _CONSTRAINT_RULES)
    _append_rule_matches(occasions, all_text, _OCCASION_RULES)
    expressive_axes.extend(str(item) for item in expressive.get("vibes", []) or [])
    attributes.extend(str(item) for item in functional.get("attributes", []) or [])

    negative_text = " ".join(
        str(item.get("text") or "")
        for item in (reviews.get("negative") or [])
        if isinstance(item, dict)
    ).lower().replace("ё", "е")
    negative_constraints: list[str] = []
    if negative_text:
        _append_rule_matches(negative_constraints, negative_text, _ATTRIBUTE_RULES)
        if "маленьк" in negative_text or "мало места" in negative_text:
            negative_constraints.append("маленький размер")
        if "не помещ" in negative_text or "не влез" in negative_text:
            negative_constraints.append("не помещается")

    conflict_rules: list[dict[str, Any]] = []
    if "женский" in audience and "мужской" in audience:
        conflict_rules.extend(
            [
                {"if_query_has": "мужской", "conflicts_with_sku_negative": "не мужской"},
                {"if_query_has": "женский", "conflicts_with_sku_negative": "не женский"},
            ]
        )
    if "thermal" in constraints:
        conflict_rules.append({"if_query_has": "thermal", "requires_sku_constraint": "thermal"})
    if "set" in constraints:
        conflict_rules.append({"if_query_has": "set", "requires_sku_constraint": "set"})

    product_type_axes = _top_values(product_types, limit=30, min_count=1)
    if product_type_axes:
        generic_patterns = product_type_axes[:8]
    else:
        generic_patterns = []
    synonym_groups = [
        {"label": axis, "variants": [axis]}
        for axis in unique_strings([*product_type_axes, *use_cases, *audience, *attributes, *expressive_axes])[:80]
    ]
    return CategoryMeaningAxesPayload(
        product_type_axes=product_type_axes,
        use_case_axes=unique_strings(use_cases)[:40],
        audience_axes=unique_strings(audience)[:40],
        attribute_axes=unique_strings(attributes)[:60],
        expressive_axes=unique_strings(expressive_axes)[:40],
        occasion_axes=unique_strings(occasions)[:30],
        constraint_axes=unique_strings(constraints)[:40],
        negative_constraint_axes=unique_strings(negative_constraints)[:40],
        conflict_rules=conflict_rules,
        synonym_groups=synonym_groups,
        generic_query_patterns=generic_patterns,
        evidence_refs=["query_clusters", "products", "reviews", "category_meaning"],
        confidence={"deterministic": 0.65, "reviews": 0.45 if review_texts else 0.0},
    )


def _parse_llm_json(text_value: str) -> dict[str, Any]:
    stripped = str(text_value or "").strip()
    if not stripped:
        raise CategoryBootstrapError("LLM returned empty category axes response")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first >= 0 and last > first:
            candidate = candidate[first : last + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise CategoryBootstrapError("LLM category axes response must be a JSON object")
    return parsed


def _parse_or_repair_llm_json(
    *,
    content: str,
    provider: ChatProvider,
    original_prompt: str,
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    try:
        return _parse_llm_json(content), None
    except Exception as first_exc:
        repair_prompt = (
            "Repair the model output below into one valid compact JSON object for schema "
            "category_meaning_axes_v0. Return only JSON, no markdown, no comments. "
            "Keep only these top-level keys: product_type_axes, use_case_axes, audience_axes, "
            "attribute_axes, expressive_axes, occasion_axes, constraint_axes, "
            "negative_constraint_axes, conflict_rules, synonym_groups, "
            "generic_query_patterns, evidence_refs, confidence. "
            "All *_axes, generic_query_patterns, evidence_refs must be arrays of strings. "
            "conflict_rules and synonym_groups must be arrays. confidence must be an object "
            "with numeric values.\n\n"
            "ORIGINAL_TASK:\n"
            f"{original_prompt[:6000]}\n\n"
            "BROKEN_OUTPUT:\n"
            f"{str(content or '')[:12000]}\n\n"
            f"PARSE_ERROR: {type(first_exc).__name__}: {first_exc}"
        )
        response = provider.generate_chat(
            [ChatMessage(role="user", content=repair_prompt)],
            temperature=0.0,
            max_tokens=4096,
        )
        repaired = _parse_llm_json(response.content)
        return repaired, dict(response.raw_response or {}) or {"model": response.model, "content": response.content}


def _prompt_for_axes(evidence: CategoryEvidencePack, deterministic: CategoryMeaningAxesPayload) -> str:
    compact = {
        "schema_version": CATEGORY_MEANING_AXES_SCHEMA_VERSION,
        "category_id": evidence.category_id,
        "query_clusters": evidence.payload.get("query_clusters", [])[:120],
        "products": [
            {
                "title": item.get("title"),
                "description": str(item.get("description") or "")[:400],
                "characteristics": _flatten_jsonish(item.get("characteristics"))[:20],
            }
            for item in (evidence.payload.get("products") or [])[:60]
            if isinstance(item, dict)
        ],
        "positive_reviews": (evidence.payload.get("reviews") or {}).get("positive", [])[:60],
        "negative_reviews": (evidence.payload.get("reviews") or {}).get("negative", [])[:40],
        "deterministic_axes": deterministic.model_dump(mode="json"),
    }
    return (
        "Ты строишь смысловые оси категории маркетплейса для SEO matcher.\n"
        "Верни только валидный компактный JSON без markdown и комментариев. Не оценивай конкретный SKU.\n"
        "Сохрани deterministic axes, добавь buyer language из отзывов, hard constraints и conflict rules.\n"
        "Разрешенные top-level keys: product_type_axes, use_case_axes, audience_axes, attribute_axes, "
        "expressive_axes, occasion_axes, constraint_axes, negative_constraint_axes, conflict_rules, "
        "synonym_groups, generic_query_patterns, evidence_refs, confidence. "
        "Не добавляй вложенные объяснения и длинные тексты; максимум 80 элементов на список.\n\n"
        f"{json.dumps(compact, ensure_ascii=False, sort_keys=True)}"
    )


def _merge_axes(base: CategoryMeaningAxesPayload, parsed: Mapping[str, Any]) -> CategoryMeaningAxesPayload:
    raw = parsed if isinstance(parsed, dict) else {}

    def merged_list(key: str) -> list[str]:
        return unique_strings([*getattr(base, key), *(raw.get(key) or [])])[:80]

    return CategoryMeaningAxesPayload(
        product_type_axes=merged_list("product_type_axes"),
        use_case_axes=merged_list("use_case_axes"),
        audience_axes=merged_list("audience_axes"),
        attribute_axes=merged_list("attribute_axes"),
        expressive_axes=merged_list("expressive_axes"),
        occasion_axes=merged_list("occasion_axes"),
        constraint_axes=merged_list("constraint_axes"),
        negative_constraint_axes=merged_list("negative_constraint_axes"),
        conflict_rules=[*base.conflict_rules, *(raw.get("conflict_rules") or [])][:80],
        synonym_groups=[*base.synonym_groups, *(raw.get("synonym_groups") or [])][:120],
        generic_query_patterns=unique_strings([*base.generic_query_patterns, *(raw.get("generic_query_patterns") or [])])[:80],
        evidence_refs=unique_strings([*base.evidence_refs, *(raw.get("evidence_refs") or [])]),
        confidence={**base.confidence, **(raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {})},
    )


def _store_axes_artifact(
    *,
    project_id: int,
    category_id: int,
    source: str,
    input_hash: str,
    prompt: str,
    raw_response: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> None:
    root = _artifact_root() / "category_axes" / f"p{int(project_id)}" / f"c{int(category_id)}" / source / f"h_{input_hash[:32]}"
    _write_json(root / "meta.json", {"created_at": _utc_now_iso(), "input_hash": input_hash, "source": source})
    _write_json(root / "prompt.json", {"messages": [{"role": "user", "content": prompt}]})
    _write_json(root / "raw_response.json", dict(raw_response))
    _write_json(root / "parsed.json", dict(parsed))


def _upsert_axes(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    source: str,
    evidence_hash: str,
    axes: CategoryMeaningAxesPayload,
    input_hash: str,
    status: str = "ready",
    llm_model: str | None = None,
) -> SeoCategoryMeaningAxes:
    row = session.scalars(
        select(SeoCategoryMeaningAxes).where(
            SeoCategoryMeaningAxes.project_id == int(project_id),
            SeoCategoryMeaningAxes.category_id == int(category_id),
            SeoCategoryMeaningAxes.schema_version == CATEGORY_MEANING_AXES_SCHEMA_VERSION,
            SeoCategoryMeaningAxes.source == str(source),
        )
    ).first()
    if row is None:
        row = SeoCategoryMeaningAxes(
            project_id=int(project_id),
            category_id=int(category_id),
            schema_version=CATEGORY_MEANING_AXES_SCHEMA_VERSION,
            source=str(source),
        )
        session.add(row)
    row.status = str(status)
    row.evidence_hash = str(evidence_hash)
    row.axes_payload = axes.model_dump(mode="json")
    row.canonical_text = _canonical_axes_text(axes)
    row.llm_model = llm_model
    row.prompt_version = CATEGORY_MEANING_AXES_PROMPT_VERSION
    row.input_hash = str(input_hash)
    session.flush()
    return row


def get_latest_ready_category_axes(session: Session, *, project_id: int, category_id: int) -> SeoCategoryMeaningAxes | None:
    return session.scalars(
        select(SeoCategoryMeaningAxes)
        .where(
            SeoCategoryMeaningAxes.project_id == int(project_id),
            SeoCategoryMeaningAxes.category_id == int(category_id),
            SeoCategoryMeaningAxes.schema_version == CATEGORY_MEANING_AXES_SCHEMA_VERSION,
            SeoCategoryMeaningAxes.status == "ready",
        )
        .order_by(SeoCategoryMeaningAxes.source.desc(), SeoCategoryMeaningAxes.updated_at.desc())
    ).first()


def _get_or_create_readiness(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> SeoCategoryMatchingReadiness:
    row = session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()
    if row is None:
        row = SeoCategoryMatchingReadiness(project_id=int(project_id), category_id=int(category_id))
        session.add(row)
        session.flush()
    return row


def _latest_query_batch_id(session: Session, *, project_id: int, category_id: int) -> int | None:
    row = session.scalars(
        select(SeoQueryBatch)
        .where(
            SeoQueryBatch.project_id == int(project_id),
            SeoQueryBatch.category_id == int(category_id),
            SeoQueryBatch.status == "completed",
        )
        .order_by(SeoQueryBatch.created_at.desc(), SeoQueryBatch.id.desc())
        .limit(1)
    ).first()
    return int(row.id) if row is not None else None


def _ensure_run_not_cancelled(session: Session, run: SeoCategoryBootstrapRun) -> None:
    try:
        session.refresh(run)
    except Exception as exc:
        raise CategoryBootstrapCancelled("Category bootstrap run no longer exists") from exc
    if str(run.status or "") == "cancelled":
        raise CategoryBootstrapCancelled("Category bootstrap run was cancelled")


def _refresh_readiness_counts(
    session: Session,
    readiness: SeoCategoryMatchingReadiness,
    *,
    project_id: int,
    category_id: int,
) -> None:
    readiness.query_batch_id = _latest_query_batch_id(session, project_id=project_id, category_id=category_id)
    readiness.queries_count = int(
        session.scalar(
            text(
                """
                SELECT COUNT(DISTINCT q.normalized_query)
                FROM seo_queries_normalized q
                JOIN seo_query_batches b
                  ON b.id = q.batch_id
                WHERE q.project_id = :project_id
                  AND q.category_id = :category_id
                  AND b.status = 'completed'
                """
            ),
            {"project_id": int(project_id), "category_id": int(category_id)},
        )
        or 0
    )
    readiness.clusters_count = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryCluster).where(
                SeoQueryCluster.project_id == int(project_id),
                SeoQueryCluster.category_id == int(category_id),
            )
        )
        or 0
    )
    readiness.query_meanings_count = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryMeaning).where(
                SeoQueryMeaning.project_id == int(project_id),
                SeoQueryMeaning.category_id == int(category_id),
                SeoQueryMeaning.status == "ready",
            )
        )
        or 0
    )
    readiness.query_atoms_count = count_ready_query_atoms(session, project_id=project_id, category_id=category_id)
    readiness.embeddings_count = int(
        session.scalar(
            select(func.count()).select_from(SeoMeaningEmbedding).where(
                SeoMeaningEmbedding.project_id == int(project_id),
                SeoMeaningEmbedding.category_id == int(category_id),
            )
        )
        or 0
    )
    axes = get_latest_ready_category_axes(session, project_id=project_id, category_id=category_id)
    readiness.category_axes_status = "ready" if axes is not None else "not_started"


def create_category_bootstrap_run(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    trigger: str,
) -> SeoCategoryBootstrapRun:
    run = SeoCategoryBootstrapRun(
        project_id=int(project_id),
        category_id=int(category_id),
        trigger=str(trigger),
        status="queued",
        current_step="queued",
        step_statuses={},
    )
    session.add(run)
    session.flush()
    readiness = _get_or_create_readiness(session, project_id=project_id, category_id=category_id)
    readiness.status = "building"
    readiness.latest_run_id = int(run.id)
    readiness.last_error = None
    session.flush()
    return run


def _mark_step(session: Session, run: SeoCategoryBootstrapRun, step: str, status: str, payload: Mapping[str, Any] | None = None) -> None:
    statuses = dict(run.step_statuses or {})
    statuses[step] = {"status": status, "at": _utc_now_iso(), **dict(payload or {})}
    run.current_step = step
    run.step_statuses = statuses
    session.flush()


def precompute_category_embeddings(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    provider: LocalPreviewEmbeddingProvider | None = None,
) -> int:
    resolved_provider = provider or LocalPreviewEmbeddingProvider()
    count = 0
    axes = get_latest_ready_category_axes(session, project_id=project_id, category_id=category_id)
    if axes is not None:
        ensure_meaning_embedding(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="category_axes",
            entity_id=int(axes.id),
            canonical_text=str(axes.canonical_text or ""),
            provider=resolved_provider,
        )
        count += 1
    rows = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
        )
    ).all()
    for row in rows:
        ensure_meaning_embedding(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
            canonical_text=str(row.canonical_text or ""),
            provider=resolved_provider,
        )
        count += 1
    return count


def run_category_bootstrap(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    run_id: int | None = None,
    trigger: str = "manual",
    force_refresh: bool = False,
    use_llm: bool = True,
    provider: ChatProvider | None = None,
) -> SeoCategoryBootstrapRun:
    run = (
        session.get(SeoCategoryBootstrapRun, int(run_id))
        if run_id is not None
        else create_category_bootstrap_run(session, project_id=project_id, category_id=category_id, trigger=trigger)
    )
    if run is None:
        raise CategoryBootstrapError(f"Category bootstrap run {run_id} not found")
    if str(run.status or "") == "cancelled":
        return run
    readiness = _get_or_create_readiness(session, project_id=project_id, category_id=category_id)
    readiness.status = "building"
    readiness.latest_run_id = int(run.id)
    run.status = "running"
    run.error = None
    session.flush()

    warnings: list[str] = []
    try:
        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "query_pipeline", "running")
        clustering = run_query_clustering(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            top_limit=20,
            samples_limit=20,
            persist=True,
        )
        _ensure_run_not_cancelled(session, run)
        try:
            run_query_profile_extraction(session, project_id=int(project_id), category_id=int(category_id), top_limit=20, samples_limit=20)
        except Exception as exc:
            warnings.append(f"profile_extraction:{type(exc).__name__}")
        _mark_step(
            session,
            run,
            "query_pipeline",
            "completed",
            {
                "clusters": int(clustering.diagnostics.total_clusters_created),
                "input_queries": int(clustering.diagnostics.total_input_queries),
            },
        )

        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "category_evidence", "running")
        evidence = build_category_evidence_pack(session, project_id=project_id, category_id=category_id)
        run.input_hash = evidence.evidence_hash
        _mark_step(session, run, "category_evidence", "completed", {"evidence_hash": evidence.evidence_hash})

        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "category_axes_deterministic", "running")
        deterministic_axes = _axes_from_evidence(evidence)
        deterministic_input_hash = stable_hash(
            {
                "schema_version": CATEGORY_MEANING_AXES_SCHEMA_VERSION,
                "source": "deterministic",
                "evidence_hash": evidence.evidence_hash,
                "axes": deterministic_axes.model_dump(mode="json"),
            }
        )
        _upsert_axes(
            session,
            project_id=project_id,
            category_id=category_id,
            source="deterministic",
            evidence_hash=evidence.evidence_hash,
            axes=deterministic_axes,
            input_hash=deterministic_input_hash,
        )
        _mark_step(session, run, "category_axes_deterministic", "completed")

        axes_source = "deterministic"
        if use_llm:
            _ensure_run_not_cancelled(session, run)
            _mark_step(session, run, "category_axes_llm", "running")
            try:
                prompt = _prompt_for_axes(evidence, deterministic_axes)
                resolved_provider = provider or OpenRouterProvider()
                response = resolved_provider.generate_chat(
                    [ChatMessage(role="user", content=prompt)],
                    temperature=0.1,
                    max_tokens=4096,
                )
                parsed, repair_raw_response = _parse_or_repair_llm_json(
                    content=response.content,
                    provider=resolved_provider,
                    original_prompt=prompt,
                )
                enhanced_axes = _merge_axes(deterministic_axes, parsed)
                enhanced_input_hash = stable_hash(
                    {
                        "schema_version": CATEGORY_MEANING_AXES_SCHEMA_VERSION,
                        "source": "llm_enhanced",
                        "model": response.model,
                        "evidence_hash": evidence.evidence_hash,
                        "axes": enhanced_axes.model_dump(mode="json"),
                    }
                )
                _store_axes_artifact(
                    project_id=project_id,
                    category_id=category_id,
                    source="llm_enhanced",
                    input_hash=enhanced_input_hash,
                    prompt=prompt,
                    raw_response={
                        "initial": dict(response.raw_response or {}) or {"model": response.model, "content": response.content},
                        "repair": dict(repair_raw_response or {}) if repair_raw_response is not None else None,
                    },
                    parsed=enhanced_axes.model_dump(mode="json"),
                )
                _upsert_axes(
                    session,
                    project_id=project_id,
                    category_id=category_id,
                    source="llm_enhanced",
                    evidence_hash=evidence.evidence_hash,
                    axes=enhanced_axes,
                    input_hash=enhanced_input_hash,
                    llm_model=str(response.model or getattr(resolved_provider, "chat_model", None) or "unknown_model"),
                )
                axes_source = "llm_enhanced"
                _mark_step(session, run, "category_axes_llm", "completed")
            except Exception as exc:
                warnings.append(f"category_axes_llm:{type(exc).__name__}")
                _mark_step(session, run, "category_axes_llm", "failed", {"error": str(exc)[:500]})

        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "query_meaning_library", "running")
        library = build_query_meaning_library(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            limit=None,
            force_refresh=bool(force_refresh or axes_source == "llm_enhanced"),
            use_llm=False,
        )
        _mark_step(
            session,
            run,
            "query_meaning_library",
            "completed" if library.errors == 0 else "completed_with_warnings",
            {
                "processed": int(library.processed),
                "created": int(library.created),
                "updated": int(library.updated),
                "skipped": int(library.skipped),
                "errors": int(library.errors),
                "total_clusters": int(library.total_clusters),
            },
        )
        if library.errors:
            warnings.append(f"query_meaning_library_errors:{library.errors}")

        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "query_atoms", "running")
        query_atoms = build_query_atoms_for_category(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            limit=None,
            force_refresh=bool(force_refresh or axes_source == "llm_enhanced"),
            use_llm=False,
        )
        _mark_step(
            session,
            run,
            "query_atoms",
            "completed" if int(query_atoms.get("errors") or 0) == 0 else "completed_with_warnings",
            {
                "total": int(query_atoms.get("total") or 0),
                "created": int(query_atoms.get("created") or 0),
                "updated": int(query_atoms.get("updated") or 0),
                "skipped": int(query_atoms.get("skipped") or 0),
                "errors": int(query_atoms.get("errors") or 0),
            },
        )
        if int(query_atoms.get("errors") or 0):
            warnings.append(f"query_atoms_errors:{query_atoms.get('errors')}")

        _ensure_run_not_cancelled(session, run)
        _mark_step(session, run, "embedding_precompute", "running")
        embeddings = precompute_category_embeddings(session, project_id=project_id, category_id=category_id)
        _mark_step(session, run, "embedding_precompute", "completed", {"embeddings": int(embeddings)})

        run.status = "completed_with_warnings" if warnings else "completed"
        run.current_step = "completed"
        readiness.status = "ready_for_matching" if axes_source == "llm_enhanced" else "ready_with_fallback"
        readiness.last_error = "; ".join(warnings) if warnings else None
        _refresh_readiness_counts(session, readiness, project_id=project_id, category_id=category_id)
        session.flush()
        return run
    except CategoryBootstrapCancelled:
        session.rollback()
        return run
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        readiness.status = "failed"
        readiness.last_error = run.error
        _refresh_readiness_counts(session, readiness, project_id=project_id, category_id=category_id)
        session.flush()
        raise


def run_category_bootstrap_background(run_id: int, *, force_refresh: bool = False, use_llm: bool = True) -> None:
    session = SessionLocal()
    try:
        run = session.get(SeoCategoryBootstrapRun, int(run_id))
        if run is None:
            return
        run_category_bootstrap(
            session,
            project_id=int(run.project_id),
            category_id=int(run.category_id),
            run_id=int(run.id),
            trigger=str(run.trigger),
            force_refresh=force_refresh,
            use_llm=use_llm,
        )
        session.commit()
    except Exception:
        session.rollback()
        try:
            run = session.get(SeoCategoryBootstrapRun, int(run_id))
            if run is not None:
                readiness = _get_or_create_readiness(session, project_id=int(run.project_id), category_id=int(run.category_id))
                run.status = "failed"
                readiness.status = "failed"
                readiness.latest_run_id = int(run.id)
                readiness.last_error = run.error or "Category bootstrap failed"
                session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()


def get_category_bootstrap_status(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> CategoryBootstrapStatusResponse:
    readiness = get_readiness_row(session, project_id=project_id, category_id=category_id)
    if readiness is None:
        return CategoryBootstrapStatusResponse(
            project_id=int(project_id),
            category_id=int(category_id),
            readiness_status="not_started",
            latest_run_id=None,
            run_status=None,
            current_step=None,
            step_statuses={},
            queries_count=0,
            clusters_count=0,
            query_meanings_count=0,
            query_atoms_count=0,
            embeddings_count=0,
            category_axes_status="not_started",
            last_error=None,
            updated_at=None,
        )
    _refresh_readiness_counts(session, readiness, project_id=project_id, category_id=category_id)
    run = session.get(SeoCategoryBootstrapRun, int(readiness.latest_run_id)) if readiness.latest_run_id else None
    session.flush()
    return CategoryBootstrapStatusResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        readiness_status=str(readiness.status or "not_started"),  # type: ignore[arg-type]
        latest_run_id=int(readiness.latest_run_id) if readiness.latest_run_id else None,
        run_status=str(run.status) if run is not None else None,  # type: ignore[arg-type]
        current_step=str(run.current_step) if run is not None and run.current_step else None,
        step_statuses=dict(run.step_statuses or {}) if run is not None else {},
        queries_count=int(readiness.queries_count or 0),
        clusters_count=int(readiness.clusters_count or 0),
        query_meanings_count=int(readiness.query_meanings_count or 0),
        query_atoms_count=int(getattr(readiness, "query_atoms_count", 0) or 0),
        embeddings_count=int(readiness.embeddings_count or 0),
        category_axes_status=str(readiness.category_axes_status or "not_started"),
        last_error=readiness.last_error,
        updated_at=readiness.updated_at.isoformat() if getattr(readiness, "updated_at", None) else None,
    )


def get_readiness_row(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> SeoCategoryMatchingReadiness | None:
    return session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()
