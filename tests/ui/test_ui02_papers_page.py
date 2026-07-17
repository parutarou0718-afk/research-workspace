from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton

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
        "paperAiSummaryTextLabel",
        "paperRelatedIdeasTextLabel",
        "paperRelatedPapersTextLabel",
        "paperRelationsTextLabel",
        "papersEmptyStateCard",
        "papersEmptyActionButton",
    } <= names
    assert "papersTable" not in names


def test_paper_page_empty_state_is_specific_and_actionable(qtbot):
    page = PapersPage(services())
    qtbot.addWidget(page.widget)

    assert not page.empty_state.isHidden()
    assert page.empty_title_label.text() == "No papers yet."
    assert (
        page.empty_body_label.text()
        == "Import or create your first paper to start building your research workspace."
    )
    assert page.empty_action_button.text() == "Create Paper"
    assert page.list_view.count() == 0


def test_paper_page_renders_cards_detail_and_search(qtbot):
    first = row("Transformer Survey", status="active")
    second = row("Revision Plan", status="archived", actions=("restore",))
    page = PapersPage(services((first, second)))
    qtbot.addWidget(page.widget)

    assert page.empty_state.isHidden()
    assert page.list_view.count() == 2
    assert "Transformer Survey" in page.list_view.item(0).text()

    page.list_view.setCurrentRow(0)
    page._update_actions()
    assert page.detail_title_label.text() == "Transformer Survey"
    assert page.status_badge_label.text() == "Active"
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
