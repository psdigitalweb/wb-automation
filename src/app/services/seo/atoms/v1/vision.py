"""Vision extraction for the meaning atoms shadow experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx

from app import settings
from app.services.seo.atoms.v1.guards import append_atom_unique
from app.services.seo.atoms.v1.llm_extractors import (
    MeaningAtomsExtractionError,
    _extract_json_object,
    _sanitize_atoms_payload,
)
from app.services.seo.atoms.v1.schemas import MeaningAtom, SkuAtoms
from app.services.seo.query_meaning_matcher.canonical import stable_hash


VISION_PROMPT_VERSION = "ai_vision_visual_prompt_v1"
VISION_PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[6] / "config" / "seo" / "prompts" / "AI_VISION_VISUAL_PROMPT_V1.txt"


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _read_prompt_template() -> str:
    return VISION_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _render_prompt_template(template: str, values: Mapping[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def image_urls_from_evidence(evidence_payload: Mapping[str, Any], *, limit: int = 1) -> list[str]:
    product = evidence_payload.get("product") if isinstance(evidence_payload.get("product"), Mapping) else {}
    pics = product.get("pics") if isinstance(product, Mapping) else None
    urls: list[str] = []
    if isinstance(pics, list):
        for item in pics:
            if isinstance(item, Mapping):
                url = item.get("big") or item.get("c516x688") or item.get("hq") or item.get("square")
            else:
                url = item
            if isinstance(url, str) and url.startswith("http"):
                urls.append(url)
            if len(urls) >= max(1, int(limit)):
                break
    elif isinstance(pics, str) and pics.startswith("http"):
        urls.append(pics)
    return urls


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _read_cache(cache_dir: Path | None, key: str) -> SkuAtoms | None:
    if cache_dir is None:
        return None
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    atoms = payload.get("atoms") if isinstance(payload, dict) else {}
    parsed = SkuAtoms.model_validate(_sanitize_atoms_payload(dict(atoms or {}), kind="sku"))
    has_useful_atoms = any(atom.value is not None for atom in [*parsed.facts, *parsed.positive_atoms, *parsed.negative_fit_atoms])
    raw_response = payload.get("raw_response") if isinstance(payload, dict) else None
    if not has_useful_atoms and raw_response:
        try:
            return parse_vision_sku_atoms_response(str(raw_response or ""))
        except Exception:
            return parsed
    return parsed


def _write_cache(
    cache_dir: Path | None,
    key: str,
    *,
    model: str,
    image_urls: Sequence[str],
    prompt: str,
    raw_response: str,
    atoms: SkuAtoms,
) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "sku_vision_atoms",
        "prompt_version": VISION_PROMPT_VERSION,
        "model": model,
        "image_urls": list(image_urls),
        "prompt": prompt,
        "raw_response": raw_response,
        "atoms": atoms.model_dump(mode="json"),
    }
    _cache_path(cache_dir, key).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def render_vision_prompt(evidence_payload: Mapping[str, Any]) -> str:
    product = evidence_payload.get("product") if isinstance(evidence_payload.get("product"), Mapping) else {}
    category_name = _string_value(product.get("subject_name") if isinstance(product, Mapping) else "")
    if not category_name:
        category_name = _string_value(evidence_payload.get("category_name") or evidence_payload.get("category_id"))
    return _render_prompt_template(
        _read_prompt_template(),
        {
            "category_name": category_name,
            "title": _string_value(product.get("title") if isinstance(product, Mapping) else ""),
            "description": _string_value(product.get("description") if isinstance(product, Mapping) else ""),
        },
    )


def _prompt(evidence_payload: Mapping[str, Any]) -> str:
    return render_vision_prompt(evidence_payload)


def _atom_from_pair(key: str, value: Any, *, positive: bool) -> dict[str, Any]:
    key_norm = str(key or "").strip().lower()
    if key_norm in {"print", "has_print"}:
        return {"type": "visual", "field": "design", "value": "print", "source": "vision", "confidence": 0.8}
    if key_norm in {"design"}:
        return {"type": "visual", "field": "design", "value": value, "source": "vision", "confidence": 0.8}
    if key_norm in {"motif", "pattern", "illustration"}:
        return {"type": "visual", "field": "motif", "value": value, "source": "vision", "confidence": 0.8}
    if key_norm in {"color", "colour"}:
        return {"type": "attribute", "field": "color", "value": value, "source": "vision", "confidence": 0.8}
    if key_norm in {"transparent", "transparency", "visual"}:
        return {"type": "visual", "field": "visual", "value": value or "transparent", "source": "vision", "confidence": 0.8}
    if key_norm in {"packaging", "package", "gift_box"}:
        return {"type": "attribute", "field": "packaging", "value": value, "source": "vision", "confidence": 0.75}
    if key_norm in {"ocr", "ocr_text", "text", "visible_text"}:
        return {"type": "visual", "field": "ocr_text", "value": value, "source": "vision", "confidence": 0.75}
    if key_norm in {"audience", "recipient", "recipient_fit", "audience_hypotheses"}:
        return {"type": "recipient", "field": "recipient", "value": value, "source": "vision_audience", "confidence": 0.65}
    if key_norm in {"occasion", "occasion_fit", "occasion_hypotheses"}:
        return {"type": "occasion", "field": "occasion", "value": value, "source": "vision_audience", "confidence": 0.65}
    if key_norm in {"query_intent", "supported_query_intents", "supported_intent"}:
        return {"type": "use_case", "field": "query_intent", "value": value, "source": "vision_audience", "confidence": 0.55}
    if key_norm in {"negative", "negative_query_intents", "negative_intent"}:
        return {"type": "attribute", "field": "negative", "value": value, "source": "vision_audience", "confidence": 0.7}
    if key_norm in {"feature", "lid", "saucer"}:
        field = "feature"
        atom_value = key_norm if key_norm in {"lid", "saucer"} else value
        return {"type": "attribute", "field": field, "value": atom_value, "source": "vision", "confidence": 0.75}
    if key_norm in {"shape", "form"}:
        return {"type": "attribute", "field": "shape", "value": value, "source": "vision", "confidence": 0.7}
    if positive or key_norm in {"expressive", "style", "vibe", "aesthetic"}:
        return {"type": "expressive", "field": "expressive", "value": value, "source": "vision", "confidence": 0.75}
    return {"type": "attribute", "field": key_norm or "visual", "value": value, "source": "vision", "confidence": 0.6}


def _coerce_atom_list(raw: Any, *, positive: bool = False) -> list[Any]:
    if isinstance(raw, list):
        items: list[Any] = []
        for item in raw:
            if isinstance(item, Mapping) and "type" not in item and "value" not in item:
                for key, value in item.items():
                    items.append(_atom_from_pair(str(key), value, positive=positive))
            else:
                items.append(item)
        return items
    if isinstance(raw, Mapping):
        items: list[Any] = []
        for key, value in raw.items():
            if isinstance(value, list):
                for item in value:
                    items.append(_atom_from_pair(str(key), item, positive=positive))
            else:
                items.append(_atom_from_pair(str(key), value, positive=positive))
        return items
    return []


def _coerce_named_atoms(raw: Any, *, atom_type: str, field: str, source: str = "vision_audience", confidence: float = 0.6) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if raw is None:
        return result
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        value: Any = item
        item_confidence = confidence
        if isinstance(item, Mapping):
            value = item.get("value") or item.get("label") or item.get("text") or item.get("intent") or item.get("audience")
            try:
                item_confidence = float(item.get("confidence", confidence))
            except Exception:
                item_confidence = confidence
        if value in (None, "", []):
            continue
        result.append(
            {
                "type": atom_type,
                "field": field,
                "value": value,
                "importance": "soft",
                "source": source,
                "confidence": max(0.0, min(1.0, item_confidence)),
            }
        )
    return result


def _visual_schema_atoms(raw: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []

    product_type = raw.get("visible_product_type")
    if isinstance(product_type, Mapping) and product_type.get("value"):
        facts.append(
            {
                "type": "visual",
                "field": "product_type",
                "value": product_type.get("value"),
                "importance": "soft",
                "source": "vision_audience",
                "confidence": product_type.get("confidence", 0.8),
            }
        )
    for item in _coerce_named_atoms(raw.get("colors"), atom_type="attribute", field="color", source="vision_audience", confidence=0.75):
        facts.append(item)
    for item in _coerce_named_atoms(raw.get("visible_design"), atom_type="visual", field="design", source="vision_audience", confidence=0.75):
        facts.append(item)
    for item in _coerce_named_atoms(raw.get("visible_text"), atom_type="visual", field="ocr_text", source="vision_audience", confidence=0.75):
        facts.append(item)
    for item in _coerce_named_atoms(raw.get("visual_style"), atom_type="expressive", field="expressive", source="vision_audience", confidence=0.65):
        positives.append(item)
    audience = raw.get("visual_audience")
    if isinstance(audience, list):
        for item in audience:
            if not isinstance(item, Mapping):
                continue
            group = item.get("group")
            if not group:
                continue
            positives.append(
                {
                    "type": "recipient",
                    "field": "recipient",
                    "value": group,
                    "importance": "soft",
                    "source": "vision_audience",
                    "confidence": item.get("confidence", 0.6),
                }
            )
    audience_fit = raw.get("audience_fit")
    if isinstance(audience_fit, list):
        for item in audience_fit:
            if not isinstance(item, Mapping):
                continue
            audience_name = item.get("audience")
            if not audience_name:
                continue
            fit = str(item.get("fit") or "").strip().lower()
            atom = {
                "type": "recipient",
                "field": "recipient",
                "value": audience_name,
                "importance": "soft",
                "source": str(item.get("evidence_type") or "vision_audience"),
                "confidence": item.get("confidence", 0.55),
            }
            if fit in {"high", "medium"}:
                positives.append(atom)
            elif fit in {"low", "not_supported"}:
                negatives.append(atom)
    return facts, positives, negatives


def parse_vision_sku_atoms_response(
    content: str,
    *,
    project_id: int | None = None,
    category_id: int | None = None,
    nm_id: int | None = None,
) -> SkuAtoms:
    raw = _extract_json_object(content)
    for wrapper_key in ("SkuAtoms", "sku_atoms", "skuAtoms"):
        wrapped = raw.get(wrapper_key)
        if isinstance(wrapped, Mapping):
            raw = dict(wrapped)
            break
    visual_facts, visual_positives, visual_negatives = _visual_schema_atoms(raw)
    facts = _coerce_atom_list(raw.get("facts"), positive=False)
    facts.extend(visual_facts)
    facts.extend(_coerce_atom_list(raw.get("visual_facts"), positive=False))
    facts.extend(_coerce_named_atoms(raw.get("ocr_text"), atom_type="visual", field="ocr_text", confidence=0.75))
    positives = _coerce_atom_list(raw.get("positive_atoms"), positive=True)
    positives.extend(visual_positives)
    positives.extend(_coerce_named_atoms(raw.get("audience_hypotheses"), atom_type="recipient", field="recipient", confidence=0.6))
    positives.extend(_coerce_named_atoms(raw.get("recipient_fit"), atom_type="recipient", field="recipient", confidence=0.65))
    positives.extend(_coerce_named_atoms(raw.get("occasion_hypotheses"), atom_type="occasion", field="occasion", confidence=0.6))
    positives.extend(_coerce_named_atoms(raw.get("occasion_fit"), atom_type="occasion", field="occasion", confidence=0.65))
    positives.extend(_coerce_named_atoms(raw.get("style_archetypes"), atom_type="expressive", field="expressive", confidence=0.65))
    positives.extend(_coerce_named_atoms(raw.get("supported_query_intents"), atom_type="use_case", field="query_intent", confidence=0.55))
    negatives = _coerce_atom_list(raw.get("negative_fit_atoms"), positive=False)
    negatives.extend(visual_negatives)
    negatives.extend(_coerce_named_atoms(raw.get("negative_query_intents"), atom_type="attribute", field="negative", confidence=0.7))
    raw["facts"] = facts
    raw["positive_atoms"] = positives
    raw["negative_fit_atoms"] = negatives
    data = _sanitize_atoms_payload(raw, kind="sku")
    if project_id is not None:
        data["project_id"] = int(project_id)
    if category_id is not None:
        data["category_id"] = int(category_id)
    if nm_id is not None:
        data["nm_id"] = int(nm_id)
    try:
        return SkuAtoms.model_validate(data)
    except Exception as exc:
        raise MeaningAtomsExtractionError(f"Invalid vision SKU atoms JSON: {exc}") from exc


def extract_vision_sku_atoms(
    evidence_payload: Mapping[str, Any],
    *,
    image_limit: int = 1,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    model: str = "openai/gpt-4o",
    timeout_seconds: float = 60.0,
) -> SkuAtoms:
    project_id = evidence_payload.get("project_id")
    category_id = evidence_payload.get("category_id")
    nm_id = evidence_payload.get("nm_id")
    image_urls = image_urls_from_evidence(evidence_payload, limit=image_limit)
    empty = SkuAtoms(
        project_id=int(project_id) if project_id is not None else None,
        category_id=int(category_id) if category_id is not None else None,
        nm_id=int(nm_id) if nm_id is not None else None,
        product_type="",
        product_identity="vision_unavailable",
    )
    if not image_urls:
        return empty
    prompt = _prompt(evidence_payload)
    cache_key = stable_hash(
        {
            "kind": "sku_vision_atoms",
            "prompt_version": VISION_PROMPT_VERSION,
            "model": model,
            "evidence_hash": evidence_payload.get("evidence_hash"),
            "image_urls": image_urls,
        }
    )
    if not force_refresh:
        cached = _read_cache(cache_dir, cache_key)
        if cached is not None:
            return cached
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not configured")
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
        "max_tokens": 1800,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ecomcore.local",
        "X-Title": "EcomCore SEO Vision Experiment",
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    raw_content = message.get("content") if isinstance(message, dict) else ""
    atoms = parse_vision_sku_atoms_response(
        str(raw_content or ""),
        project_id=int(project_id) if project_id is not None else None,
        category_id=int(category_id) if category_id is not None else None,
        nm_id=int(nm_id) if nm_id is not None else None,
    )
    _write_cache(cache_dir, cache_key, model=str(data.get("model") or model), image_urls=image_urls, prompt=prompt, raw_response=str(raw_content or ""), atoms=atoms)
    return atoms


def merge_sku_atoms_with_vision(base: SkuAtoms, vision: SkuAtoms) -> SkuAtoms:
    result = base.model_copy(deep=True)
    for atom in vision.facts:
        data = atom.model_dump(mode="json")
        data["source"] = f"{data.get('source') or 'vision'}:vision"
        append_atom_unique(result.facts, MeaningAtom.model_validate(data))
    for atom in vision.positive_atoms:
        data = atom.model_dump(mode="json")
        data["source"] = f"{data.get('source') or 'vision'}:vision"
        append_atom_unique(result.positive_atoms, MeaningAtom.model_validate(data))
    for atom in vision.negative_fit_atoms:
        data = atom.model_dump(mode="json")
        data["source"] = f"{data.get('source') or 'vision'}:vision"
        append_atom_unique(result.negative_fit_atoms, MeaningAtom.model_validate(data))
    return result
