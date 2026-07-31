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
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Generate a chat completion."""


class EmbeddingProvider(ABC):
    """Interface for embedding providers.

    Providers declare a ``max_mode`` ceiling (see
    ``services/seo/quality.py::QualityMode``) that propagates into any
    matcher / pipeline layer that consumes them. The default is ``FULL``;
    preview-style deterministic providers override it to ``PREVIEW`` so
    that no run that used them can be labeled ``full``.

    The attribute is typed as ``str`` at the class level so this module does
    not need to import ``quality`` (which would introduce a cycle via
    ``models`` -> ``quality`` in some call paths). Consumers coerce the value
    back into a ``QualityMode`` when they build their ``QualityState``.
    """

    #: Hard ceiling on the quality mode of any run that uses this provider.
    #: Must be one of the string values of ``quality.QualityMode``.
    max_mode: str = "full"

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> EmbeddingResponse:
        """Generate embeddings for the provided texts."""
