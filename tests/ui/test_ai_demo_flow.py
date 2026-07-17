from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.pages.papers_page import PapersPage
from research_workspace.presentation.pages.settings_page import SettingsPage


class Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


class CrudActions:
    def __init__(self):
        self.deleted = []

    def delete_paper(self, paper_id):
        self.deleted.append(paper_id)

    def restore_paper(self, paper_id):
        pass


class DoneHandle:
    done = True
    status = "completed"

    def cancel(self):
        pass


def paper(title="Transformer Survey"):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        status="active",
        row_version=1,
        actions=("edit", "soft_delete"),
    )


class AnalysisHandle:
    def __init__(self, *, done=False, result=None, error=None):
        self.done = done
        self.result = result
        self.error = error

    def cancel(self):
        pass


class AnalysisService:
    def __init__(self, *, configured=True, handle=None):
        self.configured = configured
        self.handle = handle
        self.requests = []

    def is_configured(self):
        return self.configured

    def analyze_async(self, request):
        self.requests.append(request)
        return self.handle


def services(*, configured=True, handle=None):
    return SimpleNamespace(
        get_papers=Query((paper(),)),
        crud_actions=CrudActions(),
        paper_ai_analysis=AnalysisService(configured=configured, handle=handle),
    )


def test_settings_page_exposes_ai_configuration_and_masks_key(qtbot, tmp_path):
    from research_workspace.application.ports.ai_provider import AISettings
    from research_workspace.infrastructure.config.ai_settings_store import (
        JsonAISettingsStore,
    )

    store = JsonAISettingsStore(tmp_path / "ai-settings.json")
    store.save(
        AISettings(
            "openai_compatible", "https://example.test/v1", "sk-secret-demo", "gpt-demo"
        )
    )
    page = SettingsPage(SimpleNamespace(ai_settings_store=store, ai_connection_tester=None))
    qtbot.addWidget(page.widget)

    assert page.ai_provider_label.text() == "服务商"
    assert page.ai_provider_value_label.text() == "OpenAI 兼容接口"
    assert page.ai_base_url_edit.text() == "https://example.test/v1"
    assert page.ai_api_key_edit.echoMode() == page.ai_api_key_edit.EchoMode.Password
    assert page.ai_api_key_edit.text() == "sk-secret-demo"
    assert page.ai_model_edit.text() == "gpt-demo"


def test_paper_analysis_not_configured_opens_settings(qtbot):
    page = PapersPage(services(configured=False))
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    page._update_actions()

    assert "AI 尚未配置。" in page.research_analysis_text_label.text()
    assert page.analyze_with_ai_button.text() == "打开 AI 设置"


def test_paper_analysis_loading_prevents_repeated_clicks(qtbot):
    handle = AnalysisHandle(done=False)
    app_services = services(handle=handle)
    page = PapersPage(app_services)
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    page._update_actions()

    qtbot.mouseClick(page.analyze_with_ai_button, Qt.MouseButton.LeftButton)

    assert app_services.paper_ai_analysis.requests
    assert page.analyze_with_ai_button.isEnabled() is False
    assert page.research_analysis_text_label.text() == "正在分析论文…"


def test_paper_analysis_success_shows_structured_output_and_prefills_idea(qtbot, monkeypatch):
    from research_workspace.application.ports.ai_provider import (
        PaperAnalysis,
        SuggestedIdea,
    )

    result = PaperAnalysis(
        "Summary text",
        ("Claim one", "Claim two"),
        (SuggestedIdea("Suggested Idea", "Idea content"),),
    )
    page = PapersPage(services(handle=AnalysisHandle(done=True, result=result)))
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    page._update_actions()

    opened = []

    class FakeIdeaDialog:
        def __init__(self, services, record=None, parent=None, *, initial_title="", initial_content=""):
            opened.append((initial_title, initial_content, parent))

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(
        "research_workspace.presentation.pages.papers_page.IdeaEditorDialog",
        FakeIdeaDialog,
    )

    page._start_ai_analysis()
    page._poll_ai_analysis()

    assert "摘要\nSummary text" in page.research_analysis_text_label.text()
    assert "关键观点\n• Claim one\n• Claim two" in page.research_analysis_text_label.text()
    assert page.suggestion_buttons
    qtbot.mouseClick(page.suggestion_buttons[0], Qt.MouseButton.LeftButton)
    assert opened == [("Suggested Idea", "Idea content", page.widget), "exec"]


def test_paper_analysis_failure_shows_concise_retry(qtbot):
    page = PapersPage(
        services(handle=AnalysisHandle(done=True, error=SimpleNamespace(message="Authentication failed.")))
    )
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    page._update_actions()

    page._start_ai_analysis()
    page._poll_ai_analysis()

    assert page.research_analysis_text_label.text() == "Authentication failed."
    assert page.analyze_with_ai_button.text() == "重试"


def test_idea_dialog_accepts_initial_suggestion_values(qtbot):
    dialog = IdeaEditorDialog(
        SimpleNamespace(crud_actions=SimpleNamespace(create_idea=lambda *args: DoneHandle())),
        initial_title="Suggested Idea",
        initial_content="Idea content",
    )
    qtbot.addWidget(dialog)

    assert dialog.title_edit.text() == "Suggested Idea"
    assert dialog.content_edit.toPlainText() == "Idea content"
