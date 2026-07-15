import json
import os
import subprocess
import sys

import pytest


PROBE = r"""
import json
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QWidget
from research_workspace.presentation.main_window import MainWindow
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage

PAGE_CONTROLS = {
    "overview": [
        "pageTitleLabel", "revisionCountLabel", "readyCountLabel",
        "upcomingConferenceCountLabel", "upcomingGrantCountLabel",
        "suggestionsListView", "submissionOverviewTable", "activitiesListView",
        "focusItemsListView", "focusProgressBar", "organizeNowButton",
        "quickIdeaLineEdit", "saveIdeaButton",
    ],
    "papers": ["pageTitleLabel"],
    "ideas": ["pageTitleLabel"],
    "submissions": ["pageTitleLabel", "submissionOverviewTable"],
    "conferences": ["pageTitleLabel", "comingSoonStatusLabel"],
    "grants": ["pageTitleLabel", "comingSoonStatusLabel"],
    "settings": [
        "pageTitleLabel", "dataDirectoryHelpLabel", "chooseDataDirectoryButton",
        "resolvedDataDirectoryLineEdit", "workspaceStatusLabel",
        "confirmDataDirectoryButton", "pendingDirectoryStatusLabel",
        "restartNowButton", "laterButton",
    ],
}


def overlaps(left, right):
    intersection = left.intersected(right)
    return intersection.width() > 0 and intersection.height() > 0


def global_rect(widget):
    return QRect(widget.mapToGlobal(widget.rect().topLeft()), widget.size())


def inspect_page(root, required_names):
    scroll = root.findChild(QScrollArea)
    required = []
    accessible = True
    for name in required_names:
        widget = root.findChild(QWidget, name)
        if widget is None:
            accessible = False
            continue
        required.append(widget)
        scroll.ensureWidgetVisible(widget, 8, 8)
        app.processEvents()
        viewport_rect = global_rect(scroll.viewport())
        control_rect = global_rect(widget)
        accessible = accessible and widget.isVisibleTo(root) and viewport_rect.contains(control_rect)

    rects = [global_rect(widget) for widget in required]
    nonoverlap = not any(
        overlaps(left, right)
        for index, left in enumerate(rects)
        for right in rects[index + 1:]
    )
    visible_text = [
        *root.findChildren(QLabel),
        *root.findChildren(QPushButton),
        *root.findChildren(QLineEdit),
    ]
    text_fits = all(
        widget.sizeHint().width() <= widget.width()
        and widget.sizeHint().height() <= widget.height()
        for widget in visible_text
        if widget.isVisibleTo(root)
    )
    tables = root.findChildren(QTableWidget)
    return {
        "controls_accessible": accessible,
        "nonoverlap": nonoverlap,
        "text_fits": text_fits,
        "page_h_max": scroll.horizontalScrollBar().maximum(),
        "page_v_max": scroll.verticalScrollBar().maximum(),
        "page_h_policy": scroll.horizontalScrollBarPolicy().name,
        "page_v_policy": scroll.verticalScrollBarPolicy().name,
        "table_h_maxima": [table.horizontalScrollBar().maximum() for table in tables],
    }


app = QApplication([])
window = MainWindow(services=object())
window.resize(1180, 720)
window.show()
app.processEvents()
pages = {}
for key, names in PAGE_CONTROLS.items():
    window.show_page(key)
    app.processEvents()
    pages[key] = inspect_page(window.pages[key].widget, names)

startup = StartupErrorPage(services=object())
startup.widget.resize(960, 700)
startup.widget.show()
app.processEvents()
pages["startup_error"] = inspect_page(
    startup.widget,
    ["pageTitleLabel", "startupErrorLabel", "selectedDataDirectoryLineEdit",
     "dataDirectoryStatusLabel", "chooseDataDirectoryButton"],
)

navigation = list(window.navigation_buttons.values())
navigation_rects = [global_rect(widget) for widget in navigation]
print(json.dumps({
    "scale": window.devicePixelRatioF(),
    "minimum": [window.minimumWidth(), window.minimumHeight()],
    "navigation_visible": all(widget.isVisible() for widget in navigation),
    "navigation_nonoverlap": not any(
        overlaps(left, right)
        for index, left in enumerate(navigation_rects)
        for right in navigation_rects[index + 1:]
    ),
    "pages": pages,
}))
"""


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_main_window_geometry_is_dpi_safe(scale):
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": str(scale)})
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["scale"] == pytest.approx(scale)
    assert report["minimum"] == [1180, 720]
    assert report["navigation_visible"]
    assert report["navigation_nonoverlap"]
    for page in report["pages"].values():
        assert page["controls_accessible"]
        assert page["nonoverlap"]
        assert page["text_fits"]
        assert page["page_h_policy"] == "ScrollBarAlwaysOff"
        assert page["page_v_policy"] == "ScrollBarAsNeeded"
        assert page["page_h_max"] == 0
        assert page["page_v_max"] >= 0
        assert all(maximum > 0 for maximum in page["table_h_maxima"])
