"""WB SEO text generation service."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import settings
from app.models import SeoContentVersion, SeoGenerationRun, SeoSkuQuerySet, SeoSkuQuerySetItem
from app.schemas.seo_generation import (
    GeneratedCard,
    GeneratedCharacteristic,
    GenerationValidationIssue,
    SeoRelevanceQueryCoverage,
    SeoRelevanceReport,
    SeoRelevanceV2QueryScore,
    SeoRelevanceV2Report,
    SeoGenerationLatestResponse,
    SeoGenerationRunResponse,
)
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.quality import (
    QualityMode,
    QualityState,
    infer_quality_mode,
    make_reason,
)
from app.services.seo.query_meaning_matcher.embeddings import LocalPreviewEmbeddingProvider, cosine_similarity
from app.services.seo.query_pipeline import normalize_query_text
from app.services.seo.sku_meaning.evidence import build_sku_evidence_pack


def _coerce_quality_mode(value: Any) -> QualityMode | None:
    """Best-effort coercion of a stored quality_mode string to QualityMode.

    Returns None when the upstream value is missing or unrecognized so the
    caller can treat "no upstream signal" as a no-op rather than a downgrade.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return QualityMode(value.lower())
    except ValueError:
        return None


GENERATION_PROMPT_VERSION = "wb_card_system_v1"
GENERATION_VALIDATOR_VERSION = "wb_card_validator_v1"
SEO_RELEVANCE_TARGET_SCORE = 70
SEO_RELEVANCE_RETRY_SCORE = 55

_SECTION_DELIMITERS = [
    "===== НАЗВАНИЕ =====",
    "===== ХАРАКТЕРИСТИКИ =====",
    "===== ОПИСАНИЕ =====",
    "===== ОТЧЁТ =====",
]

_TITLE_STOP_WORDS = {
    "купить",
    "цена",
    "стоимость",
    "скидка",
    "распродажа",
    "акция",
    "лучший",
    "лучшая",
    "лучшее",
    "лучшие",
    "идеальный",
    "идеальная",
    "идеальное",
    "элегантный",
    "элегантная",
    "элегантное",
    "премиальный",
    "премиальная",
    "премиальное",
    "уникальный",
    "уникальная",
    "уникальное",
    "шикарный",
    "шикарная",
    "шикарное",
    "качественный",
    "качественная",
}

_TITLE_FORBIDDEN_RE = re.compile(r"[/⭐★♥✓❤🔥💎!]|[A-ZА-ЯЁ]{4,}")


class SeoGenerationError(Exception):
    """Raised when generation cannot be completed."""


def _prompt_path() -> Path:
    return Path(__file__).resolve().parent / "prompts" / f"{GENERATION_PROMPT_VERSION}.md"


def _load_system_prompt() -> str:
    return _prompt_path().read_text(encoding="utf-8")


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _strings(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, Mapping):
        for item in value.values():
            result.extend(_strings(item))
        return result
    for item in _as_list(value):
        if isinstance(item, Mapping):
            result.extend(_strings(item))
        elif isinstance(item, list):
            result.extend(_strings(item))
        else:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
    return result


def _flatten_characteristics(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        items = []
        for key, raw in value.items():
            text = ", ".join(_strings(raw)) if isinstance(raw, (list, dict)) else str(raw or "")
            if str(key).strip() and text.strip():
                items.append(f"{key}: {text.strip()}")
        return items
    return _strings(value)


def _query_row_to_dict(row: SeoSkuQuerySetItem) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "display_query": str(row.display_query),
        "normalized_query_text": str(row.normalized_query_text),
        "cluster_key": row.cluster_key,
        "bucket": str(row.bucket),
        "score": float(row.score or 0),
        "ranking_value_used": float(row.ranking_value_used) if row.ranking_value_used is not None else None,
        "selection_state": str(row.selection_state or "auto_selected"),
        "reasons": list((row.reasons_payload or {}).get("user_reasons") or []),
        "matched_atoms": list((row.reasons_payload or {}).get("matched_atoms") or []),
        "missing_atoms": list((row.reasons_payload or {}).get("missing_atoms") or []),
        "conflict_atoms": list((row.reasons_payload or {}).get("conflict_atoms") or []),
    }


def _load_query_set(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    query_set_id: int | None,
    allow_draft: bool,
) -> SeoSkuQuerySet:
    stmt = select(SeoSkuQuerySet).where(
        SeoSkuQuerySet.project_id == int(project_id),
        SeoSkuQuerySet.category_id == int(category_id),
        SeoSkuQuerySet.nm_id == int(nm_id),
    )
    if query_set_id is not None:
        stmt = stmt.where(SeoSkuQuerySet.id == int(query_set_id))
    elif not allow_draft:
        # Iteration 2 (WS-C): the candidate path projects matcher_v2 traces
        # into a ``status='candidate'`` SeoSkuQuerySet and tracks operator
        # intent through ``approval_state``. The legacy ``status='confirmed'``
        # selection stays fully supported; additionally we accept a candidate
        # row once its ``approval_state`` is in {candidate, approved}. Draft
        # / preview rows are still refused unless ``allow_draft=True``.
        stmt = stmt.where(
            (SeoSkuQuerySet.status == "confirmed")
            | (
                (SeoSkuQuerySet.status == "candidate")
                & (SeoSkuQuerySet.approval_state.in_(("candidate", "approved")))
            )
        )
    row = session.scalars(stmt.order_by(desc(SeoSkuQuerySet.updated_at), desc(SeoSkuQuerySet.id))).first()
    if row is None:
        raise SeoGenerationError("Confirmed query set is required before generation")
    if not allow_draft:
        is_confirmed_legacy = row.status == "confirmed"
        is_candidate_ready = (
            row.status == "candidate"
            and str(getattr(row, "approval_state", "") or "") in {"candidate", "approved"}
        )
        if not (is_confirmed_legacy or is_candidate_ready):
            raise SeoGenerationError("Query set must be confirmed before generation")
    return row


def _query_groups(session: Session, query_set: SeoSkuQuerySet) -> dict[str, list[dict[str, Any]]]:
    rows = session.scalars(
        select(SeoSkuQuerySetItem)
        .where(SeoSkuQuerySetItem.query_set_id == int(query_set.id))
        .order_by(SeoSkuQuerySetItem.bucket.asc(), desc(SeoSkuQuerySetItem.score), desc(SeoSkuQuerySetItem.ranking_value_used))
    ).all()
    groups = {"primary": [], "secondary": [], "broad_context": [], "excluded": [], "rejected": []}
    for row in rows:
        item = _query_row_to_dict(row)
        state = item["selection_state"]
        bucket = item["bucket"]
        if state == "excluded":
            groups["excluded"].append(item)
        elif bucket == "rejected":
            groups["rejected"].append(item)
        elif bucket == "primary":
            groups["primary"].append(item)
        elif bucket == "secondary":
            groups["secondary"].append(item)
        elif bucket == "broad":
            groups["broad_context"].append(item)
    return groups


def _apply_main_query(groups: dict[str, list[dict[str, Any]]], main_query_text: str | None) -> str | None:
    def first_primary() -> str | None:
        primary_items = groups.get("primary") or []
        return str(primary_items[0].get("display_query") or "") if primary_items else None

    normalized_main = normalize_query_text(str(main_query_text or ""))
    if not normalized_main:
        return first_primary()

    for bucket in ("primary", "secondary", "broad_context"):
        items = groups.get(bucket) or []
        for index, item in enumerate(items):
            if normalize_query_text(str(item.get("display_query") or "")) != normalized_main:
                continue
            selected = items.pop(index)
            selected["bucket"] = "primary"
            groups.setdefault("primary", []).insert(0, selected)
            if bucket != "primary":
                groups[bucket] = items
            return str(selected.get("display_query") or "")
    return first_primary()


def _seo_target_items_from_groups(groups: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket, limit, priority in (("primary", 10, 1), ("secondary", 8, 2), ("broad_context", 4, 3)):
        for item in (groups.get(bucket) or [])[:limit]:
            query = str(item.get("display_query") or "").strip()
            normalized = normalize_query_text(query)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(
                {
                    "query": query,
                    "bucket": bucket,
                    "priority": priority,
                    "score": item.get("score"),
                    "ranking_value_used": item.get("ranking_value_used"),
                }
            )
    return result


def _build_generation_brief(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    query_set_id: int | None,
    main_query_text: str | None,
    brand_voice: str,
    allow_draft_query_set: bool,
) -> tuple[dict[str, Any], SeoSkuQuerySet]:
    evidence = build_sku_evidence_pack(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
    query_set = _load_query_set(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        query_set_id=query_set_id,
        allow_draft=allow_draft_query_set,
    )
    query_groups = _query_groups(session, query_set)
    resolved_main_query = _apply_main_query(query_groups, main_query_text)
    seo_target_items = _seo_target_items_from_groups(query_groups)
    if not query_groups["primary"] and not query_groups["secondary"]:
        raise SeoGenerationError("At least one primary or secondary selected query is required")

    product = evidence.product.model_dump(mode="json")
    meaning = {}
    if isinstance(evidence.product_projection, Mapping):
        meaning = dict(evidence.product_projection)

    functional = meaning.get("functional") if isinstance(meaning.get("functional"), Mapping) else {}
    expressive = meaning.get("expressive") if isinstance(meaning.get("expressive"), Mapping) else {}
    key_facts = _strings(product.get("title")) + _flatten_characteristics(product.get("characteristics"))
    key_facts.extend(_strings(product.get("sizes")))
    key_facts.extend(_strings(product.get("colors")))
    key_facts.extend(_strings(product.get("dimensions")))
    key_facts = list(dict.fromkeys([item for item in key_facts if item]))[:40]

    brief = {
        "schema_version": "ecomcore_generation_brief_v1",
        "product": {
            "project_id": int(project_id),
            "category_id": int(category_id),
            "nm_id": int(nm_id),
            "vendor_code": product.get("vendor_code"),
            "brand": product.get("brand"),
            "current_title": product.get("title"),
            "current_description": product.get("description"),
            "subject_name": product.get("subject_name"),
            "characteristics": product.get("characteristics"),
            "sizes": product.get("sizes"),
            "colors": product.get("colors"),
            "dimensions": product.get("dimensions"),
        },
        "meaning": {
            "functional": functional,
            "expressive": expressive,
            "category_prior": evidence.category_prior,
            "product_projection_flags": evidence.product_projection_flags,
        },
        "evidence": {
            "key_facts": key_facts,
            "reviews": [item.model_dump(mode="json") for item in evidence.reviews[:12]],
            "warnings": evidence.warnings,
        },
        "query_set": {
            "id": int(query_set.id),
            "status": str(query_set.status),
            "main_query_text": resolved_main_query,
            "matcher_version": query_set.matcher_version,
            "atoms_version": query_set.atoms_version,
            **query_groups,
        },
        "seo_targets": {
            "main_query_text": resolved_main_query,
            "target_score": SEO_RELEVANCE_TARGET_SCORE,
            "title_rule": (
                f"Название должно начинаться с фразы '{resolved_main_query}'"
                if resolved_main_query
                else "Название должно начинаться с первого primary query"
            ),
            "focus_queries": seo_target_items,
            "coverage_policy": {
                "main_query": "обязателен в названии и в первых 3 словах",
                "primary": "покрыть главный запрос и несколько top primary без перечисления вариантов подряд",
                "secondary": "использовать только естественные и фактически подходящие secondary",
                "broad_context": "использовать как контекст, не делать главным ключом",
            },
        },
        "generation_policy": {
            "brand_voice": brand_voice,
            "allow_characteristics_draft": True,
            "max_title_chars": 60,
            "max_description_chars": 5000,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "validator_version": GENERATION_VALIDATOR_VERSION,
        },
        "source": {
            "evidence_hash": evidence.evidence_hash,
            "query_set_source_hash": query_set.source_hash,
        },
    }
    return brief, query_set


def _extract_sections(raw: str) -> dict[str, str]:
    for delimiter in _SECTION_DELIMITERS:
        if delimiter not in raw:
            raise SeoGenerationError(f"Missing output section delimiter: {delimiter}")
    sections: dict[str, str] = {}
    for index, delimiter in enumerate(_SECTION_DELIMITERS):
        section_name = delimiter.strip("= ").strip()
        start = raw.find(delimiter) + len(delimiter)
        end = raw.find(_SECTION_DELIMITERS[index + 1]) if index + 1 < len(_SECTION_DELIMITERS) else len(raw)
        sections[section_name] = raw[start:end].strip()
    return sections


def parse_generated_card(raw: str) -> GeneratedCard:
    sections = _extract_sections(raw)
    characteristics: list[GeneratedCharacteristic] = []
    for line in sections["ХАРАКТЕРИСТИКИ"].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            raise SeoGenerationError(f"Characteristic line has no colon: {stripped}")
        field, _, value = stripped.partition(":")
        characteristics.append(GeneratedCharacteristic(field=field.strip(), value=value.strip()))

    report = _parse_report(sections["ОТЧЁТ"])
    return GeneratedCard(
        title=sections["НАЗВАНИЕ"].splitlines()[0].strip(),
        characteristics=characteristics,
        description=sections["ОПИСАНИЕ"].strip(),
        report=report,
    )


def _parse_report(block: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-") and current_key:
            result.setdefault(current_key, []).append(line.lstrip("- ").strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            result[key] = []
            continue
        try:
            result[key] = ast.literal_eval(value)
        except Exception:
            if value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value.strip('"')
    return result


def _description_blocks(description: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", description.strip()) if block.strip()]


_QUERY_PHRASE_STOPWORDS = {"в", "во", "для", "на", "с", "со", "к", "ко", "по", "и", "или"}
_RU_TOKEN_ENDINGS = (
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ому",
    "ыми",
    "ими",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ый",
    "ий",
    "ой",
    "ах",
    "ях",
    "ам",
    "ям",
    "ом",
    "ем",
    "а",
    "я",
    "ы",
    "и",
    "е",
    "у",
    "ю",
)


def _query_tokens(value: str, *, keep_stopwords: bool = True) -> list[str]:
    tokens = normalize_query_text(value).split()
    if keep_stopwords:
        return tokens
    return [token for token in tokens if token not in _QUERY_PHRASE_STOPWORDS]


def _soft_token(token: str) -> str:
    token = str(token or "").strip()
    if len(token) <= 4:
        return token
    for ending in _RU_TOKEN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def _normalized_contains(text: str, query: str) -> bool:
    normalized_text = normalize_query_text(text)
    normalized_query = normalize_query_text(query)
    if not normalized_query:
        return False
    if normalized_query in normalized_text:
        return True
    query_tokens = [token for token in normalized_query.split() if len(token) > 2]
    if not query_tokens:
        return False
    if all(token in normalized_text for token in query_tokens):
        return True
    text_stems = {_soft_token(token) for token in normalized_text.split() if len(token) > 2}
    return all(_soft_token(token) in text_stems for token in query_tokens)


def _contains_blocked_query_phrase(text: str, query: str) -> bool:
    normalized_text = normalize_query_text(text)
    normalized_query = normalize_query_text(query)
    if not normalized_query:
        return False
    if normalized_query in normalized_text:
        return True

    text_tokens = _query_tokens(text, keep_stopwords=False)
    query_tokens = _query_tokens(query, keep_stopwords=False)
    if not query_tokens:
        return False
    if len(query_tokens) == 1:
        return query_tokens[0] in text_tokens

    max_window = len(query_tokens) + 3
    for start_index, token in enumerate(text_tokens):
        if token != query_tokens[0]:
            continue
        query_index = 1
        last_match_index = start_index
        for text_index in range(start_index + 1, min(len(text_tokens), start_index + max_window)):
            if text_tokens[text_index] == query_tokens[query_index]:
                query_index += 1
                last_match_index = text_index
                if query_index == len(query_tokens):
                    return last_match_index - start_index + 1 <= max_window
    return False


def _all_card_text(card: GeneratedCard) -> str:
    chars = " ".join(f"{item.field} {item.value}" for item in card.characteristics)
    return f"{card.title}\n{chars}\n{card.description}"


def _count_normalized_occurrences(text: str, query: str) -> int:
    normalized_text = normalize_query_text(text)
    normalized_query = normalize_query_text(query)
    if not normalized_text or not normalized_query:
        return 0
    exact = normalized_text.count(normalized_query)
    if exact:
        return exact
    return 1 if _normalized_contains(normalized_text, normalized_query) else 0


def _report_list(report: Mapping[str, Any], key: str) -> list[str]:
    value = report.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _selected_queries_from_brief(brief: Mapping[str, Any]) -> list[str]:
    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    primary = _as_list(query_set.get("primary"))
    secondary = _as_list(query_set.get("secondary"))
    broad = _as_list(query_set.get("broad_context"))
    return [str(item.get("display_query") or "") for item in [*primary, *secondary, *broad] if isinstance(item, Mapping)]


def _blocked_queries_from_brief(brief: Mapping[str, Any]) -> list[str]:
    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    rejected = _as_list(query_set.get("rejected"))
    excluded = _as_list(query_set.get("excluded"))
    return [str(item.get("display_query") or "") for item in [*rejected, *excluded] if isinstance(item, Mapping)]


def _selected_query_items_from_brief(brief: Mapping[str, Any]) -> list[dict[str, Any]]:
    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    main_query = normalize_query_text(str(query_set.get("main_query_text") or ""))
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket, weight, limit in (("primary", 3.0, 10), ("secondary", 2.0, 8), ("broad_context", 1.0, 4)):
        bucket_items = _as_list(query_set.get(bucket))
        for item in bucket_items:
            if not isinstance(item, Mapping):
                continue
            query = str(item.get("display_query") or "").strip()
            normalized = normalize_query_text(query)
            if normalized and normalized == main_query and normalized not in seen:
                result.append(
                    {
                        "query": query,
                        "bucket": bucket,
                        "weight": weight,
                        "matched_atoms": list(item.get("matched_atoms") or []),
                        "missing_atoms": list(item.get("missing_atoms") or []),
                        "conflict_atoms": list(item.get("conflict_atoms") or []),
                    }
                )
                seen.add(normalized)
        added_from_bucket = sum(1 for item in result if item["bucket"] == bucket)
        for item in bucket_items:
            if added_from_bucket >= limit:
                break
            if not isinstance(item, Mapping):
                continue
            query = str(item.get("display_query") or "").strip()
            normalized = normalize_query_text(query)
            if not normalized or normalized in seen:
                continue
            result.append(
                {
                    "query": query,
                    "bucket": bucket,
                    "weight": weight,
                    "matched_atoms": list(item.get("matched_atoms") or []),
                    "missing_atoms": list(item.get("missing_atoms") or []),
                    "conflict_atoms": list(item.get("conflict_atoms") or []),
                }
            )
            seen.add(normalized)
            added_from_bucket += 1
    return result


def build_seo_relevance_report(
    card: GeneratedCard,
    brief: Mapping[str, Any],
    issues: list[GenerationValidationIssue],
) -> SeoRelevanceReport:
    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    main_query = str(query_set.get("main_query_text") or "").strip() or None
    query_items = _selected_query_items_from_brief(brief)
    coverage: list[SeoRelevanceQueryCoverage] = []
    total_weight = 0.0
    covered_weight = 0.0
    title_queries = 0
    description_queries = 0
    overused: list[str] = []
    missing_primary: list[str] = []

    chars_text = " ".join(f"{item.field} {item.value}" for item in card.characteristics)
    all_text = _all_card_text(card)
    for item in query_items:
        query = str(item["query"])
        weight = float(item["weight"])
        zones: list[str] = []
        if _normalized_contains(card.title, query):
            zones.append("title")
            title_queries += 1
        if _normalized_contains(chars_text, query):
            zones.append("characteristics")
        if _normalized_contains(card.description, query):
            zones.append("description")
            description_queries += 1
        occurrences = _count_normalized_occurrences(all_text, query)
        found = bool(zones)
        total_weight += weight
        if found:
            covered_weight += weight
        elif item["bucket"] == "primary":
            missing_primary.append(query)
        if occurrences > 3:
            overused.append(query)
        coverage.append(
            SeoRelevanceQueryCoverage(
                query=query,
                bucket=str(item["bucket"]),
                weight=weight,
                found=found,
                zones=zones,
                occurrences=occurrences,
            )
        )

    weighted_coverage = (covered_weight / total_weight) if total_weight > 0 else 0.0
    first_words = " ".join(card.title.split()[:3])
    main_in_title = bool(main_query and _normalized_contains(card.title, main_query))
    main_in_title_start = bool(main_query and _normalized_contains(first_words, main_query))
    blocking_errors = [issue for issue in issues if issue.severity == "error"]
    score = round(weighted_coverage * 70)
    if main_in_title_start:
        score += 15
    elif main_in_title:
        score += 8
    elif main_query and _normalized_contains(all_text, main_query):
        score += 4
    score += min(10, len({zone for item in coverage for zone in item.zones}) * 4)
    if not blocking_errors:
        score += 5
    score -= min(20, len(overused) * 5)
    if blocking_errors:
        score = min(score, 45)
    score = max(0, min(100, int(score)))
    notes: list[str] = []
    if missing_primary:
        notes.append(f"Не покрыто primary-запросов: {len(missing_primary)}")
    if not main_in_title_start:
        notes.append("Главный запрос не найден в первых 3 словах названия")
    if overused:
        notes.append(f"Переспам запросов: {len(overused)}")
    if blocking_errors:
        notes.append(f"Есть validation errors: {len(blocking_errors)}")
    grade = "high" if score >= 80 else "medium" if score >= 55 else "low"
    return SeoRelevanceReport(
        score=score,
        grade=grade,  # type: ignore[arg-type]
        main_query_text=main_query,
        main_query_in_title=main_in_title,
        main_query_in_title_start=main_in_title_start,
        weighted_coverage=round(weighted_coverage, 4),
        selected_queries_count=len(query_items),
        covered_queries_count=sum(1 for item in coverage if item.found),
        title_queries_count=title_queries,
        description_queries_count=description_queries,
        overused_queries=overused,
        missing_primary_queries=missing_primary,
        query_coverage=coverage,
        notes=notes,
    )


_RELEVANCE_STOPWORDS = {
    *_QUERY_PHRASE_STOPWORDS,
    "это",
    "как",
    "что",
    "или",
    "без",
    "при",
    "над",
    "под",
    "из",
    "от",
    "до",
    "по",
    "шт",
    "мл",
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _average(values: Sequence[float]) -> float:
    values = [float(value) for value in values]
    return sum(values) / len(values) if values else 0.0


def _weighted_average(pairs: Sequence[tuple[float, float]]) -> float:
    total_weight = sum(float(weight) for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return sum(float(value) * float(weight) for value, weight in pairs) / total_weight


def _content_stems(text: str) -> list[str]:
    stems: list[str] = []
    for token in _query_tokens(text, keep_stopwords=False):
        stem = _soft_token(token)
        if len(stem) > 2 and stem not in _RELEVANCE_STOPWORDS:
            stems.append(stem)
    return stems


def _soft_overlap_score(left: str, right: str) -> float:
    left_stems = _content_stems(left)
    if not left_stems:
        return 0.0
    right_stems = set(_content_stems(right))
    if not right_stems:
        return 0.0
    matched = 0
    for stem in left_stems:
        if stem in right_stems:
            matched += 1
            continue
        if len(stem) >= 4 and any(other.startswith(stem) or stem.startswith(other) for other in right_stems if len(other) >= 4):
            matched += 1
    return _clamp01(matched / len(left_stems))


def _field_texts(card: GeneratedCard) -> dict[str, str]:
    blocks = _description_blocks(card.description)
    return {
        "title": card.title,
        "characteristics": " ".join(f"{item.field} {item.value}" for item in card.characteristics),
        "lead_description": " ".join(blocks[:2]),
        "description": card.description,
    }


def _field_lexical_scores(query: str, fields: Mapping[str, str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for field, text in fields.items():
        score = _soft_overlap_score(query, text)
        if _normalized_contains(text, query):
            score = max(score, 0.92)
        scores[field] = round(_clamp01(score), 4)
    return scores


def _zones_from_field_scores(scores: Mapping[str, float]) -> list[str]:
    zones: list[str] = []
    for zone in ("title", "characteristics", "lead_description", "description"):
        threshold = 0.66 if zone != "description" else 0.75
        if float(scores.get(zone) or 0) >= threshold:
            zones.append(zone)
    return zones


def _zone_score(zones: Sequence[str]) -> float:
    if "title" in zones:
        return 1.0
    if "characteristics" in zones:
        return 0.8
    if "lead_description" in zones:
        return 0.7
    if "description" in zones:
        return 0.5
    return 0.0


def _field_aware_lexical_score(scores: Mapping[str, float]) -> float:
    return round(
        _clamp01(
            max(
                float(scores.get("title") or 0),
                float(scores.get("characteristics") or 0) * 0.82,
                float(scores.get("lead_description") or 0) * 0.76,
                float(scores.get("description") or 0) * 0.58,
            )
        ),
        4,
    )


def _atom_value(atom: Any) -> str:
    text = str(atom or "").strip()
    if not text:
        return ""
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    text = re.sub(r"^missing\s+[^:]+:\s*", "", text, flags=re.IGNORECASE).strip()
    return text


def _supported_atom_values(atoms: Sequence[Any], card_text: str) -> tuple[list[str], list[str]]:
    supported: list[str] = []
    unsupported: list[str] = []
    for atom in atoms:
        value = _atom_value(atom)
        if not value:
            continue
        normalized_value = normalize_query_text(value)
        normalized_card = normalize_query_text(card_text)
        if normalized_value.isdigit():
            is_supported = normalized_value in normalized_card.split()
        else:
            is_supported = _normalized_contains(card_text, value) or _soft_overlap_score(value, card_text) >= 0.75
        target = supported if is_supported else unsupported
        if value not in target:
            target.append(value)
    return supported, unsupported


def _semantic_scores(card_text: str, query_texts: Sequence[str]) -> list[float]:
    provider = LocalPreviewEmbeddingProvider()
    response = provider.embed_texts([card_text, *query_texts])
    if not response.embeddings:
        return [0.0 for _ in query_texts]
    card_vector = response.embeddings[0]
    result: list[float] = []
    for vector in response.embeddings[1:]:
        result.append(round(_clamp01(cosine_similarity(card_vector, vector)), 4))
    return result


def _naturalness_score(card: GeneratedCard, query_items: Sequence[Mapping[str, Any]], issues: Sequence[GenerationValidationIssue]) -> float:
    text = _all_card_text(card)
    stems = _content_stems(text)
    words_count = max(1, len(stems))
    selected_occurrences = sum(_count_normalized_occurrences(text, str(item.get("query") or "")) for item in query_items)
    score = 1.0
    if selected_occurrences / words_count > 0.1:
        score -= 0.18
    if stems:
        top_count = max(stems.count(stem) for stem in set(stems))
        if top_count / words_count > 0.14:
            score -= 0.12
    for issue in issues:
        if issue.check_name == "query_overuse":
            score -= 0.2
        elif issue.severity == "error":
            score -= 0.12
        elif issue.severity == "warning":
            score -= 0.03
    return round(_clamp01(score), 4)


def _truthfulness_score(issues: Sequence[GenerationValidationIssue], query_scores: Sequence[SeoRelevanceV2QueryScore]) -> float:
    score = 1.0
    for issue in issues:
        score -= 0.18 if issue.severity == "error" else 0.04
    conflict_count = sum(1 for item in query_scores if item.conflict_atoms)
    unsupported_hard_count = sum(1 for item in query_scores if item.unsupported_atoms and item.bucket == "primary")
    score -= min(0.18, conflict_count * 0.05)
    score -= min(0.14, unsupported_hard_count * 0.02)
    return round(_clamp01(score), 4)


def build_seo_relevance_v2_report(
    card: GeneratedCard,
    brief: Mapping[str, Any],
    issues: list[GenerationValidationIssue],
) -> SeoRelevanceV2Report:
    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    main_query = str(query_set.get("main_query_text") or "").strip() or None
    query_items = _selected_query_items_from_brief(brief)
    fields = _field_texts(card)
    card_text = "\n".join([fields["title"], fields["characteristics"], fields["lead_description"], fields["description"]])
    semantic_inputs = [
        " ".join(
            [
                str(item.get("query") or ""),
                *[_atom_value(atom) for atom in list(item.get("matched_atoms") or [])],
            ]
        ).strip()
        for item in query_items
    ]
    semantic_values = _semantic_scores(card_text, semantic_inputs) if semantic_inputs else []
    naturalness = _naturalness_score(card, query_items, issues)
    query_scores: list[SeoRelevanceV2QueryScore] = []

    for index, item in enumerate(query_items):
        query = str(item.get("query") or "")
        bucket = str(item.get("bucket") or "")
        weight = float(item.get("weight") or 1.0)
        matched_atoms = list(item.get("matched_atoms") or [])
        missing_atoms = list(item.get("missing_atoms") or [])
        conflict_atoms = list(item.get("conflict_atoms") or [])
        supported_atoms, unsupported_atoms = _supported_atom_values(matched_atoms, card_text)
        field_scores = _field_lexical_scores(query, fields)
        zones = _zones_from_field_scores(field_scores)
        lexical = _field_aware_lexical_score(field_scores)
        semantic = semantic_values[index] if index < len(semantic_values) else 0.0
        if matched_atoms:
            intent = len(supported_atoms) / max(1, len({_atom_value(atom) for atom in matched_atoms if _atom_value(atom)}))
        else:
            intent = max(lexical, semantic * 0.8)
        intent -= min(0.3, len(missing_atoms) * 0.08)
        intent -= min(0.45, len(conflict_atoms) * 0.18)
        intent = _clamp01(intent)
        zones_score = _zone_score(zones)
        if main_query and normalize_query_text(query) == normalize_query_text(main_query):
            first_words = " ".join(card.title.split()[:3])
            if _normalized_contains(first_words, query):
                zones_score = 1.0
                if "title" not in zones:
                    zones.insert(0, "title")

        raw_score = (
            0.30 * intent
            + 0.30 * semantic
            + 0.20 * lexical
            + 0.10 * zones_score
            + 0.10 * naturalness
        )
        if conflict_atoms:
            raw_score -= min(0.2, 0.08 * len(conflict_atoms))
        raw_score = _clamp01(raw_score)
        notes: list[str] = []
        if unsupported_atoms:
            notes.append("часть смысловых признаков запроса не раскрыта в тексте")
        if missing_atoms:
            notes.append("у запроса были missing atoms при подборе")
        if conflict_atoms:
            notes.append("у запроса есть conflict atoms")
        query_scores.append(
            SeoRelevanceV2QueryScore(
                query=query,
                bucket=bucket,
                weight=weight,
                score=round(raw_score * 100),
                intent_score=round(intent, 4),
                semantic_score=round(semantic, 4),
                lexical_score=round(lexical, 4),
                zone_score=round(zones_score, 4),
                naturalness_score=naturalness,
                supported_atoms=supported_atoms,
                unsupported_atoms=unsupported_atoms,
                conflict_atoms=[_atom_value(atom) or str(atom) for atom in conflict_atoms],
                zones=zones,
                notes=notes,
            )
        )

    query_score_by_norm = {normalize_query_text(item.query): item.score / 100 for item in query_scores}
    main_score = query_score_by_norm.get(normalize_query_text(main_query or ""), 0.0)
    primary_scores = [item.score / 100 for item in query_scores if item.bucket == "primary"]
    secondary_scores = [item.score / 100 for item in query_scores if item.bucket in {"secondary", "broad_context"}]
    weighted_all = _weighted_average([(item.score / 100, item.weight) for item in query_scores])
    if main_score <= 0:
        main_score = primary_scores[0] if primary_scores else weighted_all
    primary_avg = _average(primary_scores[:10]) if primary_scores else weighted_all
    secondary_avg = _average(secondary_scores[:8]) if secondary_scores else weighted_all
    truthfulness = _truthfulness_score(issues, query_scores)
    overall = (
        0.35 * main_score
        + 0.35 * primary_avg
        + 0.15 * secondary_avg
        + 0.10 * truthfulness
        + 0.05 * naturalness
    )
    score = max(0, min(100, round(overall * 100)))
    weak_queries = [item.query for item in query_scores if item.score < 55][:8]
    unsupported_intents = list(dict.fromkeys(atom for item in query_scores for atom in item.unsupported_atoms))[:12]
    notes = [
        "V2 оценивает смысловую близость, атомы намерения, зоны текста и естественность, а не только точные фразы.",
    ]
    if weak_queries:
        notes.append(f"Слабых запросов в фокус-наборе: {len(weak_queries)}")
    if unsupported_intents:
        notes.append(f"Не раскрыто смысловых признаков: {len(unsupported_intents)}")
    grade = "high" if score >= 80 else "medium" if score >= 55 else "low"
    return SeoRelevanceV2Report(
        score=score,
        grade=grade,  # type: ignore[arg-type]
        main_query_text=main_query,
        intent_fit=round(_weighted_average([(item.intent_score, item.weight) for item in query_scores]), 4),
        semantic_similarity=round(_weighted_average([(item.semantic_score, item.weight) for item in query_scores]), 4),
        lexical_relevance=round(_weighted_average([(item.lexical_score, item.weight) for item in query_scores]), 4),
        zone_placement=round(_weighted_average([(item.zone_score, item.weight) for item in query_scores]), 4),
        naturalness=naturalness,
        product_truthfulness=truthfulness,
        evaluated_queries_count=len(query_scores),
        strong_queries_count=sum(1 for item in query_scores if item.score >= 70),
        weak_queries=weak_queries,
        unsupported_intents=unsupported_intents,
        query_scores=query_scores,
        notes=notes,
    )


def normalize_generated_card_report(card: GeneratedCard, brief: Mapping[str, Any]) -> GeneratedCard:
    selected_queries = _selected_queries_from_brief(brief)
    selected_by_normalized = {normalize_query_text(query): query for query in selected_queries if query}
    card_text = _all_card_text(card)
    cleaned_used: list[str] = []
    for raw_used in _report_list(card.report, "использованные_запросы"):
        normalized_used = normalize_query_text(raw_used.split("(")[0].strip())
        selected_query = selected_by_normalized.get(normalized_used)
        if not selected_query or selected_query in cleaned_used:
            continue
        if _normalized_contains(card_text, selected_query):
            cleaned_used.append(selected_query)

    if cleaned_used != _report_list(card.report, "использованные_запросы"):
        card.report = dict(card.report or {})
        card.report["использованные_запросы"] = cleaned_used
        card.report["охват_запросов"] = len(cleaned_used)
    return card


def validate_generated_card(card: GeneratedCard, brief: Mapping[str, Any]) -> list[GenerationValidationIssue]:
    issues: list[GenerationValidationIssue] = []

    def add(check_name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> None:
        issues.append(
            GenerationValidationIssue(
                check_name=check_name,
                severity=severity,  # type: ignore[arg-type]
                message=message,
                details=details or {},
            )
        )

    if len(card.title) > 60:
        add("title_length", "error", f"Название {len(card.title)} символов, должно быть <= 60")
    if _TITLE_FORBIDDEN_RE.search(card.title):
        add("title_forbidden_symbols", "error", "В названии найдены запрещенные символы или CAPS")
    title_words = {word.strip(".,:;!?").lower().replace("ё", "е") for word in card.title.split()}
    stop_found = sorted(title_words & {word.replace("ё", "е") for word in _TITLE_STOP_WORDS})
    if stop_found:
        add("title_stop_words", "error", f"В названии запрещенные слова: {', '.join(stop_found)}")
    if len(card.description) > 5000:
        add("description_length", "error", f"Описание {len(card.description)} символов, должно быть <= 5000")
    blocks = _description_blocks(card.description)
    if len(blocks) != 6:
        add("description_blocks", "error", f"Описание содержит {len(blocks)} блоков, должно быть 6")
    if len(card.characteristics) < 8:
        add("characteristics_count", "error", f"Заполнено {len(card.characteristics)} характеристик, минимум 8")

    query_set = brief.get("query_set") if isinstance(brief.get("query_set"), Mapping) else {}
    primary = _as_list(query_set.get("primary"))
    selected_queries = _selected_queries_from_brief(brief)
    blocked_queries = _blocked_queries_from_brief(brief)
    selected_normalized = {normalize_query_text(query) for query in selected_queries if query}
    card_text = _all_card_text(card)

    used_queries = _report_list(card.report, "использованные_запросы")
    for used in used_queries:
        normalized_used = normalize_query_text(used.split("(")[0].strip())
        if normalized_used and normalized_used not in selected_normalized:
            add("used_query_not_selected", "warning", f"Запрос '{used}' помечен как использованный, но его нет в selected query set")
        if not _normalized_contains(card_text, used.split("(")[0].strip()):
            add("used_query_not_found", "warning", f"Запрос '{used}' помечен как использованный, но не найден в тексте")

    for query in blocked_queries:
        if query and _contains_blocked_query_phrase(card_text, query):
            add("blocked_query_used", "error", f"Rejected/excluded query найден в тексте: {query}")

    for query in selected_queries:
        if not query:
            continue
        normalized_card = normalize_query_text(card_text)
        normalized_query = normalize_query_text(query)
        count = normalized_card.count(normalized_query) if normalized_query else 0
        if count > 3:
            add("query_overuse", "error", f"Запрос '{query}' встречается {count} раз (лимит 3)")

    if primary:
        main = str(primary[0].get("display_query") or "") if isinstance(primary[0], Mapping) else ""
        first_words = " ".join(card.title.split()[:3])
        if main and not _normalized_contains(first_words, main):
            add("main_query_title_position", "warning", f"Главный primary query '{main}' не найден в первых 3 словах названия")

    return issues


def _has_errors(issues: list[GenerationValidationIssue]) -> bool:
    return any(item.severity == "error" for item in issues)


def _provider_for_model(model: str, provider: ChatProvider | None) -> ChatProvider:
    if provider is not None:
        return provider
    return OpenRouterProvider(chat_model=model, timeout_seconds=90.0)


def _build_messages(brief: Mapping[str, Any], *, retry_errors: list[str] | None = None) -> list[ChatMessage]:
    user_payload = {
        "input": brief,
        "instruction": "Сгенерируй карточку по системному промпту. Верни только четыре секции.",
    }
    if retry_errors:
        user_payload["previous_validation_errors"] = retry_errors
        user_payload["retry_instruction"] = (
            "Исправь только перечисленные ошибки и SEO-недочеты. Не добавляй новые факты. "
            "Сохрани формат четырех секций. Используй только selected queries и product evidence из входа."
        )
    return [
        ChatMessage(role="system", content=_load_system_prompt()),
        ChatMessage(role="user", content=_stable_json(user_payload)),
    ]


def run_seo_generation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    query_set_id: int | None = None,
    main_query_text: str | None = None,
    brand_voice: str = "экспертный",
    allow_draft_query_set: bool = False,
    provider: ChatProvider | None = None,
) -> SeoGenerationRunResponse:
    brief, query_set = _build_generation_brief(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        query_set_id=query_set_id,
        main_query_text=main_query_text,
        brand_voice=brand_voice,
        allow_draft_query_set=allow_draft_query_set,
    )

    # Iteration 1: propagate upstream quality from the SKU's saved query set.
    # When the query set came from the candidate matcher (matcher_v2), its
    # quality_mode floors the generation run's own quality_mode.
    upstream_quality_mode = _coerce_quality_mode(getattr(query_set, "quality_mode", None))
    upstream_degraded_reasons = list(getattr(query_set, "degraded_reasons", None) or [])
    upstream_matcher_run_id = getattr(query_set, "matcher_run_id", None)
    upstream_category_profile_version = getattr(query_set, "category_profile_version", None)

    run = SeoGenerationRun(
        project_id=int(project_id),
        category_id=int(category_id),
        provider_name=settings.SEO_GENERATION_PROVIDER,
        model_name=settings.SEO_GENERATION_PRIMARY_MODEL,
        status="running",
        request_payload={
            "nm_id": int(nm_id),
            "brief": brief,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "validator_version": GENERATION_VALIDATOR_VERSION,
            "main_query_text": brief.get("query_set", {}).get("main_query_text") if isinstance(brief.get("query_set"), Mapping) else None,
            "primary_model": settings.SEO_GENERATION_PRIMARY_MODEL,
            "fallback_model": settings.SEO_GENERATION_FALLBACK_MODEL,
        },
        response_payload={},
        matcher_run_id=int(upstream_matcher_run_id) if upstream_matcher_run_id is not None else None,
    )
    session.add(run)
    session.flush()

    attempts: list[dict[str, Any]] = []
    last_errors: list[str] | None = None
    # Iteration 1 discipline (CD-2): SEO_GENERATION_MAX_ATTEMPTS default=1.
    # Retry happens ONLY on validator hard errors. V2-relevance is emitted as
    # internal lint, not a retry gate.
    attempt_cap = max(1, int(settings.SEO_GENERATION_MAX_ATTEMPTS))
    models: list[str] = [settings.SEO_GENERATION_PRIMARY_MODEL] * attempt_cap
    if attempt_cap > 1:
        # When the cap is raised (research / ops), the last attempt uses the
        # fallback model — matching prior behavior but only when explicitly
        # opted in.
        models[-1] = settings.SEO_GENERATION_FALLBACK_MODEL
    final_card: GeneratedCard | None = None
    final_issues: list[GenerationValidationIssue] = []
    final_seo_relevance: SeoRelevanceReport | None = None
    final_seo_relevance_v2: SeoRelevanceV2Report | None = None
    final_model: str | None = None

    for attempt_index, model in enumerate(models, start=1):
        final_model = model
        try:
            response = _provider_for_model(model, provider).generate_chat(
                _build_messages(brief, retry_errors=last_errors),
                temperature=float(settings.SEO_GENERATION_TEMPERATURE),
                top_p=float(settings.SEO_GENERATION_TOP_P),
                max_tokens=int(settings.SEO_GENERATION_MAX_TOKENS),
            )
            card = parse_generated_card(response.content)
            card = normalize_generated_card_report(card, brief)
            issues = validate_generated_card(card, brief)
            seo_relevance = build_seo_relevance_report(card, brief, issues)
            seo_relevance_v2 = build_seo_relevance_v2_report(card, brief, issues)
            attempts.append(
                {
                    "attempt": attempt_index,
                    "model": response.model or model,
                    "raw_response": response.raw_response,
                    "content": response.content,
                    "parsed": card.model_dump(mode="json"),
                    "validation": [item.model_dump(mode="json") for item in issues],
                    # Relabeled: relevance is an internal lint, NOT a retry gate.
                    "internal_lint_seo_relevance": seo_relevance.model_dump(mode="json"),
                    "internal_lint_seo_relevance_v2": seo_relevance_v2.model_dump(mode="json"),
                }
            )
            has_validation_errors = _has_errors(issues)
            final_card = card
            final_issues = issues
            final_seo_relevance = seo_relevance
            final_seo_relevance_v2 = seo_relevance_v2
            final_model = response.model or model
            if not has_validation_errors:
                # Accept the first validator-clean attempt. No relevance retry.
                break
            # Validator-hard-error retry: only populate last_errors from errors.
            last_errors = [item.message for item in issues if item.severity == "error"]
        except Exception as exc:
            attempts.append({"attempt": attempt_index, "model": model, "error": f"{type(exc).__name__}: {exc}"})
            last_errors = [str(exc)]

    run.model_name = final_model
    run.response_payload = {
        "attempts": attempts,
        "final_card": final_card.model_dump(mode="json") if final_card is not None else None,
        "validation": [item.model_dump(mode="json") for item in final_issues],
        # Iteration 1: relevance reports are internal lint, not a quality gate.
        "internal_lint_seo_relevance": (
            final_seo_relevance.model_dump(mode="json") if final_seo_relevance is not None else None
        ),
        "internal_lint_seo_relevance_v2": (
            final_seo_relevance_v2.model_dump(mode="json") if final_seo_relevance_v2 is not None else None
        ),
    }

    # Iteration 1 quality_mode for generation:
    # validator-clean ⇒ inherit upstream; validator-error or no card ⇒ degraded.
    has_validator_errors = _has_errors(final_issues)
    gen_state = QualityState(
        upstream_modes={"query_set": upstream_quality_mode}
        if upstream_quality_mode is not None
        else {},
        evidence_signals={
            "validator_clean": final_card is not None and not has_validator_errors,
        },
        extra_reasons=[
            make_reason(
                "generation_validator_errors",
                {"errors": [i.message for i in final_issues if i.severity == "error"]},
            )
        ]
        if has_validator_errors
        else [],
        fallback_taken=final_card is None,
    )
    gen_quality_mode, gen_degraded_reasons = infer_quality_mode(gen_state)
    merged_degraded = list(upstream_degraded_reasons) + [dict(r) for r in gen_degraded_reasons]
    run.quality_mode = gen_quality_mode.value
    run.degraded_reasons = merged_degraded or None

    content_version: SeoContentVersion | None = None
    if final_card is not None:
        content_version = SeoContentVersion(
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
            # Iteration 2 (WS-D): tightened lifecycle. ``preview`` replaces the
            # iteration-1 ``llm_draft`` label. Stays non-publishable; promotion
            # to ``candidate`` / ``approved`` requires the promote endpoint.
            content_kind="preview",
            title=final_card.title,
            description=final_card.description,
            query_snapshot=dict(brief.get("query_set") or {}),
            score_breakdown={
                "source": brief.get("source") or {},
                "generation_policy": brief.get("generation_policy") or {},
                "validation": [item.model_dump(mode="json") for item in final_issues],
                # Internal lint, not a publish gate.
                "internal_lint_seo_relevance": (
                    final_seo_relevance.model_dump(mode="json") if final_seo_relevance is not None else None
                ),
                "internal_lint_seo_relevance_v2": (
                    final_seo_relevance_v2.model_dump(mode="json") if final_seo_relevance_v2 is not None else None
                ),
            },
            status="needs_review",
            # Iteration 1 additive fields.
            quality_mode=gen_quality_mode.value,
            degraded_reasons=merged_degraded or None,
            mode_used="research_preview"
            if not bool(getattr(settings, "SEO_GENERATION_PREVIEW_ENABLED", False))
            or gen_quality_mode != QualityMode.FULL
            else "current",
            publishable=False,  # Iteration 1: nothing produced here is publishable.
            matcher_run_id=int(upstream_matcher_run_id) if upstream_matcher_run_id is not None else None,
            category_profile_version=(
                str(upstream_category_profile_version)
                if upstream_category_profile_version
                else None
            ),
        )
        session.add(content_version)
        session.flush()
        run.content_version_id = int(content_version.id)
        run.status = "completed"
    else:
        run.status = "failed"
        run.error_text = "; ".join(last_errors or ["generation failed"])
    session.flush()

    return SeoGenerationRunResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        run_id=int(run.id),
        query_set_id=int(query_set.id),
        content_version_id=int(content_version.id) if content_version is not None else None,
        status="completed" if final_card is not None else "failed",
        content_status=content_version.status if content_version is not None else None,
        provider_name=run.provider_name,
        model_name=run.model_name,
        attempts=len(attempts),
        prompt_version=GENERATION_PROMPT_VERSION,
        validator_version=GENERATION_VALIDATOR_VERSION,
        generated_card=final_card,
        validation_results=final_issues,
        seo_relevance=final_seo_relevance,
        seo_relevance_v2=final_seo_relevance_v2,
        error_text=run.error_text,
        quality_mode=gen_quality_mode.value,
        degraded_reasons=merged_degraded,
        mode_used=content_version.mode_used if content_version is not None else "research_preview",
        publishable=False,
        matcher_run_id=int(upstream_matcher_run_id) if upstream_matcher_run_id is not None else None,
    )


def _generated_card_from_latest(content: SeoContentVersion, run: SeoGenerationRun | None) -> GeneratedCard:
    response_payload = dict(run.response_payload or {}) if run is not None else {}
    final_card = response_payload.get("final_card")
    if isinstance(final_card, Mapping):
        try:
            return GeneratedCard.model_validate(final_card)
        except Exception:
            pass
    return GeneratedCard(
        title=str(content.title or ""),
        characteristics=[],
        description=str(content.description or ""),
        report={},
    )


def _validation_issues_from_payload(payload: Any) -> list[GenerationValidationIssue]:
    issues: list[GenerationValidationIssue] = []
    for item in _as_list(payload):
        if not isinstance(item, Mapping):
            continue
        try:
            issues.append(GenerationValidationIssue.model_validate(item))
        except Exception:
            continue
    return issues


def recalculate_latest_seo_relevance_v2(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoRelevanceV2Report:
    content = session.scalars(
        select(SeoContentVersion)
        .where(
            SeoContentVersion.project_id == int(project_id),
            SeoContentVersion.category_id == int(category_id),
            SeoContentVersion.nm_id == int(nm_id),
            # Iteration 2 (WS-D): accept both the legacy ``llm_draft`` label
            # and the new ``preview`` label so existing rows keep working
            # after migration.
            SeoContentVersion.content_kind.in_(("llm_draft", "preview")),
        )
        .order_by(desc(SeoContentVersion.updated_at), desc(SeoContentVersion.id))
    ).first()
    if content is None:
        raise SeoGenerationError("No saved preview content found for SEO relevance V2 recalculation")
    run = session.scalars(
        select(SeoGenerationRun)
        .where(SeoGenerationRun.content_version_id == int(content.id))
        .order_by(desc(SeoGenerationRun.updated_at), desc(SeoGenerationRun.id))
    ).first()
    score_breakdown = dict(content.score_breakdown or {})
    card = _generated_card_from_latest(content, run)
    brief = {"query_set": dict(content.query_snapshot or {})}
    issues = _validation_issues_from_payload(score_breakdown.get("validation"))
    report = build_seo_relevance_v2_report(card, brief, issues)
    score_breakdown["seo_relevance_v2"] = report.model_dump(mode="json")
    content.score_breakdown = score_breakdown
    if run is not None:
        response_payload = dict(run.response_payload or {})
        response_payload["seo_relevance_v2"] = report.model_dump(mode="json")
        run.response_payload = response_payload
    session.flush()
    return report


def get_latest_generation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoGenerationLatestResponse:
    content = session.scalars(
        select(SeoContentVersion)
        .where(
            SeoContentVersion.project_id == int(project_id),
            SeoContentVersion.category_id == int(category_id),
            SeoContentVersion.nm_id == int(nm_id),
            # Iteration 2 (WS-D): surface both legacy ``llm_draft`` and new
            # ``preview`` so the operator page keeps rendering through the
            # migration window.
            SeoContentVersion.content_kind.in_(("llm_draft", "preview")),
        )
        .order_by(desc(SeoContentVersion.updated_at), desc(SeoContentVersion.id))
    ).first()
    run = session.scalars(
        select(SeoGenerationRun)
        .where(SeoGenerationRun.content_version_id == int(content.id))
        .order_by(desc(SeoGenerationRun.updated_at), desc(SeoGenerationRun.id))
    ).first() if content is not None else None
    score_breakdown = dict(content.score_breakdown or {}) if content is not None else {}
    response_payload = dict(run.response_payload or {}) if run is not None else {}
    # Accept both new (internal_lint_*) and legacy (seo_relevance*) keys.
    seo_relevance_payload = (
        score_breakdown.get("internal_lint_seo_relevance")
        or score_breakdown.get("seo_relevance")
        or response_payload.get("internal_lint_seo_relevance")
        or response_payload.get("seo_relevance")
    )
    seo_relevance_v2_payload = (
        score_breakdown.get("internal_lint_seo_relevance_v2")
        or score_breakdown.get("seo_relevance_v2")
        or response_payload.get("internal_lint_seo_relevance_v2")
        or response_payload.get("seo_relevance_v2")
    )
    return SeoGenerationLatestResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        content_version_id=int(content.id) if content is not None else None,
        generation_run_id=int(run.id) if run is not None else None,
        status=content.status if content is not None else (run.status if run is not None else None),
        title=content.title if content is not None else None,
        description=content.description if content is not None else None,
        query_snapshot=dict(content.query_snapshot or {}) if content is not None else {},
        score_breakdown=score_breakdown,
        response_payload=response_payload,
        seo_relevance=SeoRelevanceReport.model_validate(seo_relevance_payload) if isinstance(seo_relevance_payload, Mapping) else None,
        seo_relevance_v2=SeoRelevanceV2Report.model_validate(seo_relevance_v2_payload) if isinstance(seo_relevance_v2_payload, Mapping) else None,
        error_text=run.error_text if run is not None else None,
        quality_mode=getattr(content, "quality_mode", None) if content is not None else None,
        degraded_reasons=list(getattr(content, "degraded_reasons", None) or []) if content is not None else [],
        mode_used=getattr(content, "mode_used", None) if content is not None else None,
        publishable=bool(getattr(content, "publishable", False)) if content is not None else False,
        matcher_run_id=getattr(content, "matcher_run_id", None) if content is not None else None,
    )
