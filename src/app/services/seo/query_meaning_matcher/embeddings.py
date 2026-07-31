"""Embedding persistence helpers for meaning-aware matching."""

from __future__ import annotations

import math
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SeoMeaningEmbedding
from app.services.seo.providers.base import EmbeddingProvider, EmbeddingResponse
from app.services.seo.providers.openrouter import OpenRouterProvider
from app.services.seo.query_meaning_matcher.canonical import stable_hash
from app.services.seo.visual_motifs import embedding_markers


class MeaningEmbeddingError(Exception):
    """Raised when embedding generation or persistence fails."""


class LocalPreviewEmbeddingProvider(EmbeddingProvider):
    """Fast deterministic embeddings for internal matcher preview.

    The interactive matcher must not block on hundreds of network calls. This
    provider encodes the same canonical meaning fields into a small semantic
    vector, good enough for preview ranking while persisted provider-backed
    embeddings can be introduced as a separate batch job.

    ``max_mode = "preview"`` means any matcher / generation run that consumes
    this provider cannot be labeled ``full`` — the quality-mode framework
    propagates the ceiling up through :func:`infer_quality_mode`. See
    ``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
    CD-4.
    """

    embedding_model = "local_preview_embedding_v4_visual_motifs"
    #: See ``quality.QualityMode.PREVIEW``. Provider-enforced, not documentation.
    max_mode = "preview"

    _FEATURES: tuple[tuple[str, tuple[str, ...], float], ...] = (
        ("mug", ("^круж", "^чашк", "mug"), 2.0),
        ("backpack", ("^рюкзак", "backpack"), 2.0),
        ("thermo", ("^термо", "thermal"), 2.4),
        ("set", ("набор", "комплект", "set_quantity", " set"), 2.1),
        ("beer", ("^пив", "beer"), 2.0),
        ("tea", ("чай", "чая", "tea"), 1.1),
        ("coffee", ("кофе", "coffee"), 1.1),
        ("ceramic", ("^керами", "ceramic"), 1.3),
        ("glass", ("^стекл", "glass"), 1.3),
        ("porcelain", ("^фарфор", "porcelain"), 1.3),
        ("cute", ("милая", "милый", "милые", "милую", "милого", "милота", "^милаш", "cute"), 2.0),
        ("cozy", ("^уют", "cozy"), 1.8),
        ("aesthetic", ("^эстет", "^красив", "пинтерест", "pinterest"), 2.0),
        ("visual_motif", embedding_markers(), 2.2),
        ("gift", ("^подар", "день рождения", "новый год", "^любим", "^подруг"), 1.2),
        ("female", ("^женск", "^девуш", "^любим", "^подруг"), 1.2),
        ("male", ("^мужск", "^парн", "^мальчик"), 1.2),
        ("school", ("^школ", "^учеб"), 1.4),
        ("travel", ("^путешеств", "^поезд"), 1.4),
        ("laptop", ("^ноутбук",), 1.4),
    )

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingResponse:
        return EmbeddingResponse(
            model=self.embedding_model,
            embeddings=[self._vector(text) for text in texts],
            raw_response={"provider": self.embedding_model},
        )

    def _vector(self, text: str) -> list[float]:
        normalized = str(text or "").lower().replace("ё", "е")
        tokens = [
            "".join(ch for ch in token if ch.isalnum() or ch in {":", "_"})
            for token in normalized.replace("\n", " ").replace(",", " ").split()
        ]
        tokens = [token for token in tokens if token]
        vector = [0.0] * 64
        for index, (_, markers, weight) in enumerate(self._FEATURES):
            if any(self._matches_marker(marker, normalized, tokens) for marker in markers):
                vector[index] = float(weight)

        for token in tokens:
            if len(token) < 3:
                continue
            bucket = 16 + (sum(ord(ch) for ch in token) % 48)
            vector[bucket] += 0.25
        return vector

    def _matches_marker(self, marker: str, normalized: str, tokens: Sequence[str]) -> bool:
        if marker.startswith("^"):
            prefix = marker[1:]
            return any(token.startswith(prefix) for token in tokens)
        if " " in marker or ":" in marker or "_" in marker:
            return marker in normalized
        return marker in tokens


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def ensure_meaning_embedding(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    entity_type: str,
    entity_id: int,
    canonical_text: str,
    provider: EmbeddingProvider | None = None,
) -> SeoMeaningEmbedding:
    resolved_provider = provider or OpenRouterProvider()
    model = str(getattr(resolved_provider, "embedding_model", None) or "unknown_embedding_model")
    input_hash = stable_hash({"model": model, "canonical_text": canonical_text})

    row = session.scalars(
        select(SeoMeaningEmbedding).where(
            SeoMeaningEmbedding.entity_type == str(entity_type),
            SeoMeaningEmbedding.entity_id == int(entity_id),
            SeoMeaningEmbedding.model == model,
            SeoMeaningEmbedding.input_hash == input_hash,
        )
    ).first()
    if row is not None:
        return row

    try:
        response = resolved_provider.embed_texts([canonical_text])
    except Exception as exc:
        raise MeaningEmbeddingError(f"Embedding generation failed: {exc}") from exc
    if not response.embeddings or not response.embeddings[0]:
        raise MeaningEmbeddingError("Embedding provider returned an empty vector")

    row = SeoMeaningEmbedding(
        project_id=int(project_id),
        category_id=int(category_id),
        entity_type=str(entity_type),
        entity_id=int(entity_id),
        model=str(response.model or model),
        input_hash=input_hash,
        embedding=[float(value) for value in response.embeddings[0]],
        canonical_text=canonical_text,
    )
    session.add(row)
    session.flush()
    return row
