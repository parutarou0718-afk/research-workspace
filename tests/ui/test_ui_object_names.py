import re
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
    } <= names


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
