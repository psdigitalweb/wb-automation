"""Meaning-aware query matcher preview."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SeoQueryClusterMembership, SeoQueryMeaning, SeoSkuMeaningAnnotation, SeoSkuQueryJudgment
from app.schemas.seo_query_meaning_matcher import (
    MEANING_AWARE_MATCHER_VERSION,
    MeaningAwareMatcherDiagnostics,
    MeaningAwareMatcherItem,
    MeaningAwareMatcherResponse,
)
from app.services.seo.providers.base import EmbeddingProvider
from app.services.seo.query_meaning_matcher.canonical import (
    build_sku_canonical_text,
    listify,
    normalize_query_meaning_payload,
    normalized_tokens,
)
from app.services.seo.query_meaning_matcher.embeddings import (
    LocalPreviewEmbeddingProvider,
    cosine_similarity,
    ensure_meaning_embedding,
)
from app.services.seo.query_pipeline import normalize_query_text
from app.services.seo.meaning_atoms import get_atoms_payload, merge_sku_and_vision_atoms
from app.services.seo.atoms.v1.schemas import QueryAtoms
from app.services.seo.atoms.v1.matcher_v1 import ATOMS_MATCHER_V1_VERSION, match_atoms_v1
from app.services.seo.visual_motifs import expand_visual_tokens


class MeaningAwareMatcherError(Exception):
    """Base matcher error."""


class MissingQueryMeaningLibraryError(MeaningAwareMatcherError):
    """Raised when matcher cannot run because query meanings are absent."""


class MissingSkuMeaningAnnotationError(MeaningAwareMatcherError):
    """Raised when matcher cannot run because SKU meaning annotation is absent."""


class CategoryBootstrapBuildingError(MeaningAwareMatcherError):
    """Raised when category bootstrap is still running."""


@dataclass(frozen=True)
class _FeatureSet:
    product_type: str
    tokens: set[str]
    use_case_terms: set[str]
    attribute_terms: set[str]
    expressive_terms: set[str]
    audience_terms: set[str]
    occasion_terms: set[str]
    negative_terms: set[str]
    negative_audience_terms: set[str]
    constraints: set[str]
    materials: set[str]
    canonical_text: str


_WEAK_OVERLAP_TOKENS = {
    "а",
    "без",
    "в",
    "во",
    "для",
    "до",
    "и",
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

_MATERIAL_CONSTRAINTS = {
    "material:glass": {"glass", "стекло", "стеклянная", "стеклянный", "стеклянные"},
    "material:ceramic": {"ceramic", "керамика", "керамическая", "керамический", "керамические"},
    "material:porcelain": {"porcelain", "фарфор", "фарфоровая", "фарфоровый", "фарфоровые"},
    "material:metal": {"metal", "металл", "металлическая", "металлический"},
    "material:plastic": {"plastic", "пластик", "пластиковая", "пластиковый"},
}


_EXPRESSIVE_GROUPS = {
    "милая": {"милота", "милая", "милый", "милые", "милую", "милого", "няшная", "няшный", "няшные"},
    "уют": {"уют", "уютная", "уютный"},
    "эстетика": {"эстет", "эстетичная", "красивая", "красив", "пинтерест", "pinterest", "стильный", "стильная", "стильные"},
}

_AUDIENCE_GROUPS = {
    "женская": {"женский", "женская", "женские", "женщине", "женщин", "девушка", "девушки", "девочке", "девочка", "девочек"},
    "мужская": {"мужской", "мужская", "мужские", "мужчине", "мужчин", "мальчик", "мальчика", "мальчиков"},
    "школьники": {"школьник", "школьники", "школьников", "школа", "школы", "школьный", "школьная", "учеба", "учебы"},
    "подростки": {"подросток", "подростка", "подростков", "подростковый", "подростковая"},
}

_USER_BUCKET_LABELS = {
    "primary": "Лучшие",
    "secondary": "Подходящие",
    "broad": "Слишком общие",
    "rejected": "Не подходят",
}


def _first_text(value: Any) -> str:
    values = listify(value)
    return values[0] if values else ""


def _expand_expressive(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for group_name, variants in _EXPRESSIVE_GROUPS.items():
        if group_name == "милая":
            matched = bool(tokens & variants) or any(token.startswith("милаш") for token in tokens)
        else:
            matched = any(any(token.startswith(variant) for variant in variants) for token in tokens)
        if matched:
            expanded.add(group_name)
    return expanded


def _expand_audience(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for group_name, variants in _AUDIENCE_GROUPS.items():
        if tokens & variants or any(any(token.startswith(variant) for variant in variants) for token in tokens):
            expanded.add(group_name)
    return expanded


def _expand_visual_terms(tokens: set[str]) -> set[str]:
    return expand_visual_tokens(tokens)


def _material_set(tokens: set[str], constraints: set[str]) -> set[str]:
    materials: set[str] = set()
    for constraint, variants in _MATERIAL_CONSTRAINTS.items():
        if constraint in constraints or any(token in variants or any(token.startswith(v[:5]) for v in variants if len(v) > 5) for token in tokens):
            materials.add(constraint)
    return materials


def _sku_features(meaning: Mapping[str, Any]) -> _FeatureSet:
    functional = meaning.get("functional") if isinstance(meaning.get("functional"), dict) else {}
    expressive = meaning.get("expressive") if isinstance(meaning.get("expressive"), dict) else {}
    canonical_text = build_sku_canonical_text(meaning)
    constraints: set[str] = set()
    positive_text = " ".join(listify(functional) + listify(expressive) + listify(meaning.get("audience")))
    all_tokens = normalized_tokens(functional, expressive, meaning.get("audience"))
    use_case_terms = normalized_tokens(functional.get("use_cases"))
    attribute_terms = _expand_visual_terms(normalized_tokens(functional.get("attributes")))
    expressive_terms = _expand_expressive(
        normalized_tokens(
            expressive.get("styles"),
            expressive.get("vibes"),
            expressive.get("emotions"),
            expressive.get("gift_contexts"),
        )
    )
    audience_terms = _expand_audience(normalized_tokens(meaning.get("audience"), functional.get("attributes"), functional.get("use_cases")))
    occasion_terms = normalized_tokens(expressive.get("gift_contexts"))
    negative_terms = normalized_tokens(meaning.get("negative_constraints"))
    negative_audience_terms = _expand_audience(negative_terms)
    if "подар" in positive_text.lower().replace("ё", "е"):
        occasion_terms.add("подарок")
    product_type = _first_text(functional.get("product_type")).lower().replace("ё", "е")
    if not product_type and any(token.startswith("круж") for token in all_tokens):
        product_type = "кружка"
    if "термокруж" in positive_text.lower().replace("ё", "е"):
        constraints.add("thermal")
    if "набор" in all_tokens or "комплект" in all_tokens:
        constraints.add("set")
    return _FeatureSet(
        product_type=product_type,
        tokens=all_tokens,
        use_case_terms=use_case_terms,
        attribute_terms=attribute_terms,
        expressive_terms=expressive_terms,
        audience_terms=audience_terms,
        occasion_terms=occasion_terms,
        negative_terms=negative_terms,
        negative_audience_terms=negative_audience_terms,
        constraints=constraints,
        materials=_material_set(all_tokens, constraints),
        canonical_text=canonical_text,
    )


def _query_features(row: SeoQueryMeaning) -> _FeatureSet:
    payload = normalize_query_meaning_payload(row.meaning_payload or {})
    functional = payload.functional or {}
    expressive = payload.expressive or {}
    canonical_text = str(row.canonical_text or "")
    constraints = set(str(item).lower().replace("ё", "е") for item in listify(row.constraints or payload.constraints))
    all_tokens = normalized_tokens(canonical_text, functional, expressive, payload.audience, payload.occasion, constraints)
    use_case_terms = normalized_tokens(functional.get("use_cases"))
    attribute_terms = _expand_visual_terms(normalized_tokens(functional.get("attributes"), canonical_text))
    expressive_terms = _expand_expressive(
        normalized_tokens(
            expressive.get("styles"),
            expressive.get("vibes"),
            expressive.get("emotions"),
            expressive.get("gift_contexts"),
        )
    )
    product_type = _first_text(functional.get("product_type")).lower().replace("ё", "е")
    return _FeatureSet(
        product_type=product_type,
        tokens=all_tokens,
        use_case_terms=use_case_terms,
        attribute_terms=attribute_terms,
        expressive_terms=expressive_terms,
        audience_terms=_expand_audience(normalized_tokens(payload.audience, functional.get("use_cases"), functional.get("attributes"))),
        occasion_terms=normalized_tokens(payload.occasion, expressive.get("gift_contexts")),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=constraints,
        materials=_material_set(all_tokens, constraints),
        canonical_text=canonical_text,
    )


def _ranking_by_cluster(session: Session, *, project_id: int, category_id: int, cluster_ids: list[int]) -> dict[int, float]:
    if not cluster_ids:
        return {}
    rows = session.execute(
        select(SeoQueryClusterMembership.cluster_id, SeoQueryClusterMembership.ranking_value_used)
        .where(
            SeoQueryClusterMembership.project_id == int(project_id),
            SeoQueryClusterMembership.category_id == int(category_id),
            SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
        )
        .order_by(desc(SeoQueryClusterMembership.ranking_value_used))
    ).all()
    result: dict[int, float] = {}
    for cluster_id, ranking in rows:
        cid = int(cluster_id)
        try:
            value = float(ranking or 0)
        except Exception:
            value = 0.0
        result[cid] = max(result.get(cid, 0.0), value)
    return result


def _hard_conflicts(sku: _FeatureSet, query: _FeatureSet) -> list[str]:
    conflicts: list[str] = []
    if "thermal" in query.constraints and "thermal" not in sku.constraints and "термокруж" not in sku.product_type:
        conflicts.append("requires thermal/термокружка, SKU meaning does not")
    if query.product_type == "термокружка" and sku.product_type != "термокружка":
        conflicts.append("product_type conflict: термокружка vs SKU product type")
    if "beer_use_case" in query.constraints and "beer_use_case" not in sku.constraints and "пив" not in sku.tokens:
        conflicts.append("requires beer mug use case")
    set_constraints = [item for item in query.constraints if item == "set" or item.startswith("set_quantity:")]
    if set_constraints and not any(item == "set" or item.startswith("set_quantity:") for item in sku.constraints):
        conflicts.append(f"requires set/quantity: {', '.join(set_constraints)}")
    if query.materials and sku.materials and not (query.materials & sku.materials):
        conflicts.append(f"material conflict: requires {', '.join(sorted(query.materials))}")
    negative_audience = (sku.negative_audience_terms & query.audience_terms) & {
        "женская",
        "мужская",
        "школьники",
        "подростки",
    }
    if negative_audience:
        conflicts.append(f"blocked by SKU negative constraint: {', '.join(sorted(negative_audience))}")
    return conflicts


def _product_type_score(sku: _FeatureSet, query: _FeatureSet) -> tuple[float, list[str]]:
    if not query.product_type:
        return 0.0, []
    if sku.product_type and sku.product_type == query.product_type:
        return 0.22, [f"product_type matched: {query.product_type}"]
    if query.product_type == "кружка" and "круж" in sku.product_type:
        return 0.16, ["product_type compatible: кружка"]
    if query.product_type == "рюкзак" and "рюкзак" in sku.product_type:
        return 0.18, ["product_type compatible: рюкзак"]
    return -0.18, [f"product_type weak/conflicting: {query.product_type}"]


def _overlap_score(label: str, left: set[str], right: set[str], weight: float) -> tuple[float, list[str], list[str]]:
    overlap = sorted((left & right) - _WEAK_OVERLAP_TOKENS)
    if not overlap:
        return 0.0, [], []
    score = min(weight, weight * (0.55 + 0.25 * len(overlap)))
    return score, overlap, [f"{label} matched: {', '.join(overlap[:5])}"]


def _frequency_boost(value: float | None, *, allow: bool) -> float:
    if not allow or value is None or value <= 0:
        return 0.0
    return min(0.08, math.log10(value + 1.0) / 90.0)


def _bucket_for(
    *,
    score: float,
    genericness: str,
    conflicts: list[str],
    semantic_similarity: float,
    expressive_overlap: list[str],
    audience_overlap: list[str],
    occasion_overlap: list[str],
    use_case_overlap: list[str],
    attribute_overlap: list[str],
) -> str:
    if conflicts or (score < 0.28 and semantic_similarity < 0.42):
        return "rejected"
    has_specific_meaning_match = bool(expressive_overlap or audience_overlap or occasion_overlap or use_case_overlap or attribute_overlap)
    if genericness == "generic" and not has_specific_meaning_match:
        return "broad"
    if genericness == "broad" and not has_specific_meaning_match and semantic_similarity < 0.78:
        return "broad"
    if occasion_overlap and not expressive_overlap and not audience_overlap and not use_case_overlap and not attribute_overlap:
        return "secondary"
    if score >= 0.62 and (expressive_overlap or audience_overlap or occasion_overlap or use_case_overlap or attribute_overlap or semantic_similarity >= 0.72):
        return "primary"
    return "secondary"


def _query_display(row: SeoQueryMeaning) -> str:
    examples = listify(row.source_query_examples)
    return examples[0] if examples else str(row.cluster_key)


def _judgment_overrides_by_query(
    session: Session,
    *,
    annotation_id: int,
) -> tuple[dict[str, SeoSkuQueryJudgment], dict[str, SeoSkuQueryJudgment]]:
    rows = session.scalars(
        select(SeoSkuQueryJudgment).where(SeoSkuQueryJudgment.annotation_id == int(annotation_id))
    ).all()
    by_query: dict[str, SeoSkuQueryJudgment] = {}
    by_cluster_key: dict[str, SeoSkuQueryJudgment] = {}
    for row in rows:
        normalized = normalize_query_text(str(row.normalized_query_text or row.query_text or ""))
        if normalized:
            by_query[normalized] = row
        if row.cluster_key:
            by_cluster_key[str(row.cluster_key)] = row
    return by_query, by_cluster_key


def _manual_bucket_override(row: SeoQueryMeaning, judgment: SeoSkuQueryJudgment | None) -> tuple[str | None, list[str], list[str]]:
    if judgment is None:
        return None, [], []
    label = str(judgment.label or "")
    reason = f"manual judgment: {label}"
    if judgment.rationale:
        reason = f"{reason} ({judgment.rationale})"
    if label in {"manual_rejected", "irrelevant", "conflict", "dangerous_claim"}:
        return "rejected", [reason], [reason]
    if label == "too_broad":
        return "broad", [reason], []
    if label in {"highly_relevant", "maybe_relevant"}:
        return None, [reason], []
    return None, [reason], []


def _user_reasons(*, bucket: str, matched_atoms: list[str], missing_atoms: list[str], conflict_atoms: list[str], fallback_reasons: list[str]) -> list[str]:
    reasons: list[str] = []
    if conflict_atoms:
        reasons.append("Есть обязательное несовпадение с товаром")
    if missing_atoms:
        reasons.append("В запросе есть требование, которого нет у товара")
    if matched_atoms:
        reasons.append("Совпали признаки товара и запроса")
    if bucket == "broad":
        reasons.append("Запрос слишком общий для точной оптимизации")
    if not reasons:
        if any("manual judgment" in item for item in fallback_reasons):
            reasons.append("Учтена ручная правка")
        elif bucket == "primary":
            reasons.append("Хорошее смысловое совпадение без конфликтов")
        elif bucket == "secondary":
            reasons.append("Запрос подходит, но не самый точный")
        elif bucket == "rejected":
            reasons.append("Смысл запроса слабо соответствует товару")
    return reasons


def _query_coverage_tags(item: MeaningAwareMatcherItem) -> list[str]:
    query = normalize_query_text(item.query)
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    if "пинтерест" in query or "pinterest" in query:
        add("style:pinterest")
    if "эстет" in query or "красив" in query:
        add("style:aesthetic")
    if "мил" in query or "няш" in query:
        add("style:cute")

    for atom in item.matched_atoms:
        parts = str(atom or "").split(":")
        if len(parts) < 2:
            continue
        if "motif" in parts:
            add(f"motif:{parts[-1]}")
        elif "expressive" in parts:
            add(f"expressive:{parts[-1]}")
        elif "recipient" in parts:
            add(f"recipient:{parts[-1]}")
        elif "occasion" in parts:
            add(f"occasion:{parts[-1]}")
    return tags


def _select_bucket_with_coverage(candidates: list[MeaningAwareMatcherItem], limit: int) -> list[MeaningAwareMatcherItem]:
    if len(candidates) <= limit:
        return candidates
    selected: list[MeaningAwareMatcherItem] = []
    selected_keys: set[tuple[str, int | None, str]] = set()
    tag_counts: dict[str, int] = {}
    coverage_budget = min(20, max(8, limit // 2))
    per_tag_limit = 3

    def key(item: MeaningAwareMatcherItem) -> tuple[str, int | None, str]:
        return (str(item.cluster_key or ""), item.query_meaning_id, normalize_query_text(item.query))

    def add(item: MeaningAwareMatcherItem) -> bool:
        item_key = key(item)
        if item_key in selected_keys:
            return False
        selected.append(item)
        selected_keys.add(item_key)
        return True

    tag_items: dict[str, list[MeaningAwareMatcherItem]] = {}
    for item in candidates:
        for tag in _query_coverage_tags(item):
            tag_items.setdefault(tag, []).append(item)

    priority_tags = [
        "style:pinterest",
        "style:aesthetic",
        "style:cute",
        *sorted(tag for tag in tag_items if not tag.startswith("style:")),
    ]
    for tag in priority_tags:
        if len(selected) >= coverage_budget:
            break
        for item in tag_items.get(tag, []):
            if tag_counts.get(tag, 0) >= per_tag_limit or len(selected) >= coverage_budget:
                break
            if add(item):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    for item in candidates:
        if len(selected) >= limit:
            break
        add(item)
    return selected[:limit]


def _apply_atoms_gate(
    *,
    bucket: str,
    score: float,
    row: SeoQueryMeaning,
    query_display: str,
    ranking_value: float | None,
    sku_atoms: Any,
    query_atoms_payload: dict[str, Any] | None,
) -> tuple[str, float, list[str], list[str], list[str], list[str]]:
    if sku_atoms is None or not query_atoms_payload:
        return bucket, score, [], [], [], ["atoms gate skipped: missing SKU or query atoms"]
    try:
        query_atoms = QueryAtoms.model_validate(query_atoms_payload)
        atoms_result = match_atoms_v1(
            sku_atoms,
            query_atoms,
            query_text=query_display,
            cluster_key=str(row.cluster_key or ""),
            ranking_value_used=ranking_value,
        )
    except Exception as exc:
        return bucket, score, [], [], [], [f"atoms gate skipped: {type(exc).__name__}: {exc}"]

    gated_bucket = bucket
    gated_score = score
    if atoms_result.bucket == "rejected":
        gated_bucket = "rejected"
        gated_score = min(score, atoms_result.score, 0.05)
    elif atoms_result.bucket == "broad":
        if bucket in {"primary", "secondary"}:
            gated_bucket = "broad"
            gated_score = min(score, 0.45)
    elif atoms_result.bucket == "primary":
        if bucket in {"secondary", "broad"}:
            gated_bucket = "primary"
        gated_score = max(score, atoms_result.score)
    elif bucket == "primary" and atoms_result.bucket != "primary":
        gated_bucket = "secondary"
        gated_score = min(score, max(0.34, atoms_result.score))

    debug_reasons = [f"atoms bucket: {atoms_result.bucket}", *atoms_result.reasons]
    return (
        gated_bucket,
        round(max(0.0, min(1.0, gated_score)), 4),
        atoms_result.matched_atoms,
        atoms_result.missing_atoms,
        atoms_result.conflict_atoms,
        debug_reasons,
    )


def _get_sku_annotation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoSkuMeaningAnnotation:
    row = session.scalars(
        select(SeoSkuMeaningAnnotation)
        .where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.category_id == int(category_id),
            SeoSkuMeaningAnnotation.nm_id == int(nm_id),
        )
        .order_by(SeoSkuMeaningAnnotation.updated_at.desc())
    ).first()
    if row is None:
        raise MissingSkuMeaningAnnotationError("Save SKU Meaning annotation before running matcher preview")
    return row


def run_meaning_aware_matcher(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 120,
    include_rejected: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
) -> MeaningAwareMatcherResponse:
    resolved_embedding_provider = embedding_provider or LocalPreviewEmbeddingProvider()
    sku_annotation = _get_sku_annotation(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
    from app.services.seo.category_bootstrap import get_readiness_row

    readiness = get_readiness_row(session, project_id=project_id, category_id=category_id)
    readiness_status = str(readiness.status) if readiness is not None else "not_started"
    if readiness_status == "building":
        raise CategoryBootstrapBuildingError("Category bootstrap is still running. Refresh readiness status before matching.")
    query_rows = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
        )
    ).all()
    if not query_rows:
        if readiness_status in {"not_started", "failed"}:
            detail = "Query Meaning Library is empty for this category. Run category bootstrap first."
            if readiness is not None and readiness.last_error:
                detail = f"{detail} Last bootstrap error: {readiness.last_error}"
            raise MissingQueryMeaningLibraryError(detail)
        raise MissingQueryMeaningLibraryError(
            "Query Meaning Library is empty for this category. Build/refresh query meanings first."
        )

    sku_meaning = dict(sku_annotation.meaning_payload or {})
    sku_features = _sku_features(sku_meaning)
    sku_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        nm_id=nm_id,
    )
    vision_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_vision",
        entity_id=int(sku_annotation.id),
        nm_id=nm_id,
    )
    sku_atoms = merge_sku_and_vision_atoms(sku_atoms_payload, vision_atoms_payload)
    atoms_gate_enabled = sku_atoms is not None
    judgment_by_query, judgment_by_cluster_key = _judgment_overrides_by_query(
        session,
        annotation_id=int(sku_annotation.id),
    )
    sku_embedding = ensure_meaning_embedding(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        canonical_text=sku_features.canonical_text,
        provider=resolved_embedding_provider,
    )
    ranking_by_cluster = _ranking_by_cluster(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_ids=[int(row.cluster_id) for row in query_rows if row.cluster_id is not None],
    )

    items: list[MeaningAwareMatcherItem] = []
    embedding_model: str | None = str(sku_embedding.model)
    for row in query_rows:
        query_display = _query_display(row)
        query_features = _query_features(row)
        query_embedding = ensure_meaning_embedding(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
            canonical_text=str(row.canonical_text or ""),
            provider=resolved_embedding_provider,
        )
        embedding_model = str(query_embedding.model or embedding_model)
        raw_similarity = cosine_similarity(sku_embedding.embedding or [], query_embedding.embedding or [])
        semantic_similarity = round(max(0.0, min(1.0, (raw_similarity + 1.0) / 2.0)), 4)

        conflicts = _hard_conflicts(sku_features, query_features)
        reasons: list[str] = []
        matched: list[str] = []
        product_score, product_reasons = _product_type_score(sku_features, query_features)
        reasons.extend(product_reasons)
        expressive_score, expressive_overlap, expressive_reasons = _overlap_score(
            "expressive",
            sku_features.expressive_terms,
            query_features.expressive_terms,
            0.22,
        )
        use_case_score, use_case_overlap, use_case_reasons = _overlap_score(
            "use_case",
            sku_features.use_case_terms,
            query_features.use_case_terms,
            0.14,
        )
        attribute_score, attribute_overlap, attribute_reasons = _overlap_score(
            "attribute",
            sku_features.attribute_terms,
            query_features.attribute_terms,
            0.08,
        )
        audience_score, audience_overlap, audience_reasons = _overlap_score(
            "audience",
            sku_features.audience_terms,
            query_features.audience_terms,
            0.12,
        )
        occasion_score, occasion_overlap, occasion_reasons = _overlap_score(
            "occasion",
            sku_features.occasion_terms,
            query_features.occasion_terms,
            0.05,
        )
        reasons.extend(expressive_reasons + use_case_reasons + attribute_reasons + audience_reasons + occasion_reasons)
        matched.extend(expressive_overlap + use_case_overlap + attribute_overlap + audience_overlap + occasion_overlap)

        genericness = str(row.genericness or "specific")
        specificity_bonus = 0.08 if genericness == "specific" else 0.0
        genericness_penalty = 0.18 if genericness == "generic" else (0.09 if genericness == "broad" else 0.0)
        conflict_penalty = 0.55 if conflicts else 0.0
        ranking_value = ranking_by_cluster.get(int(row.cluster_id)) if row.cluster_id is not None else None
        frequency = _frequency_boost(ranking_value, allow=not conflicts and genericness == "specific")
        score = (
            0.34 * semantic_similarity
            + product_score
            + expressive_score
            + use_case_score
            + attribute_score
            + audience_score
            + occasion_score
            + specificity_bonus
            + frequency
            - genericness_penalty
            - conflict_penalty
        )
        score = round(max(0.0, min(1.0, score)), 4)
        if conflicts:
            reasons.extend(conflicts)
        elif not conflicts:
            reasons.append("no hard constraints")
        if frequency:
            reasons.append("frequency boosts already relevant candidate")
        if genericness in {"generic", "broad"}:
            reasons.append(f"downgraded by genericness: {genericness}")

        bucket = _bucket_for(
            score=score,
            genericness=genericness,
            conflicts=conflicts,
            semantic_similarity=semantic_similarity,
            expressive_overlap=expressive_overlap,
            audience_overlap=audience_overlap,
            occasion_overlap=occasion_overlap,
            use_case_overlap=use_case_overlap,
            attribute_overlap=attribute_overlap,
        )
        judgment = judgment_by_cluster_key.get(str(row.cluster_key)) or judgment_by_query.get(normalize_query_text(query_display))
        manual_bucket, manual_reasons, manual_conflicts = _manual_bucket_override(row, judgment)
        if manual_reasons:
            reasons.extend(manual_reasons)
        if manual_conflicts:
            conflicts.extend(manual_conflicts)
            score = min(score, 0.01)
        if manual_bucket is not None:
            bucket = manual_bucket

        query_atoms_payload = get_atoms_payload(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
        )
        bucket, score, matched_atoms, missing_atoms, conflict_atoms, debug_reasons = _apply_atoms_gate(
            bucket=bucket,
            score=score,
            row=row,
            query_display=query_display,
            ranking_value=ranking_value,
            sku_atoms=sku_atoms,
            query_atoms_payload=query_atoms_payload,
        )
        if conflict_atoms:
            conflicts.extend(conflict_atoms)
        reasons.extend(debug_reasons)
        if bucket == "rejected" and not include_rejected:
            continue
        items.append(
            MeaningAwareMatcherItem(
                query=query_display,
                cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
                cluster_key=str(row.cluster_key),
                query_meaning_id=int(row.id),
                bucket=bucket,  # type: ignore[arg-type]
                score=score,
                semantic_similarity=semantic_similarity,
                ranking_value_used=ranking_value,
                genericness=genericness,  # type: ignore[arg-type]
                matched_meanings=sorted(set(matched)),
                conflicts=conflicts,
                reasons=reasons,
                user_bucket_label=_USER_BUCKET_LABELS.get(bucket, bucket),
                user_reasons=_user_reasons(
                    bucket=bucket,
                    matched_atoms=matched_atoms,
                    missing_atoms=missing_atoms,
                    conflict_atoms=conflict_atoms,
                    fallback_reasons=reasons,
                ),
                matched_atoms=matched_atoms,
                missing_atoms=missing_atoms,
                conflict_atoms=conflict_atoms,
                debug_reasons=reasons,
            )
        )

    per_bucket_limit = max(10, min(100, math.ceil(max(1, int(limit)) / 4)))
    items.sort(key=lambda item: (-item.score, -(item.ranking_value_used or 0), item.query))
    buckets = {
        "primary": _select_bucket_with_coverage([item for item in items if item.bucket == "primary"], per_bucket_limit),
        "secondary": _select_bucket_with_coverage([item for item in items if item.bucket == "secondary"], per_bucket_limit),
        "broad": [item for item in items if item.bucket == "broad"][:per_bucket_limit],
        "rejected": [item for item in items if item.bucket == "rejected"][:per_bucket_limit],
    }
    return MeaningAwareMatcherResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        sku_annotation_id=int(sku_annotation.id),
        sku_annotation_status=str(sku_annotation.status or "draft"),
        buckets=buckets,  # type: ignore[arg-type]
        diagnostics=MeaningAwareMatcherDiagnostics(
            matcher_version=MEANING_AWARE_MATCHER_VERSION,
            query_meanings_total=len(query_rows),
            scored_total=len(items),
            missing_library=False,
            embedding_model=embedding_model,
            atoms_version=ATOMS_MATCHER_V1_VERSION,
            atoms_gate_enabled=atoms_gate_enabled,
            notes=[
                "frequency never creates relevance by itself",
                "atoms gate protects Primary from hard semantic conflicts" if atoms_gate_enabled else "atoms gate skipped: analyze SKU to create SKU atoms",
                f"category readiness: {readiness_status}",
                *(
                    ["category uses deterministic fallback axes; rerun bootstrap with LLM for better quality"]
                    if readiness_status == "ready_with_fallback"
                    else []
                ),
            ],
        ),
    )
