"""LLM extraction for the meaning atoms shadow experiment."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from app.services.seo.atoms.v1.guards import apply_query_guards, apply_sku_guards, canonical_value, field_family, normalize_text
from app.services.seo.atoms.v1.schemas import (
    MEANING_ATOMS_PROMPT_VERSION,
    MeaningAtom,
    QueryAtoms,
    SkuAtoms,
)
from app.services.seo.category_profile import CategoryProfile
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.query_meaning_matcher.canonical import listify, stable_hash


class MeaningAtomsExtractionError(Exception):
    """Raised when LLM atoms extraction fails."""


_ALLOWED_TYPES = {
    "product_type",
    "attribute",
    "numeric",
    "visual",
    "recipient",
    "occasion",
    "use_case",
    "compatibility",
    "expressive",
    "exclusion",
}
_ALLOWED_OPERATORS = {"equals", "close_to", "contains", "excludes", "compatible_with"}


def _sanitize_atom(raw: Any, *, default_importance: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item = dict(raw)
    atom_type = str(item.get("type") or item.get("atom_type") or "attribute").strip()
    if atom_type in {"style", "emotion", "vibe"}:
        atom_type = "expressive"
    if atom_type in {"quantity", "volume", "size"}:
        atom_type = "numeric"
    if atom_type in {"audience", "gift_recipient"}:
        atom_type = "recipient"
    if atom_type not in _ALLOWED_TYPES:
        atom_type = "attribute"
    item["type"] = atom_type
    item["field"] = str(item.get("field") or atom_type or "attribute").strip()
    item["value"] = item.get("value")
    operator = str(item.get("operator") or "equals").strip()
    if operator not in _ALLOWED_OPERATORS:
        operator = "equals"
    item["operator"] = operator
    importance = str(item.get("importance") or default_importance).strip().lower()
    if importance in {"required", "mandatory", "must", "hard_required"}:
        importance = "hard"
    elif importance in {"preferred", "optional", "nice_to_have"}:
        importance = "soft"
    if importance not in {"hard", "soft"}:
        importance = default_importance
    item["importance"] = importance
    item["source"] = str(item.get("source") or "llm")
    try:
        confidence = float(item.get("confidence", 0.5))
    except Exception:
        confidence = 0.5
    item["confidence"] = max(0.0, min(1.0, confidence))
    return item


def _sanitize_atoms_payload(data: dict[str, Any], *, kind: str) -> dict[str, Any]:
    result = dict(data)
    if isinstance(result.get("product_type"), list) and result.get("product_type"):
        result["product_type"] = result["product_type"][0]
    if isinstance(result.get("product_type"), dict):
        product_atom = _sanitize_atom(result.get("product_type"), default_importance="hard")
        if product_atom is not None:
            result.setdefault("required_atoms", [])
            if isinstance(result["required_atoms"], list):
                result["required_atoms"].append(product_atom)
            result["product_type"] = str(product_atom.get("value") or "")
    if result.get("product_type") is None:
        result["product_type"] = ""
    elif not isinstance(result.get("product_type"), str):
        result["product_type"] = str(result.get("product_type") or "")
    elif "{'type'" in result["product_type"] or '"type"' in result["product_type"]:
        match = re.search(r"""['"]value['"]\s*:\s*['"]([^'"]+)['"]""", result["product_type"])
        if match:
            result["product_type"] = match.group(1)
    if kind == "query":
        if isinstance(result.get("buyer_intent"), dict):
            intent_atom = _sanitize_atom(result.get("buyer_intent"), default_importance="soft")
            if intent_atom is not None:
                result.setdefault("preferred_atoms", [])
                if isinstance(result["preferred_atoms"], list):
                    result["preferred_atoms"].append(intent_atom)
                result["buyer_intent"] = str(intent_atom.get("value") or "")
        if result.get("buyer_intent") is None:
            result["buyer_intent"] = ""
        elif not isinstance(result.get("buyer_intent"), str):
            result["buyer_intent"] = str(result.get("buyer_intent") or "")
        if result.get("genericness") not in {"specific", "broad", "generic"}:
            result["genericness"] = "specific"
    else:
        if isinstance(result.get("product_identity"), dict):
            identity = result.get("product_identity") or {}
            result["product_identity"] = str(
                identity.get("title")
                or identity.get("name")
                or identity.get("product_identity")
                or identity.get("description")
                or json.dumps(identity, ensure_ascii=False, default=str)
            )
        if result.get("product_identity") is None:
            result["product_identity"] = ""
        elif not isinstance(result.get("product_identity"), str):
            result["product_identity"] = str(result.get("product_identity") or "")
    confidence = result.get("confidence")
    if isinstance(confidence, int | float):
        result["confidence"] = {"overall": max(0.0, min(1.0, float(confidence)))}
    elif not isinstance(confidence, dict):
        result["confidence"] = {}
    if not isinstance(result.get("evidence_refs"), list):
        result["evidence_refs"] = []
    if kind == "query":
        atom_keys = {
            "required_atoms": "hard",
            "preferred_atoms": "soft",
            "excluded_atoms": "hard",
            "negative_fit_atoms": "soft",
        }
    else:
        atom_keys = {
            "facts": "soft",
            "positive_atoms": "soft",
            "negative_fit_atoms": "soft",
        }
    product_type_value = str(result.get("product_type") or "").strip().lower().replace("ё", "е")
    for key, default_importance in atom_keys.items():
        raw_items = result.get(key)
        if not isinstance(raw_items, list):
            raw_items = []
        cleaned = []
        for raw in raw_items:
            item = _sanitize_atom(raw, default_importance=default_importance)
            if item is not None:
                if (
                    kind == "query"
                    and key == "required_atoms"
                    and item.get("type") == "attribute"
                    and str(item.get("value") or "").strip().lower().replace("ё", "е") == product_type_value
                ):
                    continue
                cleaned.append(item)
        result[key] = cleaned
    return result


def _query_mentions_atom(query_text: str, atom: MeaningAtom) -> bool:
    text = normalize_text(query_text)
    raw = normalize_text(atom.value)
    canonical = canonical_value(field_family(atom.field), atom.value)
    if raw and raw in text:
        return True
    if canonical and canonical in text:
        return True
    if field_family(atom.field) == "recipient":
        recipient_markers = {
            "папа": ("пап", "отец"),
            "мама": ("мам",),
            "подруга": ("подруг",),
            "любимая": ("любим",),
            "сестра": ("сестр",),
            "брат": ("брат",),
            "муж": ("мужу", "мужа", "супруг"),
            "жена": ("жене", "жену", "жена", "супруга"),
            "девушка": ("девуш",),
            "парень": ("парн",),
            "подростки": ("подрост",),
            "женщина": ("женщ", "женск"),
            "мужчина": ("мужчин", "мужск"),
            "девочка": ("девоч",),
        }
        return any(marker in text for marker in recipient_markers.get(canonical, (canonical,)))
    return False


def _is_soft_audience_atom(atom: MeaningAtom) -> bool:
    if atom.type != "recipient" and field_family(atom.field) != "recipient":
        return False
    raw = normalize_text(atom.value)
    canonical = canonical_value("recipient", atom.value)
    if canonical in {"женщина", "мужчина", "девочка", "девушка", "подростки"}:
        return True
    return any(marker in raw for marker in ("женщ", "женск", "девоч", "девуш", "подрост", "дет", "ребен", "мужск", "мужчин"))


def _as_preferred(atom: MeaningAtom, *, atom_type: str | None = None, field: str | None = None, source_suffix: str = "v02_softened") -> MeaningAtom:
    data = atom.model_dump(mode="json")
    data["importance"] = "soft"
    data["source"] = f"{data.get('source') or 'llm'}:{source_suffix}"
    if atom_type is not None:
        data["type"] = atom_type
    if field is not None:
        data["field"] = field
    return MeaningAtom.model_validate(data)


def normalize_query_atoms_v02(query: QueryAtoms, *, primary_query: str) -> QueryAtoms:
    """Apply v0.2 role policy after LLM extraction and cache loading."""

    result = query.model_copy(deep=True)
    required: list[MeaningAtom] = []
    preferred = list(result.preferred_atoms)
    for atom in result.required_atoms:
        field_norm = field_family(atom.field)
        value_norm = normalize_text(atom.value)
        if atom.field == "product_type":
            required.append(atom)
            continue
        if atom.type == "expressive" or field_norm in {"style", "styles", "vibe", "vibes", "emotion", "emotions", "expressive"}:
            preferred.append(_as_preferred(atom, atom_type="expressive", field="expressive"))
            continue
        if atom.type == "recipient" and _is_soft_audience_atom(atom):
            preferred.append(_as_preferred(atom, atom_type="recipient", field="recipient", source_suffix="v02_audience_soft"))
            continue
        if atom.type == "recipient" and not _query_mentions_atom(primary_query, atom):
            preferred.append(_as_preferred(atom, source_suffix="v02_variant_recipient"))
            continue
        if any(marker in value_norm for marker in {"чай", "чая", "кофе"}) and field_norm not in {"compatibility", "thermal"}:
            preferred.append(_as_preferred(atom, atom_type="use_case", field="use_case", source_suffix="v02_beverage_soft"))
            continue
        if atom.type == "use_case" and any(marker in value_norm for marker in {"чай", "чая", "кофе"}):
            preferred.append(_as_preferred(atom, source_suffix="v02_beverage_soft"))
            continue
        if atom.type == "attribute" and field_norm == "use_case":
            preferred.append(_as_preferred(atom, atom_type="use_case", field=field_norm, source_suffix="v02_beverage_soft"))
            continue
        if atom.type == "attribute" and field_norm == "recipient" and _is_soft_audience_atom(atom):
            preferred.append(_as_preferred(atom, atom_type="recipient", field="recipient", source_suffix="v02_audience_soft"))
            continue
        if atom.type == "attribute" and field_norm == "recipient" and not _query_mentions_atom(primary_query, atom):
            preferred.append(_as_preferred(atom, atom_type="recipient", field="recipient", source_suffix="v02_variant_recipient"))
            continue
        required.append(atom)
    result.required_atoms = required
    result.preferred_atoms = preferred
    return result


def _extract_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise MeaningAtomsExtractionError("LLM response does not contain a JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MeaningAtomsExtractionError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MeaningAtomsExtractionError("LLM response JSON must be an object")
    return data


def parse_query_atoms_response(content: str, *, query: str | None = None, cluster_key: str | None = None) -> QueryAtoms:
    data = _sanitize_atoms_payload(_extract_json_object(content), kind="query")
    if query and not data.get("query"):
        data["query"] = query
    if cluster_key and not data.get("cluster_key"):
        data["cluster_key"] = cluster_key
    try:
        return QueryAtoms.model_validate(data)
    except Exception as exc:
        raise MeaningAtomsExtractionError(f"Invalid query atoms JSON: {exc}") from exc


def parse_sku_atoms_response(content: str, *, project_id: int | None = None, category_id: int | None = None, nm_id: int | None = None) -> SkuAtoms:
    data = _sanitize_atoms_payload(_extract_json_object(content), kind="sku")
    if project_id is not None and data.get("project_id") is None:
        data["project_id"] = int(project_id)
    if category_id is not None and data.get("category_id") is None:
        data["category_id"] = int(category_id)
    if nm_id is not None and data.get("nm_id") is None:
        data["nm_id"] = int(nm_id)
    try:
        return SkuAtoms.model_validate(data)
    except Exception as exc:
        raise MeaningAtomsExtractionError(f"Invalid SKU atoms JSON: {exc}") from exc


def _provider_or_default(provider: ChatProvider | None) -> ChatProvider:
    return provider or OpenRouterProvider()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _read_cached_atoms(cache_dir: Path | None, key: str, *, kind: str) -> QueryAtoms | SkuAtoms | None:
    if cache_dir is None:
        return None
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    atoms = payload.get("atoms") if isinstance(payload, dict) else None
    if kind == "query":
        query_atoms = QueryAtoms.model_validate(_sanitize_atoms_payload(dict(atoms or {}), kind="query"))
        return normalize_query_atoms_v02(query_atoms, primary_query=str(query_atoms.query or ""))
    return SkuAtoms.model_validate(_sanitize_atoms_payload(dict(atoms or {}), kind="sku"))


def _write_cached_atoms(
    cache_dir: Path | None,
    key: str,
    *,
    kind: str,
    prompt: list[dict[str, str]],
    response_model: str,
    raw_response: str,
    atoms: QueryAtoms | SkuAtoms,
) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": kind,
        "prompt_version": MEANING_ATOMS_PROMPT_VERSION,
        "prompt": prompt,
        "response_model": response_model,
        "raw_response": raw_response,
        "atoms": atoms.model_dump(mode="json"),
    }
    _cache_path(cache_dir, key).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _system_prompt() -> str:
    return (
        "You extract marketplace SEO meanings into strict JSON for an internal experiment. "
        "Do not score SKU-query pairs. Extract only structured intent/facts. "
        "Use required_atoms for mandatory buyer requirements, preferred_atoms for soft fit, "
        "excluded_atoms for buyer exclusions, and negative_fit_atoms for SKU meanings that should not be targeted. "
        "Return JSON only."
    )


def _query_prompt(payload: Mapping[str, Any]) -> str:
    return (
        "Extract QueryAtoms JSON from this query cluster.\n"
        "Schema keys: product_type, buyer_intent, required_atoms, preferred_atoms, excluded_atoms, "
        "negative_fit_atoms, genericness, confidence, evidence_refs.\n"
        "Atom keys: type, field, value, operator, importance, source, confidence.\n"
        "Hard examples: numeric volume, set quantity, no-print exclusion, car/coffee-machine compatibility, product subtype.\n"
            "Soft examples: cute/aesthetic style, tea/coffee generic use, broad gift occasion without recipient.\n"
            "Recipient is hard only when it is explicit in the top query, not merely present in another cluster example.\n"
            "Do not copy constraints, recipients, colors, quantities, or accessories from source_query_examples into the top query unless they are visible in the top query itself. "
            "Use source_query_examples only as weak context for synonyms and genericness.\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
    )


def _sku_prompt(payload: Mapping[str, Any]) -> str:
    return (
        "Extract SkuAtoms JSON from this SKU evidence pack.\n"
        "Schema keys: product_type, product_identity, facts, positive_atoms, negative_fit_atoms, "
        "confidence, evidence_refs.\n"
        "Facts are explicit product capabilities/attributes. Positive atoms are meanings the SKU fits. "
        "Negative fit atoms are meanings this SKU should not target when evidence says mismatch or absence.\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
    )


def extract_query_atoms(
    cluster_payload: Mapping[str, Any],
    *,
    profile: CategoryProfile | None = None,
    provider: ChatProvider | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
) -> QueryAtoms:
    examples = listify(cluster_payload.get("source_query_examples"))
    query = str(cluster_payload.get("query") or cluster_payload.get("top_query") or (examples[0] if examples else "") or "")
    cluster_key = str(cluster_payload.get("cluster_key") or "")
    cache_key = stable_hash(
        {
            "kind": "query_atoms",
            "prompt_version": MEANING_ATOMS_PROMPT_VERSION,
            "cluster_payload": cluster_payload,
        }
    )
    if not force_refresh:
        cached = _read_cached_atoms(cache_dir, cache_key, kind="query")
        if isinstance(cached, QueryAtoms):
            guarded = apply_query_guards(cached, [query], profile=profile)
            return normalize_query_atoms_v02(guarded, primary_query=query)

    messages = [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(role="user", content=_query_prompt(cluster_payload)),
    ]
    response = _provider_or_default(provider).generate_chat(messages, temperature=0.1, max_tokens=1800)
    atoms = parse_query_atoms_response(response.content, query=query, cluster_key=cluster_key or None)
    atoms = apply_query_guards(atoms, [query], profile=profile)
    atoms = normalize_query_atoms_v02(atoms, primary_query=query)
    _write_cached_atoms(
        cache_dir,
        cache_key,
        kind="query",
        prompt=[message.__dict__ for message in messages],
        response_model=response.model,
        raw_response=response.content,
        atoms=atoms,
    )
    return atoms


def extract_sku_atoms(
    evidence_payload: Mapping[str, Any],
    *,
    meaning_payload: Mapping[str, Any] | None = None,
    profile: CategoryProfile | None = None,
    provider: ChatProvider | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
) -> SkuAtoms:
    project_id = evidence_payload.get("project_id")
    category_id = evidence_payload.get("category_id")
    nm_id = evidence_payload.get("nm_id")
    cache_key = stable_hash(
        {
            "kind": "sku_atoms",
            "prompt_version": MEANING_ATOMS_PROMPT_VERSION,
            "evidence_hash": evidence_payload.get("evidence_hash"),
            "meaning_payload": meaning_payload or {},
        }
    )
    if not force_refresh:
        cached = _read_cached_atoms(cache_dir, cache_key, kind="sku")
        if isinstance(cached, SkuAtoms):
            return apply_sku_guards(cached, evidence=evidence_payload, meaning_payload=meaning_payload, profile=profile)

    prompt_payload = dict(evidence_payload)
    prompt_payload["current_sku_meaning"] = dict(meaning_payload or {})
    messages = [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(role="user", content=_sku_prompt(prompt_payload)),
    ]
    response = _provider_or_default(provider).generate_chat(messages, temperature=0.1, max_tokens=2200)
    atoms = parse_sku_atoms_response(
        response.content,
        project_id=int(project_id) if project_id is not None else None,
        category_id=int(category_id) if category_id is not None else None,
        nm_id=int(nm_id) if nm_id is not None else None,
    )
    atoms = apply_sku_guards(atoms, evidence=evidence_payload, meaning_payload=meaning_payload, profile=profile)
    _write_cached_atoms(
        cache_dir,
        cache_key,
        kind="sku",
        prompt=[message.__dict__ for message in messages],
        response_model=response.model,
        raw_response=response.content,
        atoms=atoms,
    )
    return atoms
