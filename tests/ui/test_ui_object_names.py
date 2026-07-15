import re
import json
from pathlib import Path
from xml.etree import ElementTree

import pytest


UI_DIR = (
    Path(__file__).parents[2]
    / "src"
    / "research_workspace"
    / "presentation"
    / "ui"
)
PAGE_FILES = {
    "overview_page.ui": "overviewPage",
    "papers_page.ui": "papersPage",
    "ideas_page.ui": "ideasPage",
    "submissions_page.ui": "submissionsPage",
    "conferences_page.ui": "conferencesPage",
    "grants_page.ui": "grantsPage",
    "settings_page.ui": "settingsPage",
    "startup_error_page.ui": "startupErrorPage",
}
LOWER_CAMEL = re.compile(r"^[a-z][A-Za-z0-9]*$")
FORBIDDEN_DEFAULTS = {"pushButton", "label_2", "verticalLayout_3"}
WIDGET_SUFFIXES = {
    "QMainWindow": ("Window",),
    "QWidget": ("Page", "Widget"),
    "QPushButton": ("Button",),
    "QLabel": ("Label",),
    "QLineEdit": ("LineEdit",),
    "QTableWidget": ("Table",),
    "QFrame": ("Card",),
    "QStackedWidget": ("Stack",),
    "QScrollArea": ("ScrollArea",),
    "QListWidget": ("ListView",),
    "QProgressBar": ("Bar",),
}


def object_names(root):
    return [
        node.attrib["name"]
        for node in root.iter()
        if node.tag in {"widget", "layout", "spacer"} and "name" in node.attrib
    ]


def assert_semantic_type_suffixes(root):
    for node in root.iter("widget"):
        name = node.attrib["name"]
        assert name.endswith(WIDGET_SUFFIXES[node.attrib["class"]]), name
    for node in root.iter("layout"):
        assert node.attrib["name"].endswith(("HorizontalLayout", "VerticalLayout"))
    for node in root.iter("spacer"):
        assert node.attrib["name"].endswith("Spacer")


def test_runtime_ui_file_set_is_complete_and_independent():
    assert {path.name for path in UI_DIR.glob("*.ui")} == {
        "main_window.ui",
        *PAGE_FILES,
    }


@pytest.mark.parametrize("filename,root_name", PAGE_FILES.items())
def test_each_page_has_its_own_compliant_ui(filename, root_name):
    root = ElementTree.parse(UI_DIR / filename).getroot()
    assert root.find("widget").attrib["name"] == root_name
    names = object_names(root)
    assert len(names) == len(set(names))
    assert not FORBIDDEN_DEFAULTS.intersection(names)
    assert all(LOWER_CAMEL.fullmatch(name) for name in names)
    assert_semantic_type_suffixes(root)


def test_main_window_owns_only_navigation_and_page_stack():
    root = ElementTree.parse(UI_DIR / "main_window.ui").getroot()
    names = set(object_names(root))
    assert root.find("widget").attrib == {"class": "QMainWindow", "name": "mainWindow"}
    assert "pageStack" in names
    assert {f"nav{page}Button" for page in (
        "Overview", "Papers", "Ideas", "Submissions", "Conferences", "Grants", "Settings"
    )} <= names
    assert names == {
        "mainWindow",
        "centralWidget",
        "shellHorizontalLayout",
        "navigationCard",
        "navigationVerticalLayout",
        "brandLabel",
        "navOverviewButton",
        "navPapersButton",
        "navIdeasButton",
        "navSubmissionsButton",
        "navConferencesButton",
        "navGrantsButton",
        "navigationVerticalSpacer",
        "navSettingsButton",
        "localModeStatusLabel",
        "pageStack",
    }
    assert not any(
        node.attrib.get("class") in {
            "QScrollArea", "QTableWidget", "QLineEdit", "QComboBox", "QListWidget"
        }
        for node in root.iter("widget")
    )
    assert len(object_names(root)) == len(set(object_names(root)))
    assert all(LOWER_CAMEL.fullmatch(name) for name in object_names(root))
    assert_semantic_type_suffixes(root)


def test_runtime_ui_uses_no_implicit_slot_binding():
    for path in UI_DIR.glob("*.ui"):
        assert "connectSlotsByName" not in path.read_text(encoding="utf-8")


def test_overview_exposes_every_view_model_binding_and_prototype_region():
    root = ElementTree.parse(UI_DIR / "overview_page.ui").getroot()
    names = set(object_names(root))
    assert {
        "revisionCountLabel",
        "readyCountLabel",
        "upcomingConferenceCountLabel",
        "upcomingGrantCountLabel",
        "suggestionsListView",
        "submissionOverviewTable",
        "activitiesListView",
        "focusItemsListView",
        "focusProgressBar",
        "organizeNowButton",
        "quickIdeaLineEdit",
        "saveIdeaButton",
        "statisticsCard",
        "aiSuggestionsCard",
        "quickIdeaCard",
        "submissionsCard",
        "activitiesCard",
        "focusCard",
        "revisionHelpLabel",
        "readyHelpLabel",
        "conferenceHelpLabel",
        "grantHelpLabel",
        "viewAllSuggestionsButton",
        "ideaArgumentCategoryButton",
        "ideaMaterialCategoryButton",
        "ideaQuestionCategoryButton",
    } <= names
    assert widget_text(root, "viewAllSuggestionsButton") == "查看全部建议"
    assert widget_text(root, "ideaArgumentCategoryButton") == "论点"
    assert widget_text(root, "ideaMaterialCategoryButton") == "材料"
    assert widget_text(root, "ideaQuestionCategoryButton") == "问题"


def widget_text(root, object_name):
    widget = next(node for node in root.iter("widget") if node.attrib["name"] == object_name)
    text_property = next(
        prop for prop in widget.findall("property") if prop.attrib["name"] == "text"
    )
    return text_property.find("string").text or ""


def test_settings_and_startup_error_expose_task9_designer_controls():
    settings = ElementTree.parse(UI_DIR / "settings_page.ui").getroot()
    settings_names = set(object_names(settings))
    assert {
        "chooseDataDirectoryButton",
        "resolvedDataDirectoryLineEdit",
        "workspaceStatusLabel",
        "confirmDataDirectoryButton",
        "pendingDirectoryStatusLabel",
        "restartNowButton",
        "laterButton",
    } <= settings_names
    assert widget_text(settings, "dataDirectoryHelpLabel") == (
        "切换后将使用新目录中的工作台数据；现有数据不会自动迁移或删除。"
    )
    assert widget_text(settings, "confirmDataDirectoryButton") == "验证并在重启后切换"

    startup = ElementTree.parse(UI_DIR / "startup_error_page.ui").getroot()
    startup_names = set(object_names(startup))
    assert {
        "startupErrorLabel",
        "selectedDataDirectoryLineEdit",
        "dataDirectoryStatusLabel",
        "chooseDataDirectoryButton",
    } <= startup_names
    assert widget_text(startup, "chooseDataDirectoryButton") == "选择数据目录"


@pytest.mark.parametrize("filename", ["conferences_page.ui", "grants_page.ui"])
def test_coming_soon_designer_class_set_is_closed_and_passive(filename):
    root = ElementTree.parse(UI_DIR / filename).getroot()
    assert {node.attrib["class"] for node in root.iter("widget")} <= {
        "QWidget",
        "QScrollArea",
        "QLabel",
    }


def test_runtime_tokens_drive_card_style_spacing_and_point_typography(qapp):
    from research_workspace.presentation import load_ui_resource

    tokens = json.loads((UI_DIR / "design_tokens.json").read_text(encoding="utf-8"))
    widget = load_ui_resource("overview_page.ui")
    stylesheet = widget.styleSheet()
    assert tokens["colors"]["surface"] in stylesheet
    assert tokens["colors"]["border"] in stylesheet
    assert f'border-radius: {tokens["radius"]["card"]}px' in stylesheet
    body_points = tokens["typography"]["body"] * tokens["typography"]["pointScale"]
    title_points = tokens["typography"]["title"] * tokens["typography"]["pointScale"]
    assert f"font-size: {body_points:g}pt" in stylesheet
    assert f"font-size: {title_points:g}pt" in stylesheet

    root = ElementTree.parse(UI_DIR / "overview_page.ui").getroot()
    content_layout = next(
        node
        for node in root.iter("layout")
        if node.attrib["name"] == "overviewContentVerticalLayout"
    )
    properties = {
        prop.attrib["name"]: int(prop.find("number").text)
        for prop in content_layout.findall("property")
        if prop.find("number") is not None
    }
    assert properties["spacing"] == tokens["spacing"]["lg"]
    assert all(
        properties[name] == tokens["spacing"]["xl"]
        for name in ("leftMargin", "topMargin", "rightMargin", "bottomMargin")
    )
