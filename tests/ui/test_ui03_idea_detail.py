from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtWidgets import QLabel, QPushButton

from research_workspace.presentation.pages.ideas_page import IdeasPage


UI_PATH = (
    __import__("pathlib").Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
    / "ideas_page.ui"
)


class Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


class Actions:
    def delete_idea(self, idea_id):
        raise AssertionError("delete should not be called by detail rendering")

    def restore_idea(self, idea_id):
        raise AssertionError("restore should not be called by detail rendering")


def idea(
    title="Resultative Complement Theory",
    content="A compact explanation of the idea and why it matters.",
    origin_type="claim",
):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        content=content,
        status="active",
        origin_type=origin_type,
        row_version=7,
        actions=("edit", "soft_delete"),
        updated_at="2026-07-18T10:00:00Z",
    )


def services(rows=()):
    return SimpleNamespace(get_ideas=Query(rows), crud_actions=Actions())


def widget_names():
    root = ElementTree.parse(UI_PATH).getroot()
    return {
        element.attrib["name"]
        for element in root.iter()
        if "name" in element.attrib
    }


def test_idea_detail_designer_contract_exists():
    assert {
        "ideaDetailCard",
        "ideaDetailTitleLabel",
        "ideaContentTextLabel",
        "ideaResearchNotesTextLabel",
        "ideaRelatedPapersTextLabel",
        "ideaRelationsTextLabel",
        "ideaTimelineTextLabel",
        "ideaAiSuggestionsCard",
        "ideaAiSuggestionsTitleLabel",
        "ideaAiSuggestionsTextLabel",
        "ideaAnalyzeWithAiButton",
        "ideaAiMilestoneLabel",
        "ideaNextStepCard",
        "ideaNextStepTitleLabel",
        "ideaNextStepTextLabel",
        "ideaNextStepMilestoneLabel",
        "ideaEmptyDetailCard",
    } <= widget_names()


def test_idea_detail_empty_state_has_next_step_context(qtbot):
    page = IdeasPage(services())
    qtbot.addWidget(page.widget)

    assert page.widget.findChild(QLabel, "ideasEmptyIconLabel") is None
    assert not page.empty_detail_card.isHidden()
    assert page.empty_detail_title_label.text() == "Idea Detail"
    assert page.detail_card.isHidden()


def test_idea_detail_renders_selected_idea_and_ai_placeholder(qtbot):
    current = idea()
    page = IdeasPage(services((current,)))
    qtbot.addWidget(page.widget)

    page.list_view.setCurrentRow(0)
    page._update_actions()

    assert page.empty_detail_card.isHidden()
    assert not page.detail_card.isHidden()
    assert page.detail_title_label.text() == "Resultative Complement Theory"
    assert page.content_text_label.text() == "A compact explanation of the idea and why it matters."
    assert page.research_notes_text_label.text() == "Research notes linked to this idea will appear here."
    assert page.related_papers_text_label.text() == "No related papers yet."
    assert page.relations_text_label.text() == "No relations yet."
    assert page.timeline_text_label.text() == "Idea history will appear here."
    assert page.ai_suggestions_title_label.text() == "AI Suggestions"
    assert page.ai_suggestions_text_label.text() == (
        "No suggestions yet.\n\n"
        "Analyze this idea to discover related concepts and possible connections."
    )
    assert page.ai_button.text() == "Analyze with AI"
    assert page.ai_button.property("informational") is True
    assert page.ai_milestone_label.text() == "Available in the next milestone."
    assert page.next_step_title_label.text() == "Next Step"
    assert page.next_step_text_label.text() == "Analyze this idea with AI."
    assert page.next_step_milestone_label.text() == "Available in the next milestone."


def test_idea_detail_ai_button_is_informational_only(qtbot):
    page = IdeasPage(services((idea(),)))
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)

    button = page.widget.findChild(QPushButton, "ideaAnalyzeWithAiButton")
    assert button is page.ai_button
    assert button.receivers("clicked()") == 0
