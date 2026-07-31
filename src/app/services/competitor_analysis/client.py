"""Single-attempt OpenRouter Structured Outputs client for competitor analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app import settings
from app.services.seo.providers.http_client import build_openrouter_http_client


@dataclass(frozen=True)
class StructuredResponse:
    model: str
    content: Any
    usage: dict[str, Any]
    provider_request_id: str | None


class StructuredOpenRouterClient:
    def __init__(
        self,
        *,
        model: str,
        reasoning_effort: str,
        timeout_seconds: int | None = None,
    ) -> None:
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = int(
            timeout_seconds or settings.OPENROUTER_REVIEW_TIMEOUT_SECONDS
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ecomcore.ru",
            "X-Title": "EcomCore Competitor Review Analysis",
        }

    def generate(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
        max_completion_tokens: int,
    ) -> StructuredResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": __import__("json").dumps(
                        user_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "reasoning": {"effort": self.reasoning_effort},
            "max_completion_tokens": int(max_completion_tokens),
            "stream": False,
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
        last_error: Exception | None = None
        with build_openrouter_http_client(
            timeout_seconds=float(self.timeout_seconds)
        ) as client:
            for attempt in range(2):
                try:
                    response = client.post(url, headers=self._headers(), json=payload)
                    if (response.status_code == 429 or response.status_code >= 500) and attempt == 0:
                        time.sleep(1.5)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    choices = data.get("choices") if isinstance(data, dict) else None
                    message = (
                        choices[0].get("message")
                        if isinstance(choices, list) and choices and isinstance(choices[0], dict)
                        else None
                    )
                    if not isinstance(message, dict):
                        raise ValueError("OpenRouter response has no assistant message")
                    return StructuredResponse(
                        model=str(data.get("model") or self.model),
                        content=message.get("content"),
                        usage=dict(data.get("usage") or {}),
                        provider_request_id=(
                            response.headers.get("x-request-id")
                            or str(data.get("id") or "")
                            or None
                        ),
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt == 0:
                        continue
        raise RuntimeError(
            f"openrouter_request_failed:{type(last_error).__name__ if last_error else 'UnknownError'}"
        )
