"""OpenAI-compatible HTTP provider implementation."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from research_workspace.application.ports.ai_provider import (
    AIProviderError,
    AISettings,
    PaperAnalysis,
    PaperAnalysisRequest,
    SuggestedIdea,
)


def _endpoint(base_url: str, suffix: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith(suffix):
        return normalized
    return f"{normalized}{suffix}"


def _default_transport(method, url, headers, payload, timeout):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured AI endpoint
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


class OpenAICompatibleProvider:
    def __init__(self, transport=None, timeout_seconds: int = 30) -> None:
        self._transport = transport or _default_transport
        self._timeout = timeout_seconds

    def test_connection(self, settings: AISettings) -> None:
        try:
            self._transport(
                "GET",
                _endpoint(settings.base_url, "/models"),
                {"Authorization": f"Bearer {settings.api_key}"},
                None,
                self._timeout,
            )
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise AIProviderError("authentication_failure", "Authentication failed.") from exc
            if exc.code == 429:
                raise AIProviderError("rate_limit", "The provider rate limit was reached.") from exc
            raise AIProviderError("provider_failure", "The provider rejected the request.") from exc
        except (TimeoutError, URLError) as exc:
            raise AIProviderError("network_failure", "Could not reach the AI provider.") from exc

    def analyze_paper(
        self, settings: AISettings, request: PaperAnalysisRequest
    ) -> PaperAnalysis:
        payload = {
            "model": settings.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return strict JSON with summary, key_claims, and "
                        "suggested_ideas. suggested_ideas items need title and content."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Title: {request.title}\n"
                        f"Authors: {request.authors}\n"
                        f"Year: {request.year}\n"
                        f"Abstract: {request.abstract}\n"
                        f"Research notes: {request.research_notes}"
                    ),
                },
            ],
        }
        try:
            response = self._transport(
                "POST",
                _endpoint(settings.base_url, "/chat/completions"),
                {
                    "Authorization": f"Bearer {settings.api_key}",
                    "Content-Type": "application/json",
                },
                payload,
                self._timeout,
            )
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise AIProviderError("authentication_failure", "Authentication failed.") from exc
            if exc.code == 429:
                raise AIProviderError("rate_limit", "The provider rate limit was reached.") from exc
            raise AIProviderError("provider_failure", "The provider failed to analyze the paper.") from exc
        except (TimeoutError, URLError) as exc:
            raise AIProviderError("network_failure", "Could not reach the AI provider.") from exc
        try:
            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return PaperAnalysis(
                summary=str(parsed["summary"]),
                key_claims=tuple(str(item) for item in parsed["key_claims"]),
                suggested_ideas=tuple(
                    SuggestedIdea(str(item["title"]), str(item["content"]))
                    for item in parsed["suggested_ideas"]
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(
                "invalid_response", "The provider returned an invalid response."
            ) from exc
