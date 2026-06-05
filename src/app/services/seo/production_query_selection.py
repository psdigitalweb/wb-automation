"""Production-targeted SKU query selection preview and LLM run service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMeaningAxes,
    SeoGenerationRun,
    SeoMeaningAtom,
    SeoQueryCluster,
    SeoSkuMeaningAnnotation,
)
from app.schemas.seo_products import (
    SeoProductionCandidate,
    SeoProductionCandidatesBlock,
    SeoProductionCategoryBlock,
    SeoProductionMeaningLine,
    SeoProductionOperatorCandidate,
    SeoProductionProductBlock,
    SeoProductionQuerySelectionPreviewResponse,
    SeoProductionQuerySelectionRunResponse,
    SeoProductionReadinessBlock,
    SeoProductionSelectedQuery,
)
from app.services.seo.products import _count_category_queries, _latest_annotation, _latest_vision_row, _vision_verdict_from_row
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.query_meaning_matcher.canonical import stable_hash
from app.services.seo.query_pipeline.normalization import normalize_query_text


PRODUCTION_QUERY_SELECTION_MODEL = "openai/gpt-4o"
PRODUCTION_QUERY_SELECTION_PROMPT_VERSION = "query_selection_id_only_prompt_v1"
QUERY_SELECTION_PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[4] / "config" / "seo" / "prompts" / "QUERY_SELECTION_ID_ONLY_PROMPT_V1.txt"
AGREED_CANDIDATE_LIMIT = 2200
LLM_CANDIDATE_LIMIT = AGREED_CANDIDATE_LIMIT
LLM_BATCH_SIZE = 200
MAX_CLUSTER_REPRESENTATIVES = 2300
FALLBACK_CLUSTER_DISPLAY_LIMIT = 240
REPRESENTATIVE_FREQUENCY_THRESHOLD = 500
SIGNATURE_STOPWORDS = frozenset(
    {
        "для",
        "с",
        "со",
        "и",
        "на",
        "в",
        "во",
        "под",
        "к",
        "ко",
        "из",
        "от",
        "до",
        "у",
        "без",
        "по",
    }
)
DEFAULT_PREVIEW_LIMIT = FALLBACK_CLUSTER_DISPLAY_LIMIT
SEO_CHARACTERISTIC_NOISE_MARKERS = (
    "certificate",
    "certification",
    "declaration",
    "vat",
    "сертифик",
    "декларац",
    "ндс",
)


class ProductionQuerySelectionError(RuntimeError):
    """Raised when production query selection cannot safely run."""


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _product_block(session: Session, *, project_id: int, nm_id: int) -> SeoProductionProductBlock:
    row = session.execute(
        text(
            """
            SELECT nm_id, subject_name, title, description, dimensions, characteristics
            FROM products
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"project_id": int(project_id), "nm_id": int(nm_id)},
    ).mappings().first()
    if row is None:
        return SeoProductionProductBlock(nm_id=int(nm_id))
    characteristics = row.get("characteristics") or []
    if isinstance(characteristics, str):
        try:
            characteristics = json.loads(characteristics)
        except json.JSONDecodeError:
            characteristics = []
    if isinstance(characteristics, Mapping):
        characteristics = [{"name": str(key), "value": _json_safe(value)} for key, value in characteristics.items()]
    if not isinstance(characteristics, list):
        characteristics = []
    safe_characteristics = [
        item
        for item in characteristics
        if isinstance(item, Mapping) and not _is_noise_characteristic(item)
    ][:20]
    dimensions = row.get("dimensions") or {}
    if isinstance(dimensions, str):
        try:
            dimensions = json.loads(dimensions)
        except json.JSONDecodeError:
            dimensions = {}
    if not isinstance(dimensions, Mapping):
        dimensions = {}
    return SeoProductionProductBlock(
        nm_id=int(row["nm_id"]),
        title=row.get("title"),
        description=row.get("description"),
        product_type=row.get("subject_name"),
        dimensions={str(key): _json_safe(value) for key, value in dict(dimensions).items()},
        characteristics=[dict(item) for item in safe_characteristics],
    )


def _is_noise_characteristic(item: Mapping[str, Any]) -> bool:
    name = normalize_query_text(str(item.get("name") or item.get("key") or ""))
    if any(marker in name for marker in SEO_CHARACTERISTIC_NOISE_MARKERS):
        return True
    return False


def _latest_axes_payload(session: Session, *, project_id: int, category_id: int) -> dict[str, Any]:
    row = session.scalars(
        select(SeoCategoryMeaningAxes)
        .where(
            SeoCategoryMeaningAxes.project_id == int(project_id),
            SeoCategoryMeaningAxes.category_id == int(category_id),
            SeoCategoryMeaningAxes.status == "ready",
        )
        .order_by(desc(SeoCategoryMeaningAxes.updated_at), desc(SeoCategoryMeaningAxes.id))
    ).first()
    if row is None or not isinstance(row.axes_payload, Mapping):
        return {}
    payload = dict(row.axes_payload)
    preferred_keys = (
        "expressive_axes",
        "vibe_axes",
        "style_axes",
        "audience_axes",
        "occasion_axes",
        "use_case_axes",
        "product_type_axes",
    )
    result = {key: payload.get(key) for key in preferred_keys if key in payload}
    return result or payload


def _meaning_line(cluster: SeoQueryCluster) -> str | None:
    if cluster.label:
        return str(cluster.label)
    meta = cluster.meta if isinstance(cluster.meta, Mapping) else {}
    for key in ("meaning_line", "canonical_meaning", "label", "title"):
        value = meta.get(key)
        if value:
            return str(value)
    return cluster.cluster_key


def _canonical_signature(query: str) -> str:
    normalized = normalize_query_text(query)
    tokens = [token for token in normalized.split() if token and token not in SIGNATURE_STOPWORDS]
    return " ".join(sorted(tokens)) or normalized


def _candidate_key(query: str) -> str:
    return normalize_query_text(query)


def _evidence_strings(product: SeoProductionProductBlock, ai_vision: Any) -> list[str]:
    values: list[str] = []
    for value in (product.title, product.description):
        if value:
            values.append(str(value))
    for item in product.characteristics:
        if not isinstance(item, Mapping):
            continue
        for key in ("name", "value"):
            value = item.get(key)
            if isinstance(value, (str, int, float)):
                values.append(str(value))
    for item in getattr(ai_vision, "items", []) or []:
        if item:
            values.append(str(item))
    return values


def _evidence_tokens(product: SeoProductionProductBlock, ai_vision: Any) -> set[str]:
    tokens: set[str] = set()
    for value in _evidence_strings(product, ai_vision):
        normalized = normalize_query_text(value)
        for token in normalized.split():
            if len(token) >= 4 and token not in SIGNATURE_STOPWORDS:
                tokens.add(token)
    return tokens


def _score_candidate_for_sku(
    candidate: SeoProductionCandidate,
    *,
    evidence_tokens: set[str],
) -> float:
    query_tokens = [token for token in normalize_query_text(candidate.query).split() if token not in SIGNATURE_STOPWORDS]
    if not query_tokens:
        return 0.0
    score = 0.0
    for query_token in query_tokens:
        for evidence_token in evidence_tokens:
            if query_token == evidence_token:
                score += 4.0
            elif len(query_token) >= 5 and len(evidence_token) >= 5 and (
                query_token.startswith(evidence_token[:5]) or evidence_token.startswith(query_token[:5])
            ):
                score += 2.0
    if len(query_tokens) >= 3 and score > 0:
        score += 1.0
    if candidate.ranking_value:
        score += min(float(candidate.ranking_value), 100000.0) / 1000000.0
    return round(score, 6)


def _prioritize_candidates_for_sku(
    candidates: Sequence[SeoProductionCandidate],
    *,
    product: SeoProductionProductBlock,
    ai_vision: Any,
) -> list[SeoProductionCandidate]:
    evidence_tokens = _evidence_tokens(product, ai_vision)
    scored: list[SeoProductionCandidate] = []
    for candidate in candidates:
        candidate.sku_relevance_score = _score_candidate_for_sku(candidate, evidence_tokens=evidence_tokens)
        scored.append(candidate)
    return sorted(
        scored,
        key=lambda item: (
            -(item.sku_relevance_score or 0.0),
            -(item.ranking_value or 0.0),
            normalize_query_text(item.query),
            item.cluster_id or 0,
        ),
    )


def _cluster_representatives(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int,
) -> tuple[int, list[SeoProductionCandidate]]:
    cluster_total = int(
        session.scalar(
            select(func.count()).select_from(SeoQueryCluster).where(
                SeoQueryCluster.project_id == int(project_id),
                SeoQueryCluster.category_id == int(category_id),
                SeoQueryCluster.is_noise.is_not(True),
            )
        )
        or 0
    )
    if cluster_total <= 0:
        return 0, []

    max_candidates = max(1, min(int(limit), MAX_CLUSTER_REPRESENTATIVES))
    rows = session.execute(
        text(
            """
            WITH ranked AS (
                SELECT
                    c.id AS cluster_id,
                    c.cluster_key AS cluster_key,
                    c.label AS label,
                    c.top_query_text AS top_query_text,
                    m.normalized_query_text AS normalized_query_text,
                    m.ranking_value_used AS ranking_value_used,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.id
                        ORDER BY m.ranking_value_used DESC, m.normalized_query_text ASC, m.id ASC
                    ) AS representative_rank
                FROM seo_query_clusters c
                JOIN seo_query_cluster_memberships m
                  ON m.project_id = c.project_id
                 AND m.category_id = c.category_id
                 AND m.cluster_id = c.id
                WHERE c.project_id = :project_id
                  AND c.category_id = :category_id
                  AND c.is_noise IS NOT TRUE
                  AND m.ranking_value_used > :frequency_threshold
            )
            SELECT *
            FROM ranked
            WHERE representative_rank = 1
            ORDER BY ranking_value_used DESC, normalized_query_text ASC, cluster_id ASC
            """
        ),
        {
            "project_id": int(project_id),
            "category_id": int(category_id),
            "frequency_threshold": int(REPRESENTATIVE_FREQUENCY_THRESHOLD),
        },
    ).mappings().all()
    items: list[SeoProductionCandidate] = []
    by_signature: dict[str, SeoProductionCandidate] = {}
    for row in rows:
        query_text = str(row.get("normalized_query_text") or row.get("top_query_text") or "").strip()
        if not query_text:
            continue
        dedupe_key = _canonical_signature(query_text)
        if not dedupe_key:
            continue
        ranking_value_raw = row.get("ranking_value_used")
        ranking_value = float(ranking_value_raw or 0)
        candidate = SeoProductionCandidate(
            cluster_id=int(row["cluster_id"]),
            cluster_key=str(row["cluster_key"]),
            query=query_text,
            frequency=ranking_value,
            ranking_value=ranking_value,
            meaning_line=str(row.get("label") or row.get("top_query_text") or row.get("cluster_key")),
        )
        existing = by_signature.get(dedupe_key)
        if existing is None or float(existing.ranking_value or 0) < ranking_value:
            by_signature[dedupe_key] = candidate

    items = sorted(
        by_signature.values(),
        key=lambda item: (-(item.ranking_value or 0), normalize_query_text(item.query), item.cluster_id or 0),
    )[:max_candidates]
    if items:
        return len(items), items

    fallback_rows = session.execute(
        text(
            """
            WITH ranked AS (
                SELECT
                    c.id AS cluster_id,
                    c.cluster_key AS cluster_key,
                    c.label AS label,
                    c.top_query_text AS top_query_text,
                    m.normalized_query_text AS normalized_query_text,
                    m.ranking_value_used AS ranking_value_used,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.id
                        ORDER BY m.ranking_value_used DESC, m.normalized_query_text ASC, m.id ASC
                    ) AS representative_rank
                FROM seo_query_clusters c
                JOIN seo_query_cluster_memberships m
                  ON m.project_id = c.project_id
                 AND m.category_id = c.category_id
                 AND m.cluster_id = c.id
                WHERE c.project_id = :project_id
                  AND c.category_id = :category_id
                  AND c.is_noise IS NOT TRUE
            )
            SELECT *
            FROM ranked
            WHERE representative_rank = 1
            ORDER BY ranking_value_used DESC, normalized_query_text ASC, cluster_id ASC
            LIMIT :fallback_limit
            """
        ),
        {
            "project_id": int(project_id),
            "category_id": int(category_id),
            "fallback_limit": int(FALLBACK_CLUSTER_DISPLAY_LIMIT),
        },
    ).mappings().all()
    for row in fallback_rows:
        query_text = str(row.get("normalized_query_text") or row.get("top_query_text") or "").strip()
        if not query_text:
            continue
        ranking_value_raw = row.get("ranking_value_used")
        ranking_value = float(ranking_value_raw or 0)
        items.append(
            SeoProductionCandidate(
                cluster_id=int(row["cluster_id"]),
                cluster_key=str(row["cluster_key"]),
                query=query_text,
                frequency=ranking_value,
                ranking_value=ranking_value,
                meaning_line=str(row.get("label") or row.get("top_query_text") or row.get("cluster_key")),
            )
        )
    if items:
        return len(items), items

    clusters = session.scalars(
        select(SeoQueryCluster)
        .where(
            SeoQueryCluster.project_id == int(project_id),
            SeoQueryCluster.category_id == int(category_id),
            SeoQueryCluster.is_noise.is_not(True),
        )
        .order_by(SeoQueryCluster.id.asc())
        .limit(FALLBACK_CLUSTER_DISPLAY_LIMIT)
    ).all()
    for cluster in clusters:
        query_text = str(cluster.top_query_text or cluster.cluster_key).strip()
        if not query_text:
            continue
        items.append(
            SeoProductionCandidate(
                cluster_id=int(cluster.id),
                cluster_key=str(cluster.cluster_key),
                query=query_text,
                frequency=None,
                ranking_value=None,
                meaning_line=_meaning_line(cluster),
            )
        )
    return len(items), items


def build_production_query_selection_preview(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int,
    preview_limit: int = DEFAULT_PREVIEW_LIMIT,
) -> SeoProductionQuerySelectionPreviewResponse:
    """Build the exact read-only input snapshot used by production selection."""
    product = _product_block(session, project_id=project_id, nm_id=nm_id)
    query_count, normalized_count, cluster_count, expressive_ready, latest_batch_ready = _count_category_queries(
        session,
        project_id=project_id,
        category_id=category_id,
    )
    del normalized_count
    axes = _latest_axes_payload(session, project_id=project_id, category_id=category_id)
    annotation = _latest_annotation(session, project_id=project_id, nm_id=nm_id, category_id=category_id)
    vision_row = _latest_vision_row(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        annotation=annotation,
    )
    ai_vision = _vision_verdict_from_row(vision_row)
    candidate_count, all_candidates = _cluster_representatives(
        session,
        project_id=project_id,
        category_id=category_id,
        limit=AGREED_CANDIDATE_LIMIT,
    )
    display_candidates = all_candidates[: max(1, int(preview_limit))]
    blocking_reasons: list[str] = []
    if not product.title:
        blocking_reasons.append("Карточка товара не найдена или не содержит title.")
    if not latest_batch_ready or query_count <= 0:
        blocking_reasons.append("Для категории нет готового query corpus.")
    if cluster_count <= 0 or candidate_count <= 0:
        blocking_reasons.append("Для категории нет построенных кластеров.")
    if not expressive_ready:
        blocking_reasons.append("Для категории не готов expressive prior.")
    if not ai_vision.ready:
        blocking_reasons.append("AI vision по товару не выполнен или не готов.")
    category_block = SeoProductionCategoryBlock(
        category_id=int(category_id),
        query_count=int(query_count),
        cluster_count=int(cluster_count),
        expressive_prior_axes=axes,
    )
    prompt_input = _input_payload_from_parts(
        product=product,
        category=category_block,
        ai_vision=ai_vision,
        candidates=all_candidates,
        total_candidate_count=int(candidate_count),
    )
    input_prompt = render_query_selection_prompt(prompt_input)
    return SeoProductionQuerySelectionPreviewResponse(
        project_id=int(project_id),
        nm_id=int(nm_id),
        category_id=int(category_id),
        product=product,
        category=category_block,
        ai_vision=ai_vision,
        candidates=SeoProductionCandidatesBlock(
            candidate_count=int(candidate_count),
            total_candidate_count=int(candidate_count),
            display_candidate_count=len(display_candidates),
            sent_candidate_count=len(all_candidates),
            preview_limit=int(preview_limit),
            items=display_candidates,
        ),
        readiness=SeoProductionReadinessBlock(can_run=not blocking_reasons, blocking_reasons=blocking_reasons),
        prompt_version=PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
        input_prompt=input_prompt,
    )


def _system_prompt() -> str:
    return (
        "Ты выбираешь поисковые запросы Wildberries для одного конкретного товара. "
        "Цель - смысловая релевантность конкретному товару, а не популярность категории. "
        "Верни только строгий JSON-объект ровно с ключом lines. "
        "Каждый item lines содержит line, selected и operator_candidates. "
        "selected/operator_candidates - только массивы числовых id без повторов. "
        "Не возвращай тексты запросов, причины, confidence или markdown."
    )


def _read_query_prompt_template() -> str:
    return QUERY_SELECTION_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _format_query_candidates_table(candidates: Sequence[Mapping[str, Any]]) -> str:
    rows = ["id | запрос | частотность"]
    for item in candidates:
        cluster_id = item.get("cluster_id")
        query = str(item.get("query") or "").strip()
        if cluster_id is None or not query:
            continue
        frequency = item.get("frequency")
        if isinstance(frequency, float) and frequency.is_integer():
            frequency_text = str(int(frequency))
        else:
            frequency_text = "" if frequency is None else str(frequency)
        rows.append(f"{int(cluster_id)} | {query} | {frequency_text}")
    return "\n".join(rows)


def _style_hint(category: SeoProductionCategoryBlock, *, product_type: str) -> str:
    axes = category.expressive_prior_axes if isinstance(category.expressive_prior_axes, Mapping) else {}
    expressive = axes.get("expressive_axes")
    values = [str(value).strip() for value in expressive if str(value).strip()] if isinstance(expressive, Sequence) and not isinstance(expressive, (str, bytes)) else []
    if not values:
        return ""
    return f"{product_type} этого бренда обычно характеризуются как:\n{', '.join(values)}"


def _vision_line_items(ai_vision: Any) -> list[str]:
    if isinstance(ai_vision, Mapping):
        raw_items = ai_vision.get("items")
        return [str(item).strip() for item in raw_items or [] if str(item).strip()] if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes)) else []
    return [str(item).strip() for item in getattr(ai_vision, "items", []) or [] if str(item).strip()]


def _vision_evidence_block(ai_vision: Any) -> str:
    if isinstance(ai_vision, Mapping) and ai_vision.get("evidence_block"):
        return str(ai_vision["evidence_block"])
    evidence_block = getattr(ai_vision, "evidence_block", None)
    if evidence_block:
        return str(evidence_block)
    items = _vision_line_items(ai_vision)
    if not items:
        return "Фото товара подтверждает:\nНет сохраненных визуальных признаков."
    return (
        "Фото товара подтверждает:\n\n"
        "Визуально и текстом на изображении найдено:\n"
        + "\n".join(f"- {item}" for item in items[:18])
        + "\n\n"
        "Используй блок фото как дополнительное evidence к карточке товара.\n"
        "Не считай OCR-текст физическим свойством товара, если он не подтверждается карточкой."
    )


def render_query_selection_prompt(input_payload: Mapping[str, Any]) -> str:
    product = input_payload.get("product")
    category = input_payload.get("category")
    ai_vision = input_payload.get("ai_vision")
    query_candidates = input_payload.get("query_candidates")
    if not isinstance(product, SeoProductionProductBlock):
        product = SeoProductionProductBlock.model_validate(product if isinstance(product, Mapping) else {})
    if not isinstance(category, SeoProductionCategoryBlock):
        category_payload = dict(category) if isinstance(category, Mapping) else {}
        category = SeoProductionCategoryBlock(
            category_id=int(category_payload.get("category_id") or 0),
            expressive_prior_axes=dict(category_payload.get("expressive_prior_axes") or {}),
        )
    product_type = str(product.product_type or "товар").strip() or "товар"
    candidates = query_candidates if isinstance(query_candidates, Sequence) and not isinstance(query_candidates, (str, bytes)) else []
    replacements = {
        "product_type": product_type,
        "title": str(product.title or ""),
        "description": str(product.description or ""),
        "category_style_hint": _style_hint(category, product_type=product_type),
        "vision_evidence": _vision_evidence_block(ai_vision),
        "query_candidates_table": _format_query_candidates_table([dict(item) for item in candidates if isinstance(item, Mapping)]),
    }
    rendered = _read_query_prompt_template()
    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _user_prompt(input_payload: Mapping[str, Any]) -> str:
    return render_query_selection_prompt(input_payload)


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = str(content or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ProductionQuerySelectionError("LLM response JSON must be an object")
    return parsed


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_lookup(input_payload: Mapping[str, Any]) -> dict[str, SeoProductionCandidate]:
    lookup: dict[str, SeoProductionCandidate] = {}
    candidates = input_payload.get("query_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return lookup
    for item in candidates:
        if not isinstance(item, Mapping) or not item.get("query"):
            continue
        candidate = SeoProductionCandidate(**dict(item))
        lookup[_candidate_key(candidate.query)] = candidate
    return lookup


def _candidate_lookup_by_id(input_payload: Mapping[str, Any]) -> dict[int, SeoProductionCandidate]:
    lookup: dict[int, SeoProductionCandidate] = {}
    candidates = input_payload.get("query_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return lookup
    for item in candidates:
        if not isinstance(item, Mapping) or item.get("cluster_id") is None or not item.get("query"):
            continue
        candidate = SeoProductionCandidate(**dict(item))
        lookup[int(candidate.cluster_id)] = candidate
    return lookup


def _meaning_lines_from_payload(items: Any) -> list[SeoProductionMeaningLine]:
    result: list[SeoProductionMeaningLine] = []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return result
    for item in items:
        if not isinstance(item, Mapping):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        evidence_raw = item.get("evidence")
        evidence = [
            str(value)
            for value in evidence_raw
            if isinstance(value, (str, int, float)) and str(value).strip()
        ] if isinstance(evidence_raw, Sequence) and not isinstance(evidence_raw, (str, bytes)) else []
        coverage_status = str(item.get("coverage_status") or "weak")
        if coverage_status not in {"covered", "weak", "no_candidate"}:
            coverage_status = "weak"
        result.append(
            SeoProductionMeaningLine(
                line=line,
                evidence=evidence[:8],
                coverage_status=coverage_status,
            )
        )
    return result


def _meaning_lines_from_groups(parsed: Mapping[str, Any]) -> list[SeoProductionMeaningLine]:
    lines: list[SeoProductionMeaningLine] = []
    for group_key, line_name in (
        ("primary", "primary"),
        ("secondary", "secondary"),
        ("gift_style", "gift_style"),
    ):
        items = parsed.get(group_key)
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)) and items:
            lines.append(SeoProductionMeaningLine(line=line_name, evidence=[], coverage_status="covered"))
    return lines


def _selected_from_payload(
    items: Any,
    *,
    candidates_by_query: Mapping[str, SeoProductionCandidate],
) -> list[SeoProductionSelectedQuery]:
    result: list[SeoProductionSelectedQuery] = []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return result
    for item in items:
        if not isinstance(item, Mapping) or not item.get("query"):
            continue
        source_candidate = candidates_by_query.get(_candidate_key(str(item.get("query"))))
        if source_candidate is None:
            continue
        result.append(
            SeoProductionSelectedQuery(
                query=source_candidate.query,
                status=str(item.get("status") or "strong"),
                risk=str(item.get("risk")) if item.get("risk") is not None else None,
                explanation=str(item.get("reason") or item.get("explanation") or ""),
                cluster_id=source_candidate.cluster_id,
                meaning_line=str(item.get("meaning_line") or source_candidate.meaning_line or ""),
                frequency=source_candidate.frequency,
                confidence=_optional_float(item.get("confidence")),
            )
        )
    return result


def _selected_from_grouped_payload(
    parsed: Mapping[str, Any],
    *,
    candidates_by_query: Mapping[str, SeoProductionCandidate],
) -> list[SeoProductionSelectedQuery]:
    result: list[SeoProductionSelectedQuery] = []
    group_status = {
        "primary": "strong",
        "secondary": "plausible",
        "gift_style": "plausible",
    }
    for group_key in ("primary", "secondary", "gift_style"):
        items = parsed.get(group_key)
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            continue
        for item in items:
            if not isinstance(item, Mapping) or not item.get("query"):
                continue
            source_candidate = candidates_by_query.get(_candidate_key(str(item.get("query"))))
            if source_candidate is None:
                continue
            result.append(
                SeoProductionSelectedQuery(
                    query=source_candidate.query,
                    status=group_status[group_key],
                    risk=None,
                    explanation=str(item.get("reason") or item.get("explanation") or ""),
                    cluster_id=source_candidate.cluster_id,
                    meaning_line=group_key,
                    frequency=source_candidate.frequency,
                    confidence=_optional_float(item.get("confidence")),
                )
            )
    return result


def _selected_from_ids(
    ids: Any,
    *,
    candidates_by_id: Mapping[int, SeoProductionCandidate],
    status: str,
    meaning_line: str,
    limit: int = 50,
) -> list[SeoProductionSelectedQuery]:
    result: list[SeoProductionSelectedQuery] = []
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        return result
    seen: set[int] = set()
    for raw_id in ids:
        try:
            cluster_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if cluster_id in seen:
            continue
        seen.add(cluster_id)
        source_candidate = candidates_by_id.get(cluster_id)
        if source_candidate is None:
            continue
        result.append(
            SeoProductionSelectedQuery(
                query=source_candidate.query,
                status=status,
                risk=None,
                explanation="",
                cluster_id=source_candidate.cluster_id,
                meaning_line=meaning_line,
                frequency=source_candidate.frequency,
                confidence=None,
            )
        )
        if len(result) >= limit:
            break
    return result


def _operator_candidates_from_ids(
    ids: Any,
    *,
    candidates_by_id: Mapping[int, SeoProductionCandidate],
    limit: int = 20,
) -> dict[str, list[SeoProductionOperatorCandidate]]:
    items: list[SeoProductionOperatorCandidate] = []
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        return {}
    seen: set[int] = set()
    for raw_id in ids:
        try:
            cluster_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if cluster_id in seen:
            continue
        seen.add(cluster_id)
        source_candidate = candidates_by_id.get(cluster_id)
        if source_candidate is None:
            continue
        items.append(
            SeoProductionOperatorCandidate(
                meaning_line="operator_candidates",
                query=source_candidate.query,
                status="plausible",
                risk=None,
                explanation="",
                cluster_id=source_candidate.cluster_id,
                frequency=source_candidate.frequency,
                confidence=None,
            )
        )
        if len(items) >= limit:
            break
    return {"operator_candidates": items} if items else {}


def _selection_from_line_payload(
    lines: Any,
    *,
    candidates_by_id: Mapping[int, SeoProductionCandidate],
) -> tuple[list[SeoProductionMeaningLine], list[SeoProductionSelectedQuery], dict[str, list[SeoProductionOperatorCandidate]]]:
    meaning_lines: list[SeoProductionMeaningLine] = []
    selected: list[SeoProductionSelectedQuery] = []
    operators: dict[str, list[SeoProductionOperatorCandidate]] = {}
    if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)):
        return meaning_lines, selected, operators

    selected_seen: set[int] = set()
    operator_seen: set[int] = set()
    for item in lines:
        if not isinstance(item, Mapping):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        line_selected = _selected_from_ids(
            item.get("selected"),
            candidates_by_id=candidates_by_id,
            status="strong",
            meaning_line=line,
            limit=10,
        )
        line_operators = _operator_candidates_from_ids(
            item.get("operator_candidates"),
            candidates_by_id=candidates_by_id,
            limit=10,
        ).get("operator_candidates", [])
        filtered_selected: list[SeoProductionSelectedQuery] = []
        for candidate in line_selected:
            if candidate.cluster_id is None or candidate.cluster_id in selected_seen:
                continue
            selected_seen.add(candidate.cluster_id)
            filtered_selected.append(candidate)
            selected.append(candidate)
            if len(selected) >= 50:
                break
        filtered_operators: list[SeoProductionOperatorCandidate] = []
        for candidate in line_operators:
            if candidate.cluster_id is None or candidate.cluster_id in selected_seen or candidate.cluster_id in operator_seen:
                continue
            operator_seen.add(candidate.cluster_id)
            candidate.meaning_line = line
            filtered_operators.append(candidate)
            if sum(len(group) for group in operators.values()) + len(filtered_operators) >= 20:
                break
        if filtered_operators:
            operators[line] = filtered_operators
        if filtered_selected or filtered_operators:
            meaning_lines.append(
                SeoProductionMeaningLine(
                    line=line,
                    evidence=[],
                    coverage_status="covered" if filtered_selected else "weak",
                )
            )
        if len(selected) >= 50 and sum(len(group) for group in operators.values()) >= 20:
            break
    return meaning_lines, selected, operators


def _operators_from_payload(
    items: Any,
    *,
    candidates_by_query: Mapping[str, SeoProductionCandidate],
) -> dict[str, list[SeoProductionOperatorCandidate]]:
    grouped: dict[str, list[SeoProductionOperatorCandidate]] = {}
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return grouped
    for item in items:
        if not isinstance(item, Mapping) or not item.get("query"):
            continue
        source_candidate = candidates_by_query.get(_candidate_key(str(item.get("query"))))
        if source_candidate is None:
            continue
        meaning_line = str(item.get("meaning_line") or source_candidate.meaning_line or "other")
        if len(grouped.get(meaning_line, [])) >= 10:
            continue
        candidate = SeoProductionOperatorCandidate(
            meaning_line=meaning_line,
            query=source_candidate.query,
            status=str(item.get("status") or "plausible"),
            risk=str(item.get("risk")) if item.get("risk") is not None else None,
            explanation=str(item.get("reason") or item.get("explanation") or ""),
            cluster_id=source_candidate.cluster_id,
            frequency=source_candidate.frequency,
            confidence=_optional_float(item.get("confidence")),
        )
        grouped.setdefault(meaning_line, []).append(candidate)
    return grouped


def _input_payload_from_parts(
    *,
    product: SeoProductionProductBlock,
    category: SeoProductionCategoryBlock,
    ai_vision: Any,
    candidates: Sequence[SeoProductionCandidate],
    total_candidate_count: int,
) -> dict[str, Any]:
    sent_candidate_count = len(candidates)
    query_candidates = [
        {
            "cluster_id": item.cluster_id,
            "query": item.query,
            "frequency": item.frequency,
        }
        for item in candidates
    ]
    return {
        "product": {
            "nm_id": product.nm_id,
            "product_type": product.product_type,
            "title": product.title,
            "description": product.description,
        },
        "category": {
            "expressive_prior_axes": category.expressive_prior_axes,
        },
        "ai_vision": ai_vision.model_dump(mode="json") if hasattr(ai_vision, "model_dump") else ai_vision,
        "query_candidates": query_candidates,
        "candidate_count_total": total_candidate_count,
        "candidate_count_sent": sent_candidate_count,
    }


def _input_payload(preview: SeoProductionQuerySelectionPreviewResponse) -> dict[str, Any]:
    return _input_payload_from_parts(
        product=preview.product,
        category=preview.category,
        ai_vision=preview.ai_vision,
        candidates=preview.candidates.items,
        total_candidate_count=preview.candidates.total_candidate_count or preview.candidates.candidate_count,
    )


def _candidate_batches(candidates: Sequence[SeoProductionCandidate], *, batch_size: int = LLM_BATCH_SIZE) -> list[list[SeoProductionCandidate]]:
    size = max(1, int(batch_size))
    return [list(candidates[index : index + size]) for index in range(0, len(candidates), size)]


def _selection_from_parsed(
    parsed: Mapping[str, Any],
    *,
    input_payload: Mapping[str, Any],
) -> tuple[list[SeoProductionMeaningLine], list[SeoProductionSelectedQuery], dict[str, list[SeoProductionOperatorCandidate]]]:
    candidates_by_query = _candidate_lookup(input_payload)
    candidates_by_id = _candidate_lookup_by_id(input_payload)
    meaning_lines = _meaning_lines_from_payload(parsed.get("meaning_lines"))
    selected = _selected_from_payload(parsed.get("selected_queries"), candidates_by_query=candidates_by_query)
    operators = _operators_from_payload(parsed.get("operator_candidates"), candidates_by_query=candidates_by_query)
    if not selected and "lines" in parsed:
        meaning_lines, selected, operators = _selection_from_line_payload(
            parsed.get("lines"),
            candidates_by_id=candidates_by_id,
        )
    if not selected and "selected" in parsed:
        selected = _selected_from_ids(
            parsed.get("selected"),
            candidates_by_id=candidates_by_id,
            status="strong",
            meaning_line="selected",
        )
        operators = _operator_candidates_from_ids(parsed.get("operator_candidates"), candidates_by_id=candidates_by_id)
        if selected:
            meaning_lines = [SeoProductionMeaningLine(line="selected", evidence=[], coverage_status="covered")]
        if operators:
            meaning_lines.append(SeoProductionMeaningLine(line="operator_candidates", evidence=[], coverage_status="weak"))
    if not selected and any(key in parsed for key in ("primary", "secondary", "gift_style")):
        meaning_lines = meaning_lines or _meaning_lines_from_groups(parsed)
        selected = _selected_from_grouped_payload(parsed, candidates_by_query=candidates_by_query)
    return meaning_lines, selected, operators


def _merge_meaning_lines(
    target: list[SeoProductionMeaningLine],
    items: Sequence[SeoProductionMeaningLine],
    *,
    seen: set[str],
) -> None:
    for item in items:
        key = normalize_query_text(item.line)
        if not key or key in seen:
            continue
        seen.add(key)
        target.append(item)


def _merge_selected_queries(
    target: list[SeoProductionSelectedQuery],
    items: Sequence[SeoProductionSelectedQuery],
    *,
    seen: set[int],
) -> None:
    for item in items:
        if item.cluster_id is None or int(item.cluster_id) in seen:
            continue
        seen.add(int(item.cluster_id))
        target.append(item)


def _merge_operator_candidates(
    target: dict[str, list[SeoProductionOperatorCandidate]],
    items: Mapping[str, Sequence[SeoProductionOperatorCandidate]],
    *,
    selected_seen: set[int],
    operator_seen: set[int],
) -> None:
    for line, candidates in items.items():
        for item in candidates:
            if item.cluster_id is None:
                continue
            cluster_id = int(item.cluster_id)
            if cluster_id in selected_seen or cluster_id in operator_seen:
                continue
            operator_seen.add(cluster_id)
            target.setdefault(line, []).append(item)


def run_production_query_selection(
    session: Session,
    *,
    project_id: int,
    nm_id: int,
    category_id: int,
    provider: ChatProvider | None = None,
) -> SeoProductionQuerySelectionRunResponse:
    """Run LLM query selection and persist request/response in an existing run table."""
    preview = build_production_query_selection_preview(
        session,
        project_id=project_id,
        nm_id=nm_id,
        category_id=category_id,
        preview_limit=LLM_CANDIDATE_LIMIT,
    )
    preview.candidates.sent_candidate_count = len(preview.candidates.items)
    if not preview.readiness.can_run:
        raise ProductionQuerySelectionError("; ".join(preview.readiness.blocking_reasons))
    input_payload = _input_payload(preview)
    preview_messages = [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(role="user", content=_user_prompt(input_payload)),
    ]
    run = SeoGenerationRun(
        project_id=int(project_id),
        category_id=int(category_id),
        provider_name="query_selection",
        model_name=getattr(provider, "chat_model", None) or PRODUCTION_QUERY_SELECTION_MODEL,
        status="running",
        request_payload={
            "kind": "production_query_selection",
            "nm_id": int(nm_id),
            "prompt_version": PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
            "input": input_payload,
            "batch_size": LLM_BATCH_SIZE,
            "batch_count": len(_candidate_batches(preview.candidates.items)),
            "messages": [message.__dict__ for message in preview_messages],
        },
        response_payload={},
    )
    session.add(run)
    session.flush()
    artifact_root = (
        Path("artifacts")
        / "seo"
        / "query_selection"
        / f"p{int(project_id)}"
        / f"c{int(category_id)}"
        / f"nm{int(nm_id)}"
        / f"run_{int(run.id)}"
    )
    try:
        resolved_provider = provider or OpenRouterProvider(
            chat_model=PRODUCTION_QUERY_SELECTION_MODEL,
            timeout_seconds=180.0,
            response_format={"type": "json_object"},
        )
        meaning_lines: list[SeoProductionMeaningLine] = []
        selected: list[SeoProductionSelectedQuery] = []
        operators: dict[str, list[SeoProductionOperatorCandidate]] = {}
        meaning_line_seen: set[str] = set()
        selected_seen: set[int] = set()
        operator_seen: set[int] = set()
        batch_payloads: list[dict[str, Any]] = []
        response_model = getattr(resolved_provider, "chat_model", None) or PRODUCTION_QUERY_SELECTION_MODEL
        all_raw_grouped_selection: list[dict[str, Any]] = []
        all_parsed: list[dict[str, Any]] = []
        for batch_index, candidate_batch in enumerate(_candidate_batches(preview.candidates.items), start=1):
            batch_input_payload = _input_payload_from_parts(
                product=preview.product,
                category=preview.category,
                ai_vision=preview.ai_vision,
                candidates=candidate_batch,
                total_candidate_count=preview.candidates.total_candidate_count or preview.candidates.candidate_count,
            )
            messages = [
                ChatMessage(role="system", content=_system_prompt()),
                ChatMessage(role="user", content=_user_prompt(batch_input_payload)),
            ]
            response = resolved_provider.generate_chat(messages, temperature=0.1, top_p=0.9, max_tokens=1200)
            response_model = response.model
            parsed = _parse_json_object(response.content)
            raw_grouped_selection = {
                key: parsed.get(key)
                for key in ("lines", "primary", "secondary", "gift_style", "reject", "selected", "operator_candidates")
                if key in parsed
            }
            parsed.pop("rejected", None)
            parsed.pop("reject", None)
            batch_meaning_lines, batch_selected, batch_operators = _selection_from_parsed(
                parsed,
                input_payload=batch_input_payload,
            )
            _merge_meaning_lines(meaning_lines, batch_meaning_lines, seen=meaning_line_seen)
            _merge_selected_queries(selected, batch_selected, seen=selected_seen)
            _merge_operator_candidates(
                operators,
                batch_operators,
                selected_seen=selected_seen,
                operator_seen=operator_seen,
            )
            raw_response_payload = dict(response.raw_response or {}) or {"model": response.model, "content": response.content}
            batch_payload = {
                "batch_index": batch_index,
                "candidate_count_sent": len(candidate_batch),
                "input": batch_input_payload,
                "messages": [{"role": messages[0].role, "content": messages[0].content}],
                "model": response.model,
                "raw_response": raw_response_payload,
                "parsed": parsed,
                "raw_grouped_selection": raw_grouped_selection,
                "meaning_lines": [item.model_dump(mode="json") for item in batch_meaning_lines],
                "selected_queries": [item.model_dump(mode="json") for item in batch_selected],
                "operator_candidates": {
                    key: [item.model_dump(mode="json") for item in value]
                    for key, value in batch_operators.items()
                },
            }
            batch_payloads.append(batch_payload)
            all_raw_grouped_selection.append(raw_grouped_selection)
            all_parsed.append(parsed)
        artifact_payload = {
            "run_id": int(run.id),
            "input": input_payload,
            "messages": [message.__dict__ for message in preview_messages],
            "model": response_model,
            "prompt_version": PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
            "batch_size": LLM_BATCH_SIZE,
            "batch_count": len(batch_payloads),
            "batches": batch_payloads,
            "parsed": all_parsed,
            "raw_grouped_selection": all_raw_grouped_selection,
        }
        _write_json(artifact_root / "artifact.json", artifact_payload)
        run.status = "completed"
        run.model_name = response_model
        run.response_payload = {
            "artifact_path": str(artifact_root / "artifact.json"),
            "input_hash": stable_hash(input_payload),
            "prompt_version": PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
            "batch_size": LLM_BATCH_SIZE,
            "batch_count": len(batch_payloads),
            "candidate_count_total": input_payload["candidate_count_total"],
            "candidate_count_sent": input_payload["candidate_count_sent"],
            "parsed": all_parsed,
            "raw_grouped_selection": all_raw_grouped_selection,
            "meaning_lines": [item.model_dump(mode="json") for item in meaning_lines],
            "selected_queries": [item.model_dump(mode="json") for item in selected],
            "operator_candidates": {
                key: [item.model_dump(mode="json") for item in value]
                for key, value in operators.items()
            },
        }
        session.flush()
        return SeoProductionQuerySelectionRunResponse(
            run_id=int(run.id),
            project_id=int(project_id),
            nm_id=int(nm_id),
            category_id=int(category_id),
            status="completed",
            meaning_lines=meaning_lines,
            selected_queries=selected,
            operator_candidates=operators,
            model=response_model,
            prompt_version=PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
            artifact_path=str(artifact_root / "artifact.json"),
            candidate_count=preview.candidates.total_candidate_count or preview.candidates.candidate_count,
            sent_candidate_count=len(preview.candidates.items),
            input_prompt=preview_messages[1].content,
        )
    except Exception as exc:
        run.status = "failed"
        run.error_text = f"{type(exc).__name__}: {exc}"
        run.response_payload = {
            "artifact_path": str(artifact_root / "artifact.json"),
            "prompt_version": PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
            "error": run.error_text,
        }
        session.flush()
        raise
