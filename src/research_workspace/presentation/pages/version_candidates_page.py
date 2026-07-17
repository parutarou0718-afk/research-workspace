"""Read-only controller for deterministic version-candidate explanations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import (
    QScrollArea,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
)

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.relation_review_dialog import (
    RelationReviewDialog,
)
from research_workspace.presentation.view_models.monitoring import SessionUnreadState
from research_workspace.presentation.view_models.version_candidates import (
    candidate_update_marker,
)


class VersionCandidatesPage:
    def __init__(self, services) -> None:
        self.services = services
        self.widget = load_ui_resource("version_candidates_page.ui")
        self.scroll_area = require_child(
            self.widget, QScrollArea, "versionCandidatesScrollArea"
        )
        self.table = require_child(
            self.widget, QTableWidget, "versionCandidatesTable"
        )
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, 220)
        self.detail = require_child(
            self.widget, QTextBrowser, "candidateDetailText"
        )
        self.review_button = require_child(self.widget, QPushButton, "reviewCandidateButton")
        self.undo_table = require_child(self.widget, QTableWidget, "safeUndoTable")
        for column in range(self.undo_table.columnCount()):
            self.undo_table.setColumnWidth(column, 280)
        self.undo_button = require_child(self.widget, QPushButton, "undoCommandButton")
        self.undo_notice = require_child(self.widget, QLabel, "undoNoticeLabel")
        if getattr(services, "decision_actions", None) is None:
            self.review_button.setParent(None)
            self.undo_button.setParent(None)
        self._unread = SessionUnreadState()
        self._rows = ()
        self._undo_rows = ()
        self._undo_handle = None
        self._undo_timer = QTimer(self.widget); self._undo_timer.setInterval(50)
        self._undo_timer.timeout.connect(self._poll_undo)
        self.table.cellDoubleClicked.connect(self.open_selected_item)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.undo_table.itemSelectionChanged.connect(self._update_actions)
        self.review_button.clicked.connect(self.review_selected)
        self.undo_button.clicked.connect(self.undo_selected)
        self.refresh()

    def _require_ui_thread(self) -> None:
        if QThread.currentThread() is not self.widget.thread():
            raise RuntimeError("UI_UPDATE_OUTSIDE_QT_THREAD")

    def refresh(self) -> None:
        self._require_ui_thread()
        query = getattr(self.services, "get_version_candidates", None)
        self._rows = query.execute() if query is not None else ()
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            rationale = json.loads(row.direction_rationale_json)
            values = (
                str(row.earlier_snapshot_id),
                str(row.later_snapshot_id),
                rationale.get("basis", "—"),
                row.rule_id,
                row.status,
                f"{row.detector_id} {row.detector_version}",
                (
                    "未读"
                    if self._unread.is_unread(
                        "version_candidate",
                        row.candidate_id,
                        candidate_update_marker(row),
                    )
                    else "已读"
                ),
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        undo_query = getattr(self.services, "get_safe_undo", None)
        self._undo_rows = undo_query.execute(
            as_of=datetime.now(timezone.utc)) if undo_query is not None else ()
        self.undo_table.setRowCount(len(self._undo_rows))
        for index, row in enumerate(self._undo_rows):
            values = (
                row.command_type, row.committed_at.isoformat(),
                ", ".join(map(str, row.affected_entity_ids)),
            )
            for column, value in enumerate(values):
                self.undo_table.setItem(index, column, QTableWidgetItem(value))
        self._update_actions()

    def _update_actions(self) -> None:
        if self.review_button.parent() is None:
            return
        self.review_button.setEnabled(
            0 <= self.table.currentRow() < len(self._rows))
        self.undo_button.setEnabled(
            0 <= self.undo_table.currentRow() < len(self._undo_rows))

    def review_selected(self) -> None:
        index = self.table.currentRow()
        if 0 <= index < len(self._rows):
            RelationReviewDialog(
                self.services, self._rows[index], self.widget).exec()
            self.refresh()

    def undo_selected(self) -> None:
        index = self.undo_table.currentRow()
        if not (0 <= index < len(self._undo_rows)):
            return
        self._undo_handle = self.services.decision_actions.undo(
            self._undo_rows[index].command_id)
        if self._undo_handle is None:
            self.refresh()
        else:
            self.undo_button.setEnabled(False)
            self._undo_timer.start()

    def _poll_undo(self) -> None:
        if not self._undo_handle.done:
            return
        self._undo_timer.stop()
        if self._undo_handle.status != "completed":
            self.undo_notice.setText(
                f"撤销未完成（{self._undo_handle.status}）")
        self._undo_handle = None
        self.refresh()

    def open_selected_item(self, row_index: int, _column: int) -> None:
        if not (0 <= row_index < len(self._rows)):
            return
        row = self._rows[row_index]
        marker = candidate_update_marker(row)
        self._unread.mark_viewed("version_candidate", row.candidate_id, marker)
        evidence = json.dumps(
            json.loads(row.signals_json),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self.detail.setPlainText(
            f"方向：{row.earlier_snapshot_id} → {row.later_snapshot_id}\n"
            f"规则：{row.rule_id}\n检测器：{row.detector_id} "
            f"{row.detector_version}\n证据：\n{evidence}"
        )
        self.refresh()
