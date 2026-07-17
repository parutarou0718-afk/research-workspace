"""Designer-owned Paper editor."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QLineEdit, QPushButton

from research_workspace.presentation import load_ui_into, require_child, set_feedback


class ProtectedEditorDialog(QDialog):
    """Shared main-thread polling for one protected operation handle."""

    def _bind_operation_widgets(self, save_button, error_label) -> None:
        self.operation_handle = None
        self.save_button = save_button
        self.error_label = error_label
        self._completion_timer = QTimer(self)
        self._completion_timer.setInterval(50)
        self._completion_timer.timeout.connect(self._poll_completion)

    def _track(self, handle) -> None:
        self.operation_handle = handle
        if handle is None:
            self.accept()
        else:
            self._completion_timer.start()

    def _poll_completion(self) -> None:
        if not self.operation_handle.done:
            return
        self._completion_timer.stop()
        self.save_button.setEnabled(True)
        if self.operation_handle.status == "completed":
            self.accept()
        else:
            set_feedback(
                self.error_label,
                "error",
                f"操作未完成：{self.operation_handle.status}",
            )

    def reject(self) -> None:
        if self.operation_handle is not None and not self.operation_handle.done:
            self.operation_handle.cancel()
        super().reject()


class PaperEditorDialog(ProtectedEditorDialog):
    def __init__(self, services, record=None, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.record = record
        load_ui_into("paper_editor_dialog.ui", self)
        self.title_edit = require_child(self, QLineEdit, "paperTitleEdit")
        self.status_combo = require_child(self, QComboBox, "paperStatusCombo")
        self.save_button = require_child(self, QPushButton, "savePaperButton")
        self.cancel_button = require_child(self, QPushButton, "cancelPaperButton")
        self.recovery_status_label = require_child(
            self, QLabel, "paperRecoveryStatusLabel"
        )
        self.error_label = require_child(self, QLabel, "paperErrorLabel")
        self._bind_operation_widgets(self.save_button, self.error_label)
        for text, value in (
            ("进行中", "active"),
            ("已暂停", "paused"),
            ("返修中", "revision"),
            ("已投稿", "submitted"),
            ("已完成", "completed"),
            ("已归档", "archived"),
        ):
            self.status_combo.addItem(text, value)
        if record is not None:
            self.title_edit.setText(record.title)
            index = self.status_combo.findData(record.status)
            if index >= 0:
                self.status_combo.setCurrentIndex(index)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)

    def save(self) -> None:
        set_feedback(
            self.recovery_status_label,
            "working",
            "正在准备安全恢复点…",
        )
        self.save_button.setEnabled(False)
        status = self.status_combo.currentData()
        try:
            if self.record is None:
                handle = self.services.crud_actions.create_paper(
                    self.title_edit.text(), status
                )
            else:
                handle = self.services.crud_actions.update_paper(
                    self.record.id, self.title_edit.text(), status
                )
        except Exception as exc:
            set_feedback(self.error_label, "error", str(exc))
            self.save_button.setEnabled(True)
            return
        self._track(handle)
