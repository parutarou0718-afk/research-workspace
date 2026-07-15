import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QScrollArea, QTableWidget

PAGE_TYPES = (
    ("overview_page", "OverviewPage"),
    ("papers_page", "PapersPage"),
    ("ideas_page", "IdeasPage"),
    ("submissions_page", "SubmissionsPage"),
    ("conferences_page", "ConferencesPage"),
    ("grants_page", "GrantsPage"),
    ("settings_page", "SettingsPage"),
    ("startup_error_page", "StartupErrorPage"),
)


def controller_type(module_name, class_name):
    from importlib import import_module

    module = import_module(f"research_workspace.presentation.pages.{module_name}")
    assert hasattr(module, class_name)
    return getattr(module, class_name)


@pytest.mark.parametrize("module_name,class_name", PAGE_TYPES)
def test_pages_own_resizable_vertical_only_scroll_area(qtbot, module_name, class_name):
    controller = controller_type(module_name, class_name)(services=object())
    qtbot.addWidget(controller.widget)
    scroll_area = controller.widget.findChild(QScrollArea)
    assert scroll_area is not None
    assert scroll_area.widgetResizable()
    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    controller.widget.resize(640, 320)
    controller.widget.show()
    qtbot.wait(1)
    assert scroll_area.verticalScrollBar().maximum() > 0


def test_wide_tables_scroll_internally():
    controller = controller_type("submissions_page", "SubmissionsPage")(services=object())
    table = controller.widget.findChild(QTableWidget, "submissionOverviewTable")
    assert table is not None
    assert table.horizontalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    assert table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
