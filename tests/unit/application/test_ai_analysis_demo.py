from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest


def test_ai_settings_persist_without_leaking_key_in_masked_view(tmp_path):
    from research_workspace.application.ports.ai_provider import AISettings
    from research_workspace.infrastructure.config.ai_settings_store import (
        JsonAISettingsStore,
    )

    store = JsonAISettingsStore(tmp_path / "ai-settings.json")
    settings = AISettings(
        provider="openai_compatible",
        base_url="https://example.test/v1",
        api_key="sk-secret-demo",
        model="demo-model",
    )

    store.save(settings)

    loaded = store.load()
    assert loaded == settings
    assert loaded.masked_api_key == "************demo"
    assert "sk-secret-demo" not in repr(loaded)


def test_paper_analysis_service_validates_structured_response():
    from research_workspace.application.ports.ai_provider import (
        AISettings,
        PaperAnalysis,
        PaperAnalysisRequest,
        SuggestedIdea,
    )
    from research_workspace.application.services.paper_ai_analysis import (
        PaperAIAnalysisService,
    )

    class Provider:
        def analyze_paper(self, settings, request):
            assert settings.model == "demo-model"
            assert request.title == "Transformer Survey"
            return PaperAnalysis(
                summary="A concise summary.",
                key_claims=("Claim one", "Claim two"),
                suggested_ideas=(
                    SuggestedIdea("Idea title", "Idea content"),
                ),
            )

    service = PaperAIAnalysisService(
        settings_loader=lambda: AISettings(
            "openai_compatible", "https://example.test/v1", "sk-secret", "demo-model"
        ),
        provider=Provider(),
    )

    result = service.analyze(
        PaperAnalysisRequest(
            title="Transformer Survey",
            authors="Authors not added",
            year="Year not added",
            abstract="No abstract captured yet.",
            research_notes="Notes linked to this paper will appear here.",
        )
    )

    assert result.summary == "A concise summary."
    assert result.key_claims == ("Claim one", "Claim two")
    assert result.suggested_ideas[0].title == "Idea title"


def test_paper_analysis_service_fails_closed_for_missing_settings_and_invalid_response():
    from research_workspace.application.ports.ai_provider import (
        AIProviderError,
        AISettings,
        PaperAnalysisRequest,
    )
    from research_workspace.application.services.paper_ai_analysis import (
        PaperAIAnalysisService,
    )

    request = PaperAnalysisRequest("Title", "", "", "", "")

    missing = PaperAIAnalysisService(settings_loader=lambda: None, provider=object())
    with pytest.raises(AIProviderError) as missing_error:
        missing.analyze(request)
    assert missing_error.value.code == "settings_missing"

    class InvalidProvider:
        def analyze_paper(self, settings, request):
            return SimpleNamespace(summary="", key_claims=(), suggested_ideas=())

    invalid = PaperAIAnalysisService(
        settings_loader=lambda: AISettings(
            "openai_compatible", "https://example.test/v1", "sk-secret", "demo-model"
        ),
        provider=InvalidProvider(),
    )
    with pytest.raises(AIProviderError) as invalid_error:
        invalid.analyze(request)
    assert invalid_error.value.code == "invalid_response"


def test_openai_compatible_provider_uses_configured_base_url_and_parses_json():
    from research_workspace.application.ports.ai_provider import (
        AISettings,
        PaperAnalysisRequest,
    )
    from research_workspace.infrastructure.ai.openai_compatible import (
        OpenAICompatibleProvider,
    )

    calls = []

    def transport(method, url, headers, payload, timeout):
        calls.append((method, url, headers, payload, timeout))
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"summary":"Summary text",'
                            '"key_claims":["Claim"],'
                            '"suggested_ideas":[{"title":"Idea","content":"Content"}]}'
                        )
                    }
                }
            ]
        }

    provider = OpenAICompatibleProvider(transport=transport, timeout_seconds=3)
    result = provider.analyze_paper(
        AISettings(
            "openai_compatible", "https://example.test/custom", "sk-secret", "model-a"
        ),
        PaperAnalysisRequest("Title", "Authors", "2026", "Abstract", "Notes"),
    )

    assert calls[0][1] == "https://example.test/custom/chat/completions"
    assert calls[0][2]["Authorization"] == "Bearer sk-secret"
    assert calls[0][3]["model"] == "model-a"
    assert result.summary == "Summary text"
    assert result.key_claims == ("Claim",)
    assert result.suggested_ideas[0].content == "Content"


def test_application_and_presentation_do_not_import_openai_provider():
    import research_workspace.application.services.paper_ai_analysis as service_module
    import research_workspace.presentation.pages.papers_page as papers_page

    source = inspect.getsource(service_module) + inspect.getsource(papers_page)
    assert "OpenAICompatibleProvider" not in source
    assert "openai" not in source.lower()
