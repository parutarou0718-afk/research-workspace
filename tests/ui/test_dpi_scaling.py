import json
import os
import subprocess
import sys

import pytest


PROBE = r"""
import json
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QLineEdit, QListWidget, QProgressBar,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QWidget,
)
from research_workspace.presentation.main_window import MainWindow
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage

PAGE_CONTROLS = {
    "overview": [
        "pageTitleLabel", "revisionCountLabel", "readyCountLabel",
        "upcomingConferenceCountLabel", "upcomingGrantCountLabel",
        "suggestionsListView", "submissionOverviewTable", "activitiesListView",
        "focusItemsListView", "focusProgressBar", "organizeNowButton",
        "quickIdeaLineEdit", "saveIdeaButton", "viewAllSuggestionsButton",
        "ideaArgumentCategoryButton", "ideaMaterialCategoryButton",
        "ideaQuestionCategoryButton",
    ],
    "papers": ["pageTitleLabel", "pageSubtitleLabel"],
    "ideas": ["pageTitleLabel", "pageSubtitleLabel"],
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
RELEVANT_TYPES = (QFrame, QLabel, QLineEdit, QListWidget, QProgressBar, QPushButton, QTableWidget)


def overlaps(left, right):
    intersection = left.intersected(right)
    return intersection.width() > 0 and intersection.height() > 0


def global_rect(widget):
    return QRect(widget.mapToGlobal(widget.rect().topLeft()), widget.size())


def direct_sibling_evidence(root):
    pair_count = 0
    nonoverlap = True
    parents = [root, *root.findChildren(QWidget)]
    for parent in parents:
        siblings = [
            child
            for child in parent.findChildren(
                QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
            )
            if child.objectName() and child.isVisibleTo(root) and isinstance(child, RELEVANT_TYPES)
        ]
        for index, left in enumerate(siblings):
            for right in siblings[index + 1:]:
                pair_count += 1
                nonoverlap = nonoverlap and not overlaps(left.geometry(), right.geometry())
    return pair_count, nonoverlap


def prepare_rendered_collection_text(root):
    for list_view in root.findChildren(QListWidget):
        if list_view.count() == 0:
            list_view.addItem("示例内容")
    for table in root.findChildren(QTableWidget):
        if table.rowCount() == 0:
            table.setRowCount(1)
        for column in range(table.columnCount()):
            if table.item(0, column) is None:
                table.setItem(0, column, QTableWidgetItem("示例"))


def rendered_text_evidence(root):
    counts = {"basic": 0, "headers": 0, "items": 0, "lists": 0, "progress": 0}
    fits = True
    for widget in [
        *root.findChildren(QLabel),
        *root.findChildren(QPushButton),
        *root.findChildren(QLineEdit),
    ]:
        if not widget.isVisibleTo(root):
            continue
        text = widget.text() if hasattr(widget, "text") else ""
        if isinstance(widget, QLineEdit) and not text:
            text = widget.placeholderText()
        if not text:
            continue
        counts["basic"] += 1
        metrics = widget.fontMetrics()
        if isinstance(widget, QLabel) and widget.wordWrap():
            needed = metrics.boundingRect(
                QRect(0, 0, max(1, widget.contentsRect().width()), 10000),
                Qt.TextFlag.TextWordWrap,
                text,
            )
            fits = fits and needed.height() <= widget.contentsRect().height()
        else:
            padding = 20 if isinstance(widget, (QPushButton, QLineEdit)) else 0
            fits = fits and metrics.horizontalAdvance(text) + padding <= widget.contentsRect().width()
            fits = fits and metrics.height() <= widget.contentsRect().height()

    for table in root.findChildren(QTableWidget):
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(column)
            counts["headers"] += 1
            fits = fits and header_item is not None
            if header_item is not None:
                fits = fits and header.fontMetrics().horizontalAdvance(header_item.text()) + 16 <= header.sectionSize(column)
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                item = table.item(row, column)
                counts["items"] += 1
                fits = fits and item is not None
                if item is not None:
                    fits = fits and table.fontMetrics().horizontalAdvance(item.text()) + 12 <= table.columnWidth(column)
                    fits = fits and table.fontMetrics().height() + 6 <= table.rowHeight(row)

    for list_view in root.findChildren(QListWidget):
        for index in range(list_view.count()):
            item = list_view.item(index)
            counts["lists"] += 1
            fits = fits and list_view.fontMetrics().horizontalAdvance(item.text()) + 12 <= list_view.viewport().width()
            fits = fits and list_view.sizeHintForRow(index) <= list_view.viewport().height()

    for progress in root.findChildren(QProgressBar):
        counts["progress"] += 1
        text = progress.text()
        fits = fits and progress.fontMetrics().horizontalAdvance(text) <= progress.contentsRect().width()
        fits = fits and progress.fontMetrics().height() <= progress.contentsRect().height()
    return counts, fits


def inspect_page(root, required_names):
    scroll = root.findChild(QScrollArea)
    prepare_rendered_collection_text(root)
    app.processEvents()
    accessible = True
    for name in required_names:
        widget = root.findChild(QWidget, name)
        if widget is None:
            accessible = False
            continue
        scroll.ensureWidgetVisible(widget, 8, 8)
        app.processEvents()
        accessible = (
            accessible
            and widget.isVisibleTo(root)
            and global_rect(scroll.viewport()).contains(global_rect(widget))
        )
    pair_count, siblings_nonoverlap = direct_sibling_evidence(root)
    text_counts, text_fits = rendered_text_evidence(root)
    tables = root.findChildren(QTableWidget)
    return {
        "controls_accessible": accessible,
        "sibling_pairs_checked": pair_count,
        "siblings_nonoverlap": siblings_nonoverlap,
        "text_counts": text_counts,
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
        assert page["sibling_pairs_checked"] > 0
        assert page["siblings_nonoverlap"]
        assert page["text_counts"]["basic"] > 0
        assert page["text_fits"]
        assert page["page_h_policy"] == "ScrollBarAlwaysOff"
        assert page["page_v_policy"] == "ScrollBarAsNeeded"
        assert page["page_h_max"] == 0
        assert page["page_v_max"] > 0
        assert all(maximum > 0 for maximum in page["table_h_maxima"])
    overview_counts = report["pages"]["overview"]["text_counts"]
    assert overview_counts["headers"] > 0
    assert overview_counts["items"] > 0
    assert overview_counts["lists"] > 0
    assert overview_counts["progress"] > 0
