"""Application service for paper analysis through a vendor-neutral provider."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from research_workspace.application.ports.ai_provider import (
    AIProvider,
    AIProviderError,
    AISettings,
    PaperAnalysis,
    PaperAnalysisRequest,
)


def _validate_analysis(value) -> PaperAnalysis:
    if not isinstance(value, PaperAnalysis):
        raise AIProviderError("invalid_response", "The provider returned an invalid response.")
    if not value.summary.strip():
        raise AIProviderError("invalid_response", "The provider returned an empty summary.")
    if not value.key_claims:
        raise AIProviderError("invalid_response", "The provider returned no key claims.")
    if not value.suggested_ideas:
        raise AIProviderError("invalid_response", "The provider returned no suggested ideas.")
    for idea in value.suggested_ideas:
        if not idea.title.strip() or not idea.content.strip():
            raise AIProviderError(
                "invalid_response", "The provider returned an invalid suggested idea."
            )
    return value


class PaperAIAnalysisService:
    def __init__(
        self,
        settings_loader: Callable[[], AISettings | None],
        provider: AIProvider,
    ) -> None:
        self._settings_loader = settings_loader
        self._provider = provider

    def is_configured(self) -> bool:
        try:
            return self._settings_loader() is not None
        except Exception:
            return False

    def analyze(self, request: PaperAnalysisRequest) -> PaperAnalysis:
        settings = self._settings_loader()
        if settings is None:
            raise AIProviderError("settings_missing", "AI is not configured.")
        return _validate_analysis(self._provider.analyze_paper(settings, request))

    def test_connection(self, settings: AISettings) -> None:
        self._provider.test_connection(settings)


@dataclass(slots=True)
class AIAsyncHandle:
    future: Future

    @property
    def done(self) -> bool:
        return self.future.done()

    @property
    def result(self):
        if not self.future.done():
            return None
        return self.future.result()

    @property
    def error(self):
        if not self.future.done():
            return None
        try:
            self.future.result()
        except AIProviderError as exc:
            return exc
        except Exception:
            return AIProviderError("provider_failure", "AI analysis failed.")
        return None

    def cancel(self) -> None:
        self.future.cancel()


class ThreadedPaperAIAnalysisService:
    def __init__(
        self,
        service: PaperAIAnalysisService,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._service = service
        self._executor = executor or ThreadPoolExecutor(max_workers=1)

    def is_configured(self) -> bool:
        return self._service.is_configured()

    def analyze_async(self, request: PaperAnalysisRequest) -> AIAsyncHandle:
        return AIAsyncHandle(self._executor.submit(self._service.analyze, request))

    def test_async(self, settings: AISettings) -> AIAsyncHandle:
        return AIAsyncHandle(self._executor.submit(self._service.test_connection, settings))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
