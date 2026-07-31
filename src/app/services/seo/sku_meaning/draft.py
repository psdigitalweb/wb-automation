"""LLM draft generation for SKU meanings."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import settings
from app.schemas.seo_sku_meaning import SkuMeaningDraftResponse, SkuMeaningEvidencePack, SkuMeaningPayload
from app.services.seo.providers.base import ChatMessage, ChatProvider
from app.services.seo.providers.openrouter import OpenRouterProvider


SKU_MEANING_PROMPT_VERSION = "sku_meaning_preview_v0"

_MODEL_SAFE_RE = re.compile(r"[^0-9a-zA-Z_.-]+")


class SkuMeaningDraftError(Exception):
    """Raised when LLM draft generation fails."""


@dataclass(frozen=True)
class SkuMeaningDraftCacheKey:
    project_id: int
    category_id: int
    nm_id: int
    model: str
    prompt_version: str
    evidence_hash: str


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sanitize_model_id(model_id: str) -> str:
    value = str(model_id or "").strip().replace("/", "__").replace(":", "_")
    value = _MODEL_SAFE_RE.sub("_", value)
    return value or "unknown_model"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class SkuMeaningDraftStore:
    """File-based cache for raw SKU meaning LLM artifacts."""

    def __init__(self, *, root_dir: str | Path | None = None) -> None:
        self._root_dir = Path(root_dir) if root_dir is not None else self._default_root_dir()

    @staticmethod
    def _default_root_dir() -> Path:
        override = os.getenv("SEO_SKU_MEANING_CACHE_DIR", "").strip()
        if override:
            return Path(override)
        return Path(settings.INTERNAL_DATA_DIR) / "seo_sku_meaning_cache"

    def artifact_dir(self, key: SkuMeaningDraftCacheKey) -> Path:
        model_dir = _sanitize_model_id(key.model)[:48]
        prompt_dir = re.sub(r"[^0-9a-zA-Z_.-]+", "_", key.prompt_version)[:32]
        hash_dir = str(key.evidence_hash)[:32]
        return (
            self._root_dir
            / "sku_draft"
            / f"p{int(key.project_id)}"
            / f"c{int(key.category_id)}"
            / f"nm{int(key.nm_id)}"
            / f"m_{model_dir}"
            / f"pv_{prompt_dir}"
            / f"h_{hash_dir}"
        )

    def get(self, key: SkuMeaningDraftCacheKey) -> dict[str, Any] | None:
        artifact_dir = self.artifact_dir(key)
        meta_path = artifact_dir / "meta.json"
        parsed_path = artifact_dir / "parsed.json"
        if not meta_path.exists() or not parsed_path.exists():
            return None
        meta = _read_json(meta_path)
        parsed = _read_json(parsed_path)
        raw_path = artifact_dir / "raw_response.json"
        raw_response = _read_json(raw_path) if raw_path.exists() else None
        return {
            "artifact_dir": str(artifact_dir),
            "meta": meta if isinstance(meta, dict) else {},
            "parsed": parsed if isinstance(parsed, dict) else {},
            "raw_response": raw_response,
        }

    def put(
        self,
        key: SkuMeaningDraftCacheKey,
        *,
        prompt: str,
        raw_response: dict[str, Any],
        parsed: dict[str, Any],
    ) -> str:
        artifact_dir = self.artifact_dir(key)
        meta = {
            "schema_version": "v0",
            "entity": "sku_meaning_draft",
            "created_at": _utc_now_iso(),
            "key": {
                "project_id": int(key.project_id),
                "category_id": int(key.category_id),
                "nm_id": int(key.nm_id),
                "model": key.model,
                "prompt_version": key.prompt_version,
                "evidence_hash": key.evidence_hash,
            },
        }
        _write_json(artifact_dir / "meta.json", meta)
        _write_json(artifact_dir / "prompt.json", {"messages": [{"role": "user", "content": prompt}]})
        _write_json(artifact_dir / "raw_response.json", raw_response)
        _write_json(artifact_dir / "parsed.json", parsed)
        return str(artifact_dir)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        raise SkuMeaningDraftError("LLM returned empty content")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.strip().startswith("{"):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first >= 0 and last > first:
            candidate = candidate[first : last + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise SkuMeaningDraftError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SkuMeaningDraftError("LLM JSON payload must be an object")
    return payload


def normalize_sku_meaning_payload(payload: dict[str, Any]) -> SkuMeaningPayload:
    """Normalize partially valid LLM JSON into SKU Meaning Schema v0."""

    status = str(payload.get("review_status") or payload.get("status") or "draft").strip()
    if status not in {"draft", "verified", "needs_more_data", "rejected"}:
        status = "draft"

    def _list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text_value = str(value).strip()
        return [text_value] if text_value else []

    confidence_raw = payload.get("confidence")
    confidence: dict[str, float] = {}
    if isinstance(confidence_raw, dict):
        for key, value in confidence_raw.items():
            try:
                numeric = float(value)
            except Exception:
                continue
            confidence[str(key)] = max(0.0, min(1.0, numeric))

    return SkuMeaningPayload(
        functional=payload.get("functional") if isinstance(payload.get("functional"), dict) else {},
        expressive=payload.get("expressive") if isinstance(payload.get("expressive"), dict) else {},
        audience=_list(payload.get("audience")),
        negative_constraints=_list(payload.get("negative_constraints")),
        confidence=confidence,
        evidence_refs=_list(payload.get("evidence_refs")),
        review_status=status,  # type: ignore[arg-type]
    )


def _prompt_for_evidence(evidence_pack: SkuMeaningEvidencePack) -> str:
    evidence = evidence_pack.model_dump(mode="json")
    # Keep raw reviews bounded in prompt while preserving refs.
    evidence["reviews"] = [
        {
            **item,
            "text": str(item.get("text") or "")[:900],
        }
        for item in evidence.get("reviews", [])[:20]
    ]
    return (
        "You are building an internal SEO annotation draft for a Wildberries SKU.\n"
        "Return ONLY valid JSON matching SKU Meaning Schema v0. Do not include markdown.\n\n"
        "Schema:\n"
        "{\n"
        '  "schema_version": "sku_meaning_v0",\n'
        '  "functional": {"product_type": "...", "use_cases": [], "attributes": []},\n'
        '  "expressive": {"styles": [], "vibes": [], "emotions": [], "gift_contexts": []},\n'
        '  "audience": [],\n'
        '  "negative_constraints": [],\n'
        '  "confidence": {"functional": 0.0, "expressive": 0.0, "audience": 0.0},\n'
        '  "evidence_refs": [],\n'
        '  "review_status": "draft"\n'
        "}\n\n"
        "Rules:\n"
        "- Use only evidence from the pack. If you infer, include an evidence ref plus a cautious confidence.\n"
        "- Include negative_constraints for broad or misleading search meanings this SKU should not target.\n"
        "- If evidence is thin, use review_status=needs_more_data and low confidence.\n"
        "- Never set review_status=verified; only a human can verify.\n\n"
        "Evidence pack JSON:\n"
        f"{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}"
    )


def generate_sku_meaning_draft(
    evidence_pack: SkuMeaningEvidencePack,
    *,
    provider: ChatProvider | None = None,
    store: SkuMeaningDraftStore | None = None,
    force_refresh: bool = False,
) -> SkuMeaningDraftResponse:
    """Generate or load a cached LLM draft for one SKU evidence pack."""

    resolved_provider = provider or OpenRouterProvider()
    model = getattr(resolved_provider, "chat_model", None) or "unknown_model"
    prompt_version = SKU_MEANING_PROMPT_VERSION
    key = SkuMeaningDraftCacheKey(
        project_id=evidence_pack.project_id,
        category_id=evidence_pack.category_id,
        nm_id=evidence_pack.nm_id,
        model=str(model),
        prompt_version=prompt_version,
        evidence_hash=evidence_pack.evidence_hash,
    )
    resolved_store = store or SkuMeaningDraftStore()
    cached = None if force_refresh else resolved_store.get(key)
    if cached is not None:
        meaning = normalize_sku_meaning_payload(cached.get("parsed") or {})
        raw_response = cached.get("raw_response")
        raw_preview = None
        if isinstance(raw_response, dict):
            raw_preview = json.dumps(raw_response, ensure_ascii=False)[:500]
        return SkuMeaningDraftResponse(
            meaning=meaning,
            evidence_hash=evidence_pack.evidence_hash,
            cached=True,
            model=str(model),
            prompt_version=prompt_version,
            artifact_path=str(cached.get("artifact_dir") or ""),
            raw_response_preview=raw_preview,
        )

    prompt = _prompt_for_evidence(evidence_pack)
    try:
        response = resolved_provider.generate_chat(
            [ChatMessage(role="user", content=prompt)],
            temperature=0.1,
            max_tokens=1600,
        )
    except Exception as exc:
        raise SkuMeaningDraftError(f"LLM draft generation failed: {exc}") from exc

    parsed = _extract_json_object(response.content)
    meaning = normalize_sku_meaning_payload(parsed)
    raw_response = dict(response.raw_response or {})
    if not raw_response:
        raw_response = {"model": response.model, "content": response.content}
    artifact_path = resolved_store.put(
        key,
        prompt=prompt,
        raw_response=raw_response,
        parsed=meaning.model_dump(mode="json"),
    )
    return SkuMeaningDraftResponse(
        meaning=meaning,
        evidence_hash=evidence_pack.evidence_hash,
        cached=False,
        model=str(response.model or model),
        prompt_version=prompt_version,
        artifact_path=artifact_path,
        raw_response_preview=response.content[:500],
    )
