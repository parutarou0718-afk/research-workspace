from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

from PySide6.QtCore import Qt

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
    def __init__(self):
        self.deleted = []
        self.restored = []

    def delete_idea(self, idea_id):
        self.deleted.append(idea_id)

    def restore_idea(self, idea_id):
        self.restored.append(idea_id)


def idea(
    index=1,
    *,
    title=None,
    content=None,
    status="active",
    origin_type="manual",
    actions=("edit", "soft_delete"),
):
    return SimpleNamespace(
        id=uuid4(),
        title=title or f"Resultative Complement Theory {index}",
        content=content or "A compact preview of the research idea and its evidence trail.",
        status=status,
        origin_type=origin_type,
        row_version=index,
        actions=actions,
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


def test_idea_library_uses_card_layout_not_table():
    names = widget_names()
    assert {
        "ideaSearchLineEdit",
        "ideaTypeFilterButton",
        "ideaTagFilterButton",
        "newIdeaButton",
        "ideasLibraryListView",
        "ideasEmptyStateCard",
        "ideasEmptyActionButton",
    } <= names
    assert "ideasTable" not in names


def test_idea_library_empty_state_is_specific(qtbot):
    page = IdeasPage(services())
    qtbot.addWidget(page.widget)

    assert not page.empty_state.isHidden()
    assert page.empty_title_label.text() == "还没有想法。"
    assert page.empty_body_label.text() == "记录你的第一个研究想法。"
    assert page.empty_action_button.text() == "新建想法"
    assert page.list_view.count() == 0


def test_idea_library_renders_cards_and_searches_title_tag_type(qtbot):
    rows = (
        idea(1, title="Resultative Complement Theory", origin_type="claim"),
        idea(2, title="Evidence for Mandarin Corpus", origin_type="evidence"),
        idea(3, title="Open Question About Evaluation", origin_type="question"),
    )
    page = IdeasPage(services(rows))
    qtbot.addWidget(page.widget)

    assert page.empty_state.isHidden()
    assert page.list_view.count() == 3
    first = page.list_view.item(0).text()
    assert "Resultative Complement Theory" in first
    assert "论点" in first
    assert "3 篇相关论文" in first
    assert "5 个关系" in first
    assert "最近更新" in first
    assert page.list_view.item(0).sizeHint().height() >= 96

    page.search_line_edit.setText("evidence")
    assert page.list_view.count() == 1
    assert "Mandarin Corpus" in page.list_view.item(0).text()

    page.search_line_edit.setText("question")
    assert page.list_view.count() == 1
    assert "Open Question" in page.list_view.item(0).text()


def test_idea_library_handles_30_and_100_rows_without_horizontal_scroll(qtbot):
    for count in (30, 100):
        page = IdeasPage(services(tuple(idea(index) for index in range(count))))
        qtbot.addWidget(page.widget)
        page.widget.resize(1140, 720)
        page.widget.show()
        qtbot.wait(20)
        assert page.list_view.count() == count
        assert page.scroll_area.horizontalScrollBar().maximum() == 0
        assert page.scroll_area.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"


def test_idea_library_visible_actions_keep_existing_crud_path(qtbot):
    current = idea(1)
    app_services = services((current,))
    page = IdeasPage(app_services)
    qtbot.addWidget(page.widget)

    page.list_view.setCurrentRow(0)
    qtbot.mouseClick(page.delete_button, Qt.MouseButton.LeftButton)
    assert app_services.crud_actions.deleted == [current.id]

    archived = idea(2, status="archived", actions=("restore",))
    app_services = services((archived,))
    page = IdeasPage(app_services)
    qtbot.addWidget(page.widget)
    page.list_view.setCurrentRow(0)
    qtbot.mouseClick(page.restore_button, Qt.MouseButton.LeftButton)
    assert app_services.crud_actions.restored == [archived.id]
