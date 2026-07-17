from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame

from research_workspace.presentation.pages.papers_page import PapersPage


UI_PATH = (
    __import__("pathlib").Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
    / "papers_page.ui"
)


class Query:
    def __init__(self, rows=()):
        self.rows = tuple(rows)

    def project(self, *, include_deleted=False):
        return self.rows


class Actions:
    def __init__(self):
        self.deleted = []
        self.restored = []

    def delete_paper(self, paper_id):
        self.deleted.append(paper_id)

    def restore_paper(self, paper_id):
        self.restored.append(paper_id)


def row(title, status="active", version=1, actions=("edit", "soft_delete")):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        status=status,
        current_version_id=None,
        row_version=version,
        actions=actions,
        updated_at="2026-07-18T10:00:00Z",
    )


def services(rows=()):
    return SimpleNamespace(get_papers=Query(rows), crud_actions=Actions())


def widget_names():
    root = ElementTree.parse(UI_PATH).getroot()
    return {
        element.attrib["name"]
        for element in root.iter()
        if "name" in element.attrib
    }


def ui_strings():
    return [
        element.text or ""
        for element in ElementTree.parse(UI_PATH).getroot().iter("string")
    ]


def global_rect(widget):
    return widget.rect().translated(widget.mapToGlobal(widget.rect().topLeft()))


def test_paper_page_uses_product_layout_not_raw_table():
    names = widget_names()
    assert {
        "paperSearchLineEdit",
        "paperStatusFilterButton",
        "paperYearFilterButton",
        "paperTagFilterButton",
        "newPaperButton",
        "papersListView",
        "paperDetailCard",
        "paperMetadataTextLabel",
        "paperAbstractTextLabel",
        "paperResearchNotesTextLabel",
        "paperTimelineTextLabel",
        "paperResearchAnalysisTitleLabel",
        "paperResearchAnalysisTextLabel",
        "paperAnalyzeWithAiButton",
        "paperResearchAnalysisMilestoneLabel",
        "paperNextStepTitleLabel",
        "paperNextStepTextLabel",
        "paperCreateIdeaButton",
        "paperRelatedIdeasTextLabel",
        "paperRelatedPapersTextLabel",
        "paperRelationsTextLabel",
        "papersEmptyStateCard",
        "papersEmptyActionButton",
    } <= names
    assert "papersTable" not in names


def test_paper_workspace_layout_is_balanced_and_card_like():
    names = widget_names()
    assert {"papersListCard", "paperDetailCard"} <= names
    joined = "\n".join(ui_strings())
    assert 'font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI"' in joined
    assert "QListWidget#papersListView::item" in joined
    assert "border-radius: 14px" in joined


def test_paper_detail_actions_are_visible_at_demo_sizes(qtbot):
    first = row("Transformer Survey", status="active")
    page = PapersPage(services((first,)))
    qtbot.addWidget(page.widget)

    for width, height, minimum_detail_width in ((1366, 768, 700), (1280, 720, 680)):
        page.widget.resize(width, height)
        page.widget.show()
        page.list_view.setCurrentRow(0)
        page._update_actions()
        qtbot.wait(0)

        list_card = page.widget.findChild(QFrame, "papersListCard")
        detail_card = page.widget.findChild(QFrame, "paperDetailCard")
        split_width = list_card.width() + detail_card.width()
        list_ratio = list_card.width() / split_width
        assert 0.35 <= list_ratio <= 0.42
        assert detail_card.width() >= minimum_detail_width
        assert page.scroll_area.horizontalScrollBar().maximum() == 0

        viewport = global_rect(page.scroll_area.viewport())
        assert viewport.contains(global_rect(page.research_analysis_title_label))
        assert viewport.contains(global_rect(page.analyze_with_ai_button))
        assert viewport.contains(global_rect(page.next_step_title_label))
        assert viewport.contains(global_rect(page.create_idea_button))


def test_paper_page_empty_state_is_specific_and_actionable(qtbot):
    page = PapersPage(services())
    qtbot.addWidget(page.widget)

    assert not page.empty_state.isHidden()
    assert page.widget.findChild(QLabel, "papersEmptyIconLabel") is None
    assert page.empty_title_label.text() == "No papers yet."
    assert (
        page.empty_body_label.text()
        == "Import or create your first paper to start building your research workspace."
    )
    assert page.empty_action_button.text() == "Create Paper"
    assert page.list_view.count() == 0
    assert page.widget.findChild(QFrame, "papersListCard").isHidden()
    assert page.edit_button.isHidden()
    assert page.delete_button.isHidden()
    assert page.restore_button.isHidden()


def test_paper_page_renders_cards_detail_and_search(qtbot):
    first = row("Transformer Survey", status="active")
    second = row("Revision Plan", status="archived", actions=("restore",))
    page = PapersPage(services((first, second)))
    qtbot.addWidget(page.widget)

    assert page.empty_state.isHidden()
    assert not page.widget.findChild(QFrame, "papersListCard").isHidden()
    assert page.list_view.count() == 2
    assert "Transformer Survey" in page.list_view.item(0).text()

    page.list_view.setCurrentRow(0)
    page._update_actions()
    assert page.detail_title_label.text() == "Transformer Survey"
    assert page.status_badge_label.text() == "Active"
    assert page.research_analysis_title_label.text() == "Research Analysis"
    assert page.research_analysis_text_label.text() == "AI is not configured."
    assert page.analyze_with_ai_button.text() == "Open AI Settings"
    assert page.analyze_with_ai_button.isEnabled()
    assert page.research_analysis_milestone_label.text() == (
        "Configure AI in Settings to analyze this paper."
    )
    assert page.next_step_title_label.text() == "Next Step"
    assert page.next_step_text_label.text() == "Capture an idea from this paper."
    assert page.create_idea_button.text() == "Create Idea"
    assert page.edit_button.isEnabled()
    assert page.delete_button.isEnabled()
    assert not page.restore_button.isEnabled()

    page.search_line_edit.setText("revision")
    assert page.list_view.count() == 1
    assert "Revision Plan" in page.list_view.item(0).text()
    page.list_view.setCurrentRow(0)
    page._update_actions()
    assert page.status_badge_label.text() == "Archived"
    assert not page.delete_button.isEnabled()
    assert page.restore_button.isEnabled()


def test_paper_page_visible_actions_keep_existing_crud_path(qtbot):
    first = row("Delete Me")
    app_services = services((first,))
    page = PapersPage(app_services)
    qtbot.addWidget(page.widget)

    page.list_view.setCurrentRow(0)
    qtbot.mouseClick(page.delete_button, Qt.MouseButton.LeftButton)
    assert app_services.crud_actions.deleted == [first.id]

    restored = row("Restore Me", status="archived", actions=("restore",))
    app_services = services((restored,))
    page = PapersPage(app_services)
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    qtbot.mouseClick(page.restore_button, Qt.MouseButton.LeftButton)
    assert app_services.crud_actions.restored == [restored.id]


def test_paper_detail_create_idea_uses_existing_idea_dialog(qtbot, monkeypatch):
    opened = []

    class FakeIdeaDialog:
        def __init__(self, services, parent=None):
            opened.append((services, parent))

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(
        "research_workspace.presentation.pages.papers_page.IdeaEditorDialog",
        FakeIdeaDialog,
    )
    first = row("Idea Source")
    app_services = services((first,))
    page = PapersPage(app_services)
    qtbot.addWidget(page.widget)

    page.list_view.setCurrentRow(0)
    qtbot.mouseClick(page.create_idea_button, Qt.MouseButton.LeftButton)

    assert opened == [(app_services, page.widget), "exec"]
