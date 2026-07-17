"""Read-only controller for deterministic version-candidate explanations."""

from __future__ import annotations

import json

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
)

from research_workspace.presentation import load_ui_resource, require_child
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
        self.detail = require_child(
            self.widget, QTextBrowser, "candidateDetailText"
        )
        self._unread = SessionUnreadState()
        self._rows = ()
        self.table.cellDoubleClicked.connect(self.open_selected_item)
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
