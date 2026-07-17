"""Vendor-neutral AI analysis port for the demo slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AISettings:
    provider: str
    base_url: str
    api_key: str = field(repr=False)
    model: str

    def __post_init__(self) -> None:
        if self.provider != "openai_compatible":
            raise ValueError("Unsupported AI provider")
        if not self.base_url.strip():
            raise ValueError("AI base URL is required")
        if not self.api_key.strip():
            raise ValueError("AI API key is required")
        if not self.model.strip():
            raise ValueError("AI model is required")

    @property
    def masked_api_key(self) -> str:
        return f"{'*' * 12}{self.api_key[-4:]}"


@dataclass(frozen=True, slots=True)
class PaperAnalysisRequest:
    title: str
    authors: str
    year: str
    abstract: str
    research_notes: str


@dataclass(frozen=True, slots=True)
class SuggestedIdea:
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class PaperAnalysis:
    summary: str
    key_claims: tuple[str, ...]
    suggested_ideas: tuple[SuggestedIdea, ...]


class AIProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AIProvider(Protocol):
    def test_connection(self, settings: AISettings) -> None: ...

    def analyze_paper(
        self, settings: AISettings, request: PaperAnalysisRequest
    ) -> PaperAnalysis: ...
