from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QScrollArea, QTableWidget

from research_workspace.application.queries.get_monitoring import (
    MonitoringDashboard,
    MonitoringRootProjection,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


class Query:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


@dataclass
class Actions:
    calls: list[tuple[str, object]]

    def add(self, path: Path) -> None:
        self.calls.append(("add", path))

    def pause(self, root_id) -> None:
        self.calls.append(("pause", root_id))

    def resume(self, root_id) -> None:
        self.calls.append(("resume", root_id))

    def remove(self, root_id) -> None:
        self.calls.append(("remove", root_id))


def _root(marker: str = "m1", status: str = "active"):
    return MonitoringRootProjection(
        uuid4(),
        Path("D:/Research"),
        status,
        NOW,
        2,
        1,
        ("SOURCE_BUSY",),
        ("paper.pdf",),
        uuid4(),
        "running",
        12,
        100,
        3,
        False,
        False,
        marker,
    )


def test_monitoring_page_is_populated_and_actions_are_real(qtbot, monkeypatch) -> None:
    from research_workspace.presentation.pages.monitoring_page import MonitoringPage

    root = _root()
    actions = Actions([])
    services = SimpleNamespace(
        get_monitoring=Query(MonitoringDashboard((root,))),
        monitoring_actions=actions,
    )
    page = MonitoringPage(services)
    qtbot.addWidget(page.widget)
    table = page.widget.findChild(QTableWidget, "monitoringRootsTable")

    assert table.rowCount() == 1
    assert page.widget.findChild(QScrollArea, "monitoringScrollArea").widgetResizable()
    table.selectRow(0)
    qtbot.mouseClick(
        page.widget.findChild(QPushButton, "pauseMonitoringRootButton"),
        Qt.MouseButton.LeftButton,
    )
    qtbot.mouseClick(
        page.widget.findChild(QPushButton, "resumeMonitoringRootButton"),
        Qt.MouseButton.LeftButton,
    )
    qtbot.mouseClick(
        page.widget.findChild(QPushButton, "removeMonitoringRootButton"),
        Qt.MouseButton.LeftButton,
    )

    assert actions.calls == [
        ("pause", root.monitoring_root_id),
        ("resume", root.monitoring_root_id),
        ("remove", root.monitoring_root_id),
    ]
    assert all(button.isEnabled() for button in page.widget.findChildren(QPushButton))


def test_monitoring_unread_changes_only_on_explicit_view(qtbot) -> None:
    from research_workspace.presentation.pages.monitoring_page import MonitoringPage

    root = _root()
    query = Query(MonitoringDashboard((root,)))
    page = MonitoringPage(
        SimpleNamespace(get_monitoring=query, monitoring_actions=Actions([]))
    )
    qtbot.addWidget(page.widget)
    table = page.widget.findChild(QTableWidget, "monitoringRootsTable")
    assert table.item(0, 6).text() == "未读"

    page.refresh()
    assert table.item(0, 6).text() == "未读"
    page.open_selected_item(0, 0)
    assert table.item(0, 6).text() == "已读"

    query.value = MonitoringDashboard((_root(marker="m2"),))
    query.value = MonitoringDashboard(
        (
            MonitoringRootProjection(
                root.monitoring_root_id,
                root.original_path,
                root.status,
                root.last_event_at,
                root.waiting_count,
                root.failure_count,
                root.recent_failure_codes,
                root.recent_imports,
                root.reconciliation_run_id,
                root.reconciliation_status,
                root.reconciliation_items_seen,
                root.reconciliation_items_estimated,
                root.reconciliation_items_changed,
                root.overflow_warning,
                root.capacity_warning,
                "m2",
            ),
        )
    )
    page.refresh()
    assert table.item(0, 6).text() == "未读"
