import json
from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtWidgets import QLabel, QTableWidget

from research_workspace.presentation.pages.overview_page import OverviewPage
from research_workspace.presentation.view_models.overview import OverviewViewModel


UI_DIR = (
    Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
)


def _property_text(widget, name: str) -> str:
    prop = next(item for item in widget.findall("property") if item.attrib["name"] == name)
    value = prop.find("string")
    return "" if value is None or value.text is None else value.text


def _widget(root, object_name: str):
    return next(item for item in root.iter("widget") if item.attrib["name"] == object_name)


def _number_property(node, name: str) -> int:
    prop = next(item for item in node.findall("property") if item.attrib["name"] == name)
    return int(prop.find("number").text)


def test_ui01_design_tokens_are_research_os_palette():
    tokens = json.loads((UI_DIR / "design_tokens.json").read_text(encoding="utf-8"))

    assert tokens["colors"] == {
        "background": "#F6F8FC",
        "surface": "#FFFFFF",
        "primary": "#4F7DFF",
        "primaryHover": "#356AE6",
        "primarySoft": "#EEF4FF",
        "textMain": "#172033",
        "textSecondary": "#667085",
        "textMuted": "#98A2B3",
        "border": "#E4E7EC",
        "success": "#16A34A",
        "warning": "#D97706",
        "danger": "#DC2626",
    }
    assert tokens["typography"]["fontFamily"] == "Segoe UI Variable, Microsoft YaHei UI"
    assert tokens["typography"]["title"] == 24
    assert tokens["typography"]["sectionTitle"] == 16
    assert tokens["typography"]["body"] == 14
    assert tokens["typography"]["caption"] == 12
    assert tokens["typography"]["kpi"] == 28
    assert tokens["radius"] == {"card": 14, "control": 8}
    assert tokens["controls"] == {"buttonHeight": 36, "inputHeight": 36}
    assert tokens["shadow"]["card"] == "0 1px 3px rgba(16,24,40,0.06)"


def test_ui01_sidebar_order_spacing_and_navigation_visuals():
    root = ElementTree.parse(UI_DIR / "main_window.ui").getroot()
    nav = _widget(root, "navigationCard")
    assert 220 <= _number_property(nav, "minimumWidth") <= 232
    assert 220 <= _number_property(nav, "maximumWidth") <= 232

    names_in_order = [
        item.attrib["name"]
        for item in root.iter("widget")
        if item.attrib.get("name", "").startswith("nav")
        and item.attrib.get("name", "").endswith("Button")
    ]
    assert names_in_order == [
        "navOverviewButton",
        "navPapersButton",
        "navIdeasButton",
        "navRelationsButton",
        "navSubmissionsButton",
        "navConferencesButton",
        "navGrantsButton",
        "navImportsButton",
        "navMonitoringButton",
        "navVersionCandidatesButton",
        "navSettingsButton",
    ]

    expected_text = {
        "navOverviewButton": "Dashboard",
        "navPapersButton": "Papers",
        "navIdeasButton": "Ideas",
        "navRelationsButton": "Relations",
        "navSubmissionsButton": "Submissions",
        "navConferencesButton": "Conferences",
        "navGrantsButton": "Grants",
        "navImportsButton": "Import Sources",
        "navMonitoringButton": "Source Monitoring",
        "navVersionCandidatesButton": "Version Candidates",
        "navSettingsButton": "Settings",
    }
    for name, text in expected_text.items():
        button = _widget(root, name)
        assert _property_text(button, "text") == text
        assert _number_property(button, "minimumHeight") == 40

    stylesheet = _property_text(_widget(root, "centralWidget"), "styleSheet")
    assert "#EEF4FF" in stylesheet
    assert "#356AE6" in stylesheet
    assert "#F5F7FB" in stylesheet
    assert "#E5E7EB" in stylesheet


def test_ui01_uses_no_default_groupbox_chrome():
    for path in UI_DIR.glob("*.ui"):
        root = ElementTree.parse(path).getroot()
        assert "QGroupBox" not in {node.attrib["class"] for node in root.iter("widget")}


def test_ui01_overview_has_empty_suggestions_and_polished_submission_table(qtbot):
    controller = OverviewPage(services=object())
    qtbot.addWidget(controller.widget)
    controller.render(
        OverviewViewModel(
            revision_count=0,
            ready_count=0,
            upcoming_conference_count=0,
            upcoming_grant_count=0,
            suggestions=(),
            submission_rows=("Paper A | Journal | revision | 2026-07-20Z",),
            activities=(),
            focus_items=(),
            focus_progress=0,
        )
    )

    assert controller.widget.findChild(QLabel, "suggestionsEmptyTitleLabel").text() == "暂时没有建议。"
    assert (
        controller.widget.findChild(QLabel, "suggestionsEmptyBodyLabel").text()
        == "导入论文或记录研究笔记后，这里会显示分析结果。"
    )
    assert controller.suggestions_list.isHidden()

    table = controller.widget.findChild(QTableWidget, "submissionOverviewTable")
    assert not table.showGrid()
    assert table.rowHeight(0) == 44
    assert [table.item(0, column).text() for column in range(4)] == [
        "Paper A",
        "Journal",
        "返修中",
        "2026-07-20",
    ]


def test_ui01_quick_record_controls_are_visible_and_actionable(qtbot):
    controller = OverviewPage(services=object())
    qtbot.addWidget(controller.widget)

    assert controller.quick_idea_line_edit.placeholderText() == "记录一条研究笔记"
    assert controller.idea_argument_button.isEnabled()
    assert controller.idea_material_button.isEnabled()
    assert controller.idea_question_button.isEnabled()
    assert controller.save_idea_button.text() == "记录"
