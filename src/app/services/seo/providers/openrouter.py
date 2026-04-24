"""OpenRouter adapter implementing provider interfaces for foundation only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from app import settings
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse, EmbeddingProvider, EmbeddingResponse


@dataclass
class OpenRouterProvider(ChatProvider, EmbeddingProvider):
    """OpenRouter-backed adapter used only via provider interfaces."""

    api_key: str = settings.OPENROUTER_API_KEY
    base_url: str = settings.OPENROUTER_BASE_URL
    chat_model: str = settings.OPENROUTER_CHAT_MODEL
    embedding_model: str = settings.OPENROUTER_EMBEDDING_MODEL
    timeout_seconds: float = 30.0

    def _build_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ecomcore.local",
            "X-Title": "EcomCore SEO Foundation",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=self._build_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("OpenRouter returned a non-object response")
        return data

    def generate_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        data = self._post("/chat/completions", payload)
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        return ChatResponse(model=str(data.get("model") or self.chat_model), content=str(content or ""), raw_response=data)

    def embed_texts(self, texts: Sequence[str]) -> EmbeddingResponse:
        data = self._post("/embeddings", {"model": self.embedding_model, "input": list(texts)})
        embeddings: list[list[float]] = []
        for item in data.get("data") or []:
            if isinstance(item, dict):
                embeddings.append([float(value) for value in (item.get("embedding") or [])])
        return EmbeddingResponse(
            model=str(data.get("model") or self.embedding_model),
            embeddings=embeddings,
            raw_response=data,
        )
