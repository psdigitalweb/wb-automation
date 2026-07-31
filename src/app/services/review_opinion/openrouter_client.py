"""OpenRouter client with strict Structured Outputs and bounded retries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app import settings
from app.services.seo.providers.http_client import build_openrouter_http_client

from .contracts import review_opinion_json_schema
from .prompt import SYSTEM_PROMPT, build_user_prompt


@dataclass(frozen=True)
class OpenRouterOpinionResponse:
    model: str
    content: Any
    raw_output_text: str
    usage: dict[str, Any]
    provider_request_id: str | None


class OpenRouterOpinionClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.model = str(model or settings.OPENROUTER_REVIEW_MODEL).strip()
        self.reasoning_effort = str(
            reasoning_effort or settings.OPENROUTER_REVIEW_REASONING_EFFORT
        ).strip()
        self.timeout_seconds = int(timeout_seconds or settings.OPENROUTER_REVIEW_TIMEOUT_SECONDS)
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured")
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("invalid review reasoning effort")

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ecomcore.ru",
            "X-Title": "EcomCore Customer Opinion",
        }

    def _payload(self, input_payload: dict[str, Any], *, retry_errors: list[str] | None) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(input_payload, retry_errors=retry_errors),
                },
            ],
            "reasoning": {"effort": self.reasoning_effort},
            "max_completion_tokens": 5000,
            "stream": False,
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "wb_customer_opinion",
                    "strict": True,
                    "schema": review_opinion_json_schema(),
                },
            },
        }

    def generate(
        self,
        input_payload: dict[str, Any],
        *,
        retry_errors: list[str] | None = None,
    ) -> OpenRouterOpinionResponse:
        url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
        payload = self._payload(input_payload, retry_errors=retry_errors)
        last_error: Exception | None = None

        with build_openrouter_http_client(timeout_seconds=float(self.timeout_seconds)) as client:
            for attempt in range(3):
                try:
                    response = client.post(url, headers=self._headers(), json=payload)
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            time.sleep(1.5 * (2**attempt))
                            continue
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("OpenRouter returned a non-object response")
                    choices = data.get("choices") or []
                    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
                    if not isinstance(message, dict):
                        raise ValueError("OpenRouter response has no assistant message")
                    content = message.get("content")
                    raw_output = content if isinstance(content, str) else ""
                    return OpenRouterOpinionResponse(
                        model=str(data.get("model") or self.model),
                        content=content,
                        raw_output_text=raw_output,
                        usage=dict(data.get("usage") or {}),
                        provider_request_id=(
                            response.headers.get("x-request-id")
                            or str(data.get("id") or "")
                            or None
                        ),
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(1.5 * (2**attempt))
                        continue
                    break

        error_name = type(last_error).__name__ if last_error is not None else "UnknownError"
        raise RuntimeError(f"openrouter_request_failed:{error_name}")
