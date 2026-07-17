"""Thin controller for the Designer-owned monitoring page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
)

from research_workspace.application.queries.get_monitoring import MonitoringDashboard
from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.view_models.monitoring import SessionUnreadState


class MonitoringPage:
    def __init__(self, services) -> None:
        self.services = services
        self.widget = load_ui_resource("monitoring_page.ui")
        self.scroll_area = require_child(
            self.widget, QScrollArea, "monitoringScrollArea"
        )
        self.table = require_child(
            self.widget, QTableWidget, "monitoringRootsTable"
        )
        self.detail = require_child(
            self.widget, QLabel, "monitoringDetailLabel"
        )
        self.progress = require_child(
            self.widget, QProgressBar, "reconciliationProgressBar"
        )
        self._unread = SessionUnreadState()
        self._rows = ()
        self._actions = getattr(services, "monitoring_actions", None)
        self._buttons = {
            "add": require_child(
                self.widget, QPushButton, "addMonitoringRootButton"
            ),
            "pause": require_child(
                self.widget, QPushButton, "pauseMonitoringRootButton"
            ),
            "resume": require_child(
                self.widget, QPushButton, "resumeMonitoringRootButton"
            ),
            "remove": require_child(
                self.widget, QPushButton, "removeMonitoringRootButton"
            ),
        }
        self._buttons["add"].clicked.connect(self.add_root)
        self._buttons["pause"].clicked.connect(lambda: self._run_selected("pause"))
        self._buttons["resume"].clicked.connect(
            lambda: self._run_selected("resume")
        )
        self._buttons["remove"].clicked.connect(
            lambda: self._run_selected("remove")
        )
        self.table.cellDoubleClicked.connect(self.open_selected_item)
        if self._actions is None:
            for button in self._buttons.values():
                button.hide()
        self.refresh()

    def _require_ui_thread(self) -> None:
        if QThread.currentThread() is not self.widget.thread():
            raise RuntimeError("UI_UPDATE_OUTSIDE_QT_THREAD")

    def refresh(self) -> None:
        self._require_ui_thread()
        query = getattr(self.services, "get_monitoring", None)
        dashboard = (
            query.execute() if query is not None else MonitoringDashboard(())
        )
        self._rows = dashboard.roots
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            progress = (
                f"{row.reconciliation_items_seen}/"
                f"{row.reconciliation_items_estimated or '?'}"
                if row.reconciliation_status is not None
                else "—"
            )
            values = (
                str(row.original_path),
                row.status,
                row.last_event_at.isoformat() if row.last_event_at else "—",
                str(row.waiting_count),
                str(row.failure_count),
                progress,
                (
                    "未读"
                    if self._unread.is_unread(
                        "monitoring_root",
                        row.monitoring_root_id,
                        row.meaningful_update_marker,
                    )
                    else "已读"
                ),
                "、".join(row.recent_imports) or "—",
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self._update_action_visibility()

    def add_root(self) -> None:
        if self._actions is None:
            return
        selected = QFileDialog.getExistingDirectory(
            self.widget, "选择监控目录"
        )
        if selected:
            self._actions.add(Path(selected))
            self.refresh()

    def _selected(self):
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _run_selected(self, action: str) -> None:
        selected = self._selected()
        if selected is None or self._actions is None:
            return
        getattr(self._actions, action)(selected.monitoring_root_id)
        self.refresh()

    def _update_action_visibility(self) -> None:
        selected = self._selected()
        status = selected.status if selected is not None else None
        self._buttons["pause"].setVisible(status == "active")
        self._buttons["resume"].setVisible(status == "paused")
        self._buttons["remove"].setVisible(selected is not None)

    def open_selected_item(self, row_index: int, _column: int) -> None:
        if not (0 <= row_index < len(self._rows)):
            return
        row = self._rows[row_index]
        self._unread.mark_viewed(
            "monitoring_root",
            row.monitoring_root_id,
            row.meaningful_update_marker,
        )
        self.detail.setText(
            f"{row.original_path}\n状态：{row.status}\n"
            f"等待：{row.waiting_count}，失败：{row.failure_count}"
        )
        if row.reconciliation_items_estimated:
            self.progress.setMaximum(row.reconciliation_items_estimated)
            self.progress.setValue(row.reconciliation_items_seen)
        else:
            self.progress.setMaximum(1)
            self.progress.setValue(0)
        self.refresh()
