"""Thin Paper page controller."""

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.paper_editor_dialog import PaperEditorDialog
from research_workspace.presentation.view_models.papers import PapersViewModel


class CrudPageController:
    def _require_ui_thread(self):
        if QThread.currentThread() is not self.widget.thread():
            raise RuntimeError("UI_UPDATE_OUTSIDE_QT_THREAD")

    def _selected(self):
        index = self.table.currentRow()
        return self.view_model.rows[index] if 0 <= index < len(self.view_model.rows) else None

    def _standard_actions(self):
        row = self._selected()
        actions = () if row is None else row.actions
        self.edit_button.setEnabled("edit" in actions)
        self.delete_button.setEnabled("soft_delete" in actions)
        self.restore_button.setEnabled("restore" in actions)


class PapersPage(CrudPageController):
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("papers_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "papersScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.table = require_child(self.widget, QTableWidget, "papersTable")
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, 240)
        self.new_button = require_child(self.widget, QPushButton, "newPaperButton")
        self.edit_button = require_child(self.widget, QPushButton, "editPaperButton")
        self.delete_button = require_child(self.widget, QPushButton, "deletePaperButton")
        self.restore_button = require_child(self.widget, QPushButton, "restorePaperButton")
        self.view_model = PapersViewModel(
            getattr(services, "get_papers", None),
            getattr(services, "crud_actions", None),
        )
        self.new_button.clicked.connect(self.open_new)
        self.edit_button.clicked.connect(self.open_edit)
        self.delete_button.clicked.connect(self.delete_selected)
        self.restore_button.clicked.connect(self.restore_selected)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.refresh()

    def refresh(self):
        self._require_ui_thread()
        rows = self.view_model.refresh()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row.title, row.status, str(row.current_version_id or ""), str(row.row_version))
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self._update_actions()
        return rows

    def open_new(self):
        PaperEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_edit(self):
        row = self._selected()
        if row is not None and "edit" in row.actions:
            PaperEditorDialog(self.services, row, self.widget).exec()
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
