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
    assert not ({"overviewPage", "papersPage", "ideasPage"} & names)
    assert len(object_names(root)) == len(set(object_names(root)))
    assert all(LOWER_CAMEL.fullmatch(name) for name in object_names(root))
    assert_semantic_type_suffixes(root)


def test_runtime_ui_uses_no_implicit_slot_binding():
    for path in UI_DIR.glob("*.ui"):
        assert "connectSlotsByName" not in path.read_text(encoding="utf-8")
