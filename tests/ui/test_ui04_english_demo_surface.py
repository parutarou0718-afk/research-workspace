import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.dialogs.paper_editor_dialog import PaperEditorDialog
from research_workspace.presentation.pages.ideas_page import IdeasPage
from research_workspace.presentation.pages.overview_page import SUBMISSION_STATUS_TEXT
from research_workspace.presentation.pages.papers_page import PapersPage


UI_DIR = (
    Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
)

DEMO_UI_FILES = (
    "main_window.ui",
    "overview_page.ui",
    "papers_page.ui",
    "paper_editor_dialog.ui",
    "ideas_page.ui",
    "idea_editor_dialog.ui",
)

FORBIDDEN_TEXT = re.compile(
    r"[\u4e00-\u9fff]|"
    r"譁|蜈|蠅|蟇|隶|謳|郛|遘|諱|豁|螳|咲|蛻|騾|遽|"
    r"Row version|Current version|Markdown content|repository|database",
    re.IGNORECASE,
)


def _ui_texts(file_name: str) -> list[str]:
    root = ElementTree.parse(UI_DIR / file_name).getroot()
    return [element.text or "" for element in root.iter("string")]


def test_demo_flow_ui_files_are_english_only():
    joined = "\n".join(
        text for file_name in DEMO_UI_FILES for text in _ui_texts(file_name)
    )

    assert not FORBIDDEN_TEXT.search(joined)
    for term in (
        "Research Workspace",
        "Dashboard",
        "Papers",
        "Paper List",
        "Create Paper",
        "Research Analysis",
        "Summary",
        "Key Claims",
        "Suggested Ideas",
        "Create Idea",
        "Save Idea",
        "Idea Library",
        "Idea Detail",
        "Next Step",
        "Analyze with AI",
    ):
        assert term in joined


class Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


class Actions:
    def delete_paper(self, paper_id): ...
    def restore_paper(self, paper_id): ...
    def delete_idea(self, idea_id): ...
    def restore_idea(self, idea_id): ...


def paper_row():
    return SimpleNamespace(
        id=uuid4(),
        title="Transformer Survey",
        status="active",
        current_version_id=None,
        row_version=1,
        actions=("edit", "soft_delete"),
        updated_at="2026-07-18T10:00:00Z",
    )


def idea_row():
    return SimpleNamespace(
        id=uuid4(),
        title="Resultative Complement Theory",
        content="A compact research idea.",
        origin_type="claim",
        status="unused",
        row_version=1,
        actions=("edit", "soft_delete"),
        updated_at="2026-07-18T10:00:00Z",
    )


def test_demo_flow_runtime_text_is_english(qtbot):
    services = SimpleNamespace(
        get_papers=Query((paper_row(),)),
        get_ideas=Query((idea_row(),)),
        crud_actions=Actions(),
    )
    paper_page = PapersPage(services)
    idea_page = IdeasPage(services)
    paper_dialog = PaperEditorDialog(services)
    idea_dialog = IdeaEditorDialog(services)
    for widget in (paper_page.widget, idea_page.widget, paper_dialog, idea_dialog):
        qtbot.addWidget(widget)

    paper_page.list_view.setCurrentRow(0)
    idea_page.list_view.setCurrentRow(0)
    paper_page._update_actions()
    idea_page._update_actions()

    runtime_text = "\n".join(
        (
            paper_page.metadata_text_label.text(),
            paper_page.research_analysis_text_label.text(),
            idea_page.ai_suggestions_text_label.text(),
            paper_dialog.windowTitle(),
            paper_dialog.recovery_status_label.text(),
            idea_dialog.windowTitle(),
            idea_dialog.recovery_status_label.text(),
            *SUBMISSION_STATUS_TEXT.values(),
        )
    )

    assert not FORBIDDEN_TEXT.search(runtime_text)
    assert "Authors not added" in paper_page.metadata_text_label.text()
    assert "Year not added" in paper_page.metadata_text_label.text()

