"""Designer-owned Submission editor."""

from uuid import UUID

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton

from research_workspace.presentation import load_ui_into, require_child
from research_workspace.presentation.dialogs.paper_editor_dialog import (
    ProtectedEditorDialog,
)


class SubmissionEditorDialog(ProtectedEditorDialog):
    def __init__(
        self, services, record=None, parent=None, *, transition_only=False
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.record = record
        self.transition_only = transition_only
        load_ui_into("submission_editor_dialog.ui", self)
        self.paper_id_edit = require_child(
            self, QLineEdit, "submissionPaperIdEdit"
        )
        self.venue_edit = require_child(self, QLineEdit, "submissionVenueEdit")
        self.status_combo = require_child(
            self, QComboBox, "submissionStatusCombo"
        )
        self.save_button = require_child(
            self, QPushButton, "saveSubmissionButton"
        )
        self.cancel_button = require_child(
            self, QPushButton, "cancelSubmissionButton"
        )
        self.recovery_status_label = require_child(
            self, QLabel, "submissionRecoveryStatusLabel"
        )
        self.error_label = require_child(self, QLabel, "submissionErrorLabel")
        self._bind_operation_widgets(self.save_button, self.error_label)
        self.status_combo.addItems(("preparing", "ready"))
        if record is not None:
            self.paper_id_edit.setText(str(record.paper_id))
            self.paper_id_edit.setReadOnly(True)
            self.venue_edit.setText(record.venue)
            self.status_combo.clear()
            if transition_only:
                transitions = tuple(record.allowed_transitions)
                if record.active_version_id is None:
                    transitions = tuple(
                        value
                        for value in transitions
                        if value in {"preparing", "ready"}
                    )
                self.venue_edit.setReadOnly(True)
                self.status_combo.addItems(transitions)
            else:
                self.status_combo.addItem(record.status)
                self.status_combo.setEnabled(False)
                self.status_combo.setProperty(
                    "lockedReason", "use_transition_action"
                )
                self.status_combo.setToolTip(
                    "Use Update Status to change this submission state."
                )
            self.status_combo.setCurrentText(record.status)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)

    def save(self) -> None:
        self.recovery_status_label.setText("正在创建安全恢复点")
        self.save_button.setEnabled(False)
        try:
            paper_id = UUID(self.paper_id_edit.text())
            if self.record is None:
                handle = self.services.crud_actions.create_submission(
                    paper_id, self.venue_edit.text(),
                    self.status_combo.currentText(),
                )
            else:
                if self.transition_only:
                    handle = self.services.crud_actions.transition_submission(
                        self.record.id, self.status_combo.currentText()
                    )
                else:
                    handle = self.services.crud_actions.update_submission(
                        self.record.id, self.venue_edit.text()
                    )
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.save_button.setEnabled(True)
            return
        self._track(handle)
