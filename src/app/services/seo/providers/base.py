"""Provider interfaces for SEO foundation services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ChatMessage:
    """Minimal provider-agnostic chat message."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatResponse:
    """Provider-agnostic chat completion payload."""

    model: str
    content: str
    raw_response: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResponse:
    """Provider-agnostic embedding payload."""

    model: str
    embeddings: list[list[float]]
    raw_response: Mapping[str, Any] = field(default_factory=dict)


class ChatProvider(ABC):
    """Interface for chat completion providers."""

    @abstractmethod
    def generate_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Generate a chat completion."""


class EmbeddingProvider(ABC):
    """Interface for embedding providers."""

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> EmbeddingResponse:
        """Generate embeddings for the provided texts."""
