"""Thin Submission page controller."""

from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.submission_editor_dialog import SubmissionEditorDialog
from research_workspace.presentation.pages.papers_page import CrudPageController
from research_workspace.presentation.view_models.submissions import SubmissionsViewModel


class SubmissionsPage(CrudPageController):
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("submissions_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "submissionsScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.table = require_child(self.widget, QTableWidget, "submissionOverviewTable")
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, 240)
        self.new_button = require_child(self.widget, QPushButton, "newSubmissionButton")
        self.edit_button = require_child(self.widget, QPushButton, "editSubmissionButton")
        self.transition_button = require_child(self.widget, QPushButton, "transitionSubmissionButton")
        self.delete_button = require_child(self.widget, QPushButton, "deleteSubmissionButton")
        self.restore_button = require_child(self.widget, QPushButton, "restoreSubmissionButton")
        self.view_model = SubmissionsViewModel(
            getattr(services, "get_submissions", None),
            getattr(services, "crud_actions", None),
        )
        self.new_button.clicked.connect(self.open_new)
        self.edit_button.clicked.connect(self.open_edit)
        self.transition_button.clicked.connect(self.open_transition)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.refresh()

    def refresh(self):
        self._require_ui_thread()
        rows = self.view_model.refresh()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            deadline = row.deadline_at.isoformat() if row.deadline_at else ""
            values = (row.venue, row.status, str(row.paper_id), deadline, str(row.row_version))
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self._update_actions()
        return rows

    def open_new(self):
        SubmissionEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_edit(self):
        row = self._selected()
        if row is not None and "edit" in row.actions:
            SubmissionEditorDialog(self.services, row, self.widget).exec()
            self.refresh()

    def open_transition(self):
        row = self._selected()
        if row is not None and "transition" in row.actions:
            SubmissionEditorDialog(
                self.services, row, self.widget, transition_only=True
            ).exec()
            self.refresh()

    def delete_selected(self):
        row = self._selected()
        if row is not None and "soft_delete" in row.actions:
            self.view_model.delete(row)
            self.refresh()

    def restore_selected(self):
        row = self._selected()
        if row is not None and "restore" in row.actions:
            self.view_model.restore(row)
            self.refresh()

    def _update_actions(self):
        self._standard_actions()
        row = self._selected()
        actions = () if row is None else row.actions
        transitions = () if row is None else row.allowed_transitions
        if row is not None and row.active_version_id is None:
            transitions = tuple(
                value for value in transitions if value in {"preparing", "ready"}
            )
        self.transition_button.setEnabled(
            "transition" in actions and bool(transitions)
        )
