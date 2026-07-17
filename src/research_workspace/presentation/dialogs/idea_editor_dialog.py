"""Designer-owned Idea editor preserving raw Markdown."""

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
)

from research_workspace.presentation import load_ui_into, require_child
from research_workspace.presentation import set_feedback
from research_workspace.presentation.dialogs.paper_editor_dialog import (
    ProtectedEditorDialog,
)


class IdeaEditorDialog(ProtectedEditorDialog):
    def __init__(
        self,
        services,
        record=None,
        parent=None,
        *,
        initial_title: str = "",
        initial_content: str = "",
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.record = record
        load_ui_into("idea_editor_dialog.ui", self)
        self.title_edit = require_child(self, QLineEdit, "ideaTitleEdit")
        self.content_edit = require_child(self, QPlainTextEdit, "ideaContentEdit")
        self.status_combo = require_child(self, QComboBox, "ideaStatusCombo")
        self.save_button = require_child(self, QPushButton, "saveIdeaButton")
        self.cancel_button = require_child(self, QPushButton, "cancelIdeaButton")
        self.recovery_status_label = require_child(
            self, QLabel, "ideaRecoveryStatusLabel"
        )
        self.error_label = require_child(self, QLabel, "ideaErrorLabel")
        self._bind_operation_widgets(self.save_button, self.error_label)
        for text, value in (
            ("Unused", "unused"),
            ("Used", "used"),
            ("Parked", "parked"),
            ("Archived", "archived"),
        ):
            self.status_combo.addItem(text, value)
        if record is not None:
            self.title_edit.setText(record.title)
            self.content_edit.setPlainText(record.content)
            index = self.status_combo.findData(record.status)
            if index >= 0:
                self.status_combo.setCurrentIndex(index)
        else:
            self.title_edit.setText(initial_title)
            self.content_edit.setPlainText(initial_content)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.reject)

    def save(self) -> None:
        set_feedback(
            self.recovery_status_label,
            "working",
            "Preparing a safe recovery point...",
        )
        self.save_button.setEnabled(False)
        values = (
            self.title_edit.text(),
            self.content_edit.toPlainText(),
            self.status_combo.currentData(),
        )
        try:
            if self.record is None:
                handle = self.services.crud_actions.create_idea(*values)
            else:
                handle = self.services.crud_actions.update_idea(
                    self.record.id, *values
                )
        except Exception as exc:
            set_feedback(self.error_label, "error", str(exc))
            self.save_button.setEnabled(True)
            return
        self._track(handle)
