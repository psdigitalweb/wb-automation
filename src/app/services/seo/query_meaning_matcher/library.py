"""Query Meaning Library v0 build and read helpers."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import settings
from app.models import SeoCategoryMeaningAxes, SeoQueryCluster, SeoQueryClusterMembership, SeoQueryMeaning
from app.schemas.seo_query_meaning_matcher import (
    QUERY_MEANING_PROMPT_VERSION,
    QUERY_MEANING_SCHEMA_VERSION,
    QueryMeaningItem,
    QueryMeaningLibraryBuildResponse,
    QueryMeaningLibraryResponse,
    QueryMeaningPayload,
)
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.query_meaning_matcher.canonical import (
    build_query_canonical_text,
    listify,
    normalize_query_meaning_payload,
    stable_hash,
    stable_json,
    unique_strings,
)
from app.services.seo.query_pipeline import run_query_profile_extraction
from app.services.seo.visual_motifs import extract_visual_motifs


class QueryMeaningLibraryError(Exception):
    """Raised when query meaning library build cannot proceed."""


_MODEL_SAFE_RE = re.compile(r"[^0-9a-zA-Z_.-]+")
_QUANTITY_RE = re.compile(r"\b(\d+)\s*(?:шт|штук|предмет(?:а|ов)?|персон(?:ы)?)\b", re.IGNORECASE)
QUERY_MEANING_RULES_VERSION = "query_meaning_rules_v1_visual_motifs"


@dataclass(frozen=True)
class _ClusterInput:
    cluster_id: int
    cluster_key: str
    label: str
    top_query_text: str
    source_query_examples: list[str]
    query_count: int
    max_ranking_value: float
    deterministic_profile: dict[str, Any]
    category_axes_payload: dict[str, Any]
    category_axes_input_hash: str | None
    input_hash: str


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_model_dir(model: str) -> str:
    value = str(model or "").strip().replace("/", "__").replace(":", "_")
    return _MODEL_SAFE_RE.sub("_", value)[:64] or "unknown_model"


def _artifact_root() -> Path:
    override = os.getenv("SEO_QUERY_MEANING_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(settings.INTERNAL_DATA_DIR) / "seo_query_meaning_cache"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        raise QueryMeaningLibraryError("LLM returned empty content")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first >= 0 and last > first:
            candidate = candidate[first : last + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise QueryMeaningLibraryError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise QueryMeaningLibraryError("LLM query meaning response must be a JSON object")
    return payload


def _prompt_for_cluster(cluster_input: _ClusterInput) -> str:
    payload = {
        "schema_version": QUERY_MEANING_SCHEMA_VERSION,
        "cluster_key": cluster_input.cluster_key,
        "label": cluster_input.label,
        "top_query_text": cluster_input.top_query_text,
        "source_query_examples": cluster_input.source_query_examples,
        "query_count": cluster_input.query_count,
        "max_ranking_value": cluster_input.max_ranking_value,
        "deterministic_profile": cluster_input.deterministic_profile,
        "category_axes": cluster_input.category_axes_payload,
    }
    return (
        "Ты размечаешь смысл search query cluster для SEO matcher маркетплейса.\n"
        "Верни только валидный JSON без markdown. Размечай смысл кластера, не SKU.\n\n"
        "Schema query_meaning_v0:\n"
        "{\n"
        '  "functional": {"product_type": "кружка", "use_cases": [], "attributes": []},\n'
        '  "expressive": {"styles": [], "vibes": [], "emotions": [], "gift_contexts": []},\n'
        '  "audience": [],\n'
        '  "occasion": [],\n'
        '  "constraints": [],\n'
        '  "conflicts_if_missing": [],\n'
        '  "genericness": "specific|broad|generic",\n'
        '  "confidence": {"functional": 0.0, "expressive": 0.0, "constraints": 0.0}\n'
        "}\n\n"
        "Правила:\n"
        "- Частотность не делает смысл релевантным, она только описывает возможность.\n"
        "- Если запрос требует термосвойства, набора, количества, материала или особого формата, добавь constraints и conflicts_if_missing.\n"
        "- Общие запросы вроде 'кружка' должны иметь genericness=generic/broad.\n"
        "- 'милая/красивая/эстетичная/pinterest/в подарок/для подруги' должны попадать в expressive/audience/occasion.\n\n"
        "INPUT_JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )


def _texts_for_rules(cluster_input: _ClusterInput) -> str:
    return " ".join(
        [
            cluster_input.label,
            cluster_input.top_query_text,
            *cluster_input.source_query_examples,
        ]
    ).lower().replace("ё", "е")


def _primary_text_for_rules(cluster_input: _ClusterInput) -> str:
    return " ".join(
        [
            cluster_input.label,
            cluster_input.top_query_text,
            cluster_input.source_query_examples[0] if cluster_input.source_query_examples else "",
        ]
    ).lower().replace("ё", "е")


def _tokens_for_rules(text: str) -> set[str]:
    return set(re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ]+", str(text or "").lower().replace("ё", "е")))


def _has_cute_marker(tokens: set[str]) -> bool:
    exact = {"милая", "милый", "милые", "милую", "милого", "милота", "няшная", "няшный", "няшные"}
    return bool(tokens & exact) or any(token.startswith("милаш") for token in tokens)


def _has_prefix_marker(tokens: set[str], *prefixes: str) -> bool:
    return any(any(token.startswith(prefix) for prefix in prefixes) for token in tokens)


def _query_motif_markers(text: str) -> list[str]:
    return extract_visual_motifs(text)


def _append_unique(target: list[str], *values: str) -> None:
    known = {item.lower().replace("ё", "е") for item in target}
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower().replace("ё", "е")
        if key not in known:
            target.append(text)
            known.add(key)


def _enforce_deterministic_rules(payload: QueryMeaningPayload, cluster_input: _ClusterInput) -> QueryMeaningPayload:
    data = payload.model_dump(mode="json")
    functional = dict(data.get("functional") or {})
    expressive = dict(data.get("expressive") or {})
    constraints = list(data.get("constraints") or [])
    conflicts = list(data.get("conflicts_if_missing") or [])
    audience = list(data.get("audience") or [])
    occasion = list(data.get("occasion") or [])
    text = _texts_for_rules(cluster_input)
    primary_text = _primary_text_for_rules(cluster_input)
    text_tokens = _tokens_for_rules(text)
    primary_tokens = _tokens_for_rules(primary_text)
    axes = cluster_input.category_axes_payload if isinstance(cluster_input.category_axes_payload, dict) else {}

    product_type = str(functional.get("product_type") or "").strip()
    if "термокруж" in primary_text or "термо круж" in primary_text:
        product_type = "термокружка"
        _append_unique(constraints, "thermal")
        _append_unique(conflicts, "thermal")
    if not product_type:
        for axis in listify(axes.get("product_type_axes")):
            axis_norm = axis.lower().replace("ё", "е")
            axis_tokens = _tokens_for_rules(axis_norm)
            if axis_norm and (axis_norm in text or bool(axis_tokens & text_tokens)):
                product_type = axis
                break
    if "круж" in text and not product_type:
        product_type = "кружка"
    elif "тарел" in text and not product_type:
        product_type = "тарелка"
    elif "рюкзак" in text and not product_type:
        product_type = "рюкзак"
    if "пивн" in primary_text or "для пива" in primary_text:
        _append_unique(constraints, "beer_use_case")
        _append_unique(conflicts, "beer_use_case")
    quantity_match = _QUANTITY_RE.search(primary_text)
    if quantity_match:
        quantity = quantity_match.group(1)
        _append_unique(constraints, f"set_quantity:{quantity}")
        _append_unique(conflicts, f"set_quantity:{quantity}")
    elif "набор" in primary_tokens or "комплект" in primary_tokens:
        _append_unique(constraints, "set")
        _append_unique(conflicts, "set")

    attributes = listify(functional.get("attributes"))
    use_cases = listify(functional.get("use_cases"))
    use_case_rules = {
        "для школы": ("школ", "учеб"),
        "для путешествий": ("путешеств", "поезд"),
        "для прогулок": ("прогул",),
        "для ноутбука": ("ноутбук",),
        "для спорта": ("спорт", "трениров", "фитнес"),
        "для города": ("город", "городской"),
    }
    for use_case, markers in use_case_rules.items():
        if any(marker in primary_text for marker in markers):
            _append_unique(use_cases, use_case)
    for axis in listify(axes.get("use_case_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(use_cases, axis)
    material_rules = {
        "стекл": "material:glass",
        "керамич": "material:ceramic",
        "фарфор": "material:porcelain",
        "металл": "material:metal",
        "пластик": "material:plastic",
    }
    for token, constraint in material_rules.items():
        if token in primary_text:
            _append_unique(attributes, constraint.split(":", 1)[1])
            _append_unique(constraints, constraint)
            _append_unique(conflicts, constraint)
    for axis in listify(axes.get("attribute_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(attributes, axis)
    for motif in _query_motif_markers(primary_text):
        _append_unique(attributes, motif)
    for axis in listify(axes.get("constraint_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(constraints, axis)
            _append_unique(conflicts, axis)

    vibes = listify(expressive.get("vibes"))
    styles = listify(expressive.get("styles"))
    gift_contexts = listify(expressive.get("gift_contexts"))
    if _has_cute_marker(primary_tokens):
        _append_unique(vibes, "милая", "уютная")
    if _has_prefix_marker(primary_tokens, "красив", "эстет") or "пинтерест" in primary_tokens or "pinterest" in primary_tokens:
        _append_unique(vibes, "красивая", "эстетичная")
        if "пинтерест" in primary_text or "pinterest" in primary_text:
            _append_unique(styles, "pinterest")
    if "подар" in primary_text:
        _append_unique(gift_contexts, "подарок")
        _append_unique(occasion, "подарок")
    if "подруг" in primary_text:
        _append_unique(audience, "подруга")
    if "любим" in primary_text:
        _append_unique(audience, "любимая")
    if "девушк" in primary_text or "женск" in primary_text:
        _append_unique(audience, "женская")
    if "мужск" in primary_text or "мальчик" in primary_text:
        _append_unique(audience, "мужская")
    if "школ" in primary_text or "учеб" in primary_text:
        _append_unique(audience, "школьники")
    if "подрост" in primary_text:
        _append_unique(audience, "подростки")
    for axis in listify(axes.get("audience_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(audience, axis)
    for axis in listify(axes.get("expressive_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(vibes, axis)
    for axis in listify(axes.get("occasion_axes")):
        axis_norm = axis.lower().replace("ё", "е")
        if axis_norm and axis_norm in primary_text:
            _append_unique(occasion, axis)

    genericness = str(data.get("genericness") or "specific")
    if _query_motif_markers(primary_text) and genericness != "generic":
        genericness = "specific"
    normalized_examples = {item.strip() for item in cluster_input.source_query_examples if item.strip()}
    normalized_label = (cluster_input.top_query_text or cluster_input.label or "").strip().lower().replace("ё", "е")
    generic_patterns = {str(item).strip().lower().replace("ё", "е") for item in listify(axes.get("generic_query_patterns"))}
    hardcoded_generic = {"кружка", "кружки", "тарелка", "тарелки", "рюкзак", "рюкзаки"}
    if (
        normalized_label in hardcoded_generic
        or normalized_label in generic_patterns
        or normalized_examples <= hardcoded_generic
        or (generic_patterns and normalized_examples <= generic_patterns)
    ):
        genericness = "generic"
    elif "для чая" in primary_text or "чайная" in primary_text:
        genericness = "broad"

    functional["product_type"] = product_type or functional.get("product_type") or ""
    functional["use_cases"] = unique_strings(use_cases)
    functional["attributes"] = unique_strings(attributes)
    expressive["vibes"] = unique_strings(vibes)
    expressive["styles"] = unique_strings(styles)
    expressive["gift_contexts"] = unique_strings(gift_contexts)

    data.update(
        {
            "functional": functional,
            "expressive": expressive,
            "audience": unique_strings(audience),
            "occasion": unique_strings(occasion),
            "constraints": unique_strings(constraints),
            "conflicts_if_missing": unique_strings(conflicts),
            "genericness": genericness,
        }
    )
    return normalize_query_meaning_payload(data)


def _marker_values(profile: Mapping[str, Any], key: str) -> list[str]:
    values: list[str] = []
    raw_items = profile.get(key)
    if not isinstance(raw_items, list):
        return values
    for item in raw_items:
        if isinstance(item, dict):
            value = item.get("value") or item.get("normalized_value")
            if value:
                values.append(str(value))
    return values


def _deterministic_meaning_for_cluster(cluster_input: _ClusterInput) -> QueryMeaningPayload:
    profile = cluster_input.deterministic_profile if isinstance(cluster_input.deterministic_profile, dict) else {}
    product_type = _marker_values(profile, "product_type_markers")
    use_cases = _marker_values(profile, "use_case_markers")
    attributes = _marker_values(profile, "attribute_markers")
    language_markers = _marker_values(profile, "language_markers")
    genericness = "specific"
    quality_flags = profile.get("quality_flags") if isinstance(profile.get("quality_flags"), list) else []
    if "broad_cluster" in quality_flags or cluster_input.query_count >= 30 and len(cluster_input.source_query_examples) <= 2:
        genericness = "broad"

    payload = QueryMeaningPayload(
        functional={
            "product_type": product_type[0] if product_type else "",
            "use_cases": use_cases,
            "attributes": attributes,
        },
        expressive={"styles": [], "vibes": language_markers, "emotions": [], "gift_contexts": []},
        audience=[],
        occasion=[],
        constraints=[],
        conflicts_if_missing=[],
        genericness=genericness,  # type: ignore[arg-type]
        confidence={"functional": 0.45, "expressive": 0.35, "constraints": 0.45},
    )
    return _enforce_deterministic_rules(payload, cluster_input)


def _latest_ready_category_axes(session: Session, *, project_id: int, category_id: int) -> SeoCategoryMeaningAxes | None:
    return session.scalars(
        select(SeoCategoryMeaningAxes)
        .where(
            SeoCategoryMeaningAxes.project_id == int(project_id),
            SeoCategoryMeaningAxes.category_id == int(category_id),
            SeoCategoryMeaningAxes.schema_version == "category_meaning_axes_v0",
            SeoCategoryMeaningAxes.status == "ready",
        )
        .order_by(SeoCategoryMeaningAxes.source.desc(), SeoCategoryMeaningAxes.updated_at.desc())
    ).first()


def _item_from_row(row: SeoQueryMeaning) -> QueryMeaningItem:
    def _iso(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)

    payload = normalize_query_meaning_payload(row.meaning_payload or {})
    return QueryMeaningItem(
        id=int(row.id),
        project_id=int(row.project_id),
        category_id=int(row.category_id),
        cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
        cluster_key=str(row.cluster_key),
        schema_version=str(row.schema_version or QUERY_MEANING_SCHEMA_VERSION),
        source_query_examples=[str(item) for item in listify(row.source_query_examples)],
        meaning_payload=payload,
        canonical_text=str(row.canonical_text or ""),
        genericness=str(row.genericness or payload.genericness),  # type: ignore[arg-type]
        constraints=[str(item) for item in listify(row.constraints)],
        conflicts_if_missing=[str(item) for item in listify(row.conflicts_if_missing)],
        llm_model=row.llm_model,
        prompt_version=str(row.prompt_version or QUERY_MEANING_PROMPT_VERSION),
        input_hash=str(row.input_hash or ""),
        status=str(row.status or "draft"),  # type: ignore[arg-type]
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
    )


def _cluster_inputs(session: Session, *, project_id: int, category_id: int) -> list[_ClusterInput]:
    category_axes = _latest_ready_category_axes(session, project_id=project_id, category_id=category_id)
    category_axes_payload = dict(category_axes.axes_payload or {}) if category_axes is not None else {}
    category_axes_input_hash = str(category_axes.input_hash) if category_axes is not None else None
    clusters = session.scalars(
        select(SeoQueryCluster)
        .where(
            SeoQueryCluster.project_id == int(project_id),
            SeoQueryCluster.category_id == int(category_id),
        )
        .order_by(SeoQueryCluster.query_count.desc(), SeoQueryCluster.cluster_key.asc())
    ).all()
    memberships = session.scalars(
        select(SeoQueryClusterMembership).where(
            SeoQueryClusterMembership.project_id == int(project_id),
            SeoQueryClusterMembership.category_id == int(category_id),
        )
    ).all()
    members_by_cluster_id: dict[int, list[SeoQueryClusterMembership]] = {}
    for membership in memberships:
        members_by_cluster_id.setdefault(int(membership.cluster_id), []).append(membership)
    for member_rows in members_by_cluster_id.values():
        member_rows.sort(key=lambda item: (-float(item.ranking_value_used or 0), str(item.normalized_query_text)))

    try:
        profile_result = run_query_profile_extraction(
            session,
            project_id=project_id,
            category_id=category_id,
            top_limit=20,
            samples_limit=20,
            refresh_hybrid=False,
        )
        profiles_by_key = {item.cluster_key: item.to_dict() for item in profile_result.profiles}
    except Exception:
        profiles_by_key = {}

    inputs: list[_ClusterInput] = []
    for cluster in clusters:
        cluster_id = int(cluster.id)
        member_rows = members_by_cluster_id.get(cluster_id, [])
        examples = unique_strings(
            [
                cluster.top_query_text,
                cluster.label or cluster.top_query_text or cluster.cluster_key,
                *[str(member.normalized_query_text) for member in member_rows[:12]],
            ]
        )[:12]
        if not examples:
            continue
        max_rank = 0.0
        for member in member_rows:
            try:
                max_rank = max(max_rank, float(member.ranking_value_used or 0))
            except Exception:
                continue
        profile = profiles_by_key.get(cluster.cluster_key, {})
        hash_payload = {
            "schema_version": QUERY_MEANING_SCHEMA_VERSION,
            "prompt_version": QUERY_MEANING_PROMPT_VERSION,
            "cluster_id": cluster_id,
            "cluster_key": cluster.cluster_key,
            "label": cluster.label or cluster.top_query_text or cluster.cluster_key,
            "top_query_text": cluster.top_query_text,
            "source_query_examples": examples,
            "deterministic_profile": profile,
            "category_axes_input_hash": category_axes_input_hash,
            "rules_version": QUERY_MEANING_RULES_VERSION,
        }
        inputs.append(
            _ClusterInput(
                cluster_id=cluster_id,
                cluster_key=str(cluster.cluster_key),
                label=str(cluster.label or cluster.top_query_text or cluster.cluster_key),
                top_query_text=str(cluster.top_query_text or ""),
                source_query_examples=examples,
                query_count=int(cluster.query_count or len(examples)),
                max_ranking_value=max_rank,
                deterministic_profile=profile,
                category_axes_payload=category_axes_payload,
                category_axes_input_hash=category_axes_input_hash,
                input_hash=stable_hash(hash_payload),
            )
        )
    return inputs


def _store_artifact(
    *,
    project_id: int,
    category_id: int,
    cluster_key: str,
    model: str,
    input_hash: str,
    prompt: str,
    raw_response: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> None:
    artifact_dir = (
        _artifact_root()
        / "query_meaning"
        / f"p{int(project_id)}"
        / f"c{int(category_id)}"
        / f"cluster_{str(cluster_key)[:64]}"
        / f"m_{_safe_model_dir(model)}"
        / f"h_{str(input_hash)[:32]}"
    )
    _write_json(
        artifact_dir / "meta.json",
        {
            "created_at": _utc_now_iso(),
            "schema_version": QUERY_MEANING_SCHEMA_VERSION,
            "prompt_version": QUERY_MEANING_PROMPT_VERSION,
            "model": model,
            "input_hash": input_hash,
        },
    )
    _write_json(artifact_dir / "prompt.json", {"messages": [{"role": "user", "content": prompt}]})
    _write_json(artifact_dir / "raw_response.json", dict(raw_response))
    _write_json(artifact_dir / "parsed.json", dict(parsed))


def build_query_meaning_library(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int | None = 100,
    force_refresh: bool = False,
    use_llm: bool = False,
    provider: ChatProvider | None = None,
) -> QueryMeaningLibraryBuildResponse:
    cluster_inputs = _cluster_inputs(session, project_id=project_id, category_id=category_id)
    existing_rows = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.schema_version == QUERY_MEANING_SCHEMA_VERSION,
        )
    ).all()
    existing_by_key = {str(row.cluster_key): row for row in existing_rows}
    if force_refresh:
        candidate_inputs = cluster_inputs
    else:
        candidate_inputs = [
            cluster_input
            for cluster_input in cluster_inputs
            if (
                cluster_input.cluster_key not in existing_by_key
                or existing_by_key[cluster_input.cluster_key].input_hash != cluster_input.input_hash
            )
        ]
    if limit is None or int(limit) <= 0:
        limited_inputs = candidate_inputs
    else:
        limited_inputs = candidate_inputs[: max(1, int(limit))]
    resolved_provider = provider or OpenRouterProvider()
    model = str(getattr(resolved_provider, "chat_model", None) or "unknown_model") if use_llm else "deterministic/query_rules_v0"
    counters = {"processed": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    error_items: list[dict[str, Any]] = []

    for cluster_input in limited_inputs:
        row = session.scalars(
            select(SeoQueryMeaning).where(
                SeoQueryMeaning.project_id == int(project_id),
                SeoQueryMeaning.category_id == int(category_id),
                SeoQueryMeaning.cluster_key == cluster_input.cluster_key,
                SeoQueryMeaning.schema_version == QUERY_MEANING_SCHEMA_VERSION,
            )
        ).first()
        if row is not None and row.input_hash == cluster_input.input_hash and not force_refresh:
            counters["skipped"] += 1
            continue

        try:
            if use_llm:
                prompt = _prompt_for_cluster(cluster_input)
                response = resolved_provider.generate_chat(
                    [ChatMessage(role="user", content=prompt)],
                    temperature=0.1,
                    max_tokens=1200,
                )
                parsed = _extract_json_object(response.content)
                meaning = _enforce_deterministic_rules(normalize_query_meaning_payload(parsed), cluster_input)
                raw_response = dict(response.raw_response or {}) or {"model": response.model, "content": response.content}
                _store_artifact(
                    project_id=project_id,
                    category_id=category_id,
                    cluster_key=cluster_input.cluster_key,
                    model=str(response.model or model),
                    input_hash=cluster_input.input_hash,
                    prompt=prompt,
                    raw_response=raw_response,
                    parsed=meaning.model_dump(mode="json"),
                )
            else:
                meaning = _deterministic_meaning_for_cluster(cluster_input)
            canonical_text = build_query_canonical_text(meaning)
        except Exception as exc:
            counters["errors"] += 1
            error_items.append({"cluster_key": cluster_input.cluster_key, "error": str(exc)})
            continue

        is_new = row is None
        if row is None:
            row = SeoQueryMeaning(
                project_id=int(project_id),
                category_id=int(category_id),
                cluster_key=cluster_input.cluster_key,
                schema_version=QUERY_MEANING_SCHEMA_VERSION,
            )
            session.add(row)
        row.cluster_id = cluster_input.cluster_id
        row.source_query_examples = cluster_input.source_query_examples
        row.meaning_payload = meaning.model_dump(mode="json")
        row.canonical_text = canonical_text
        row.genericness = meaning.genericness
        row.constraints = meaning.constraints
        row.conflicts_if_missing = meaning.conflicts_if_missing
        row.llm_model = model
        row.prompt_version = QUERY_MEANING_PROMPT_VERSION
        row.input_hash = cluster_input.input_hash
        row.status = "ready"
        session.flush()

        counters["processed"] += 1
        counters["created" if is_new else "updated"] += 1

    return QueryMeaningLibraryBuildResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        total_clusters=len(cluster_inputs),
        processed=counters["processed"],
        created=counters["created"],
        updated=counters["updated"],
        skipped=counters["skipped"],
        errors=counters["errors"],
        error_items=error_items,
    )


def list_query_meanings(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> QueryMeaningLibraryResponse:
    stmt = select(SeoQueryMeaning).where(
        SeoQueryMeaning.project_id == int(project_id),
        SeoQueryMeaning.category_id == int(category_id),
    )
    if status:
        stmt = stmt.where(SeoQueryMeaning.status == status)
    rows = session.scalars(
        stmt.order_by(SeoQueryMeaning.cluster_key.asc()).offset(max(0, int(offset))).limit(max(1, min(int(limit), 1000)))
    ).all()
    total = session.scalars(stmt).all()
    return QueryMeaningLibraryResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        total=len(total),
        items=[_item_from_row(row) for row in rows],
    )
