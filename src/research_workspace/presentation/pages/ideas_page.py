"""Thin Idea page controller and local-only Markdown rendering boundary."""

import html
import re

from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTextBrowser

from research_workspace.presentation import load_ui_resource, require_child
from research_workspace.presentation.dialogs.idea_editor_dialog import IdeaEditorDialog
from research_workspace.presentation.pages.papers_page import CrudPageController
from research_workspace.presentation.view_models.ideas import IdeasViewModel


class IdeasPage(CrudPageController):
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("ideas_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "ideasScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.table = require_child(self.widget, QTableWidget, "ideasTable")
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, 240)
        self.new_button = require_child(self.widget, QPushButton, "newIdeaButton")
        self.edit_button = require_child(self.widget, QPushButton, "editIdeaButton")
        self.delete_button = require_child(self.widget, QPushButton, "deleteIdeaButton")
        self.restore_button = require_child(self.widget, QPushButton, "restoreIdeaButton")
        self.view_model = IdeasViewModel(
            getattr(services, "get_ideas", None),
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
            for column, value in enumerate((row.title, row.status, row.origin_type, str(row.row_version))):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self._update_actions()
        return rows

    def open_new(self):
        IdeaEditorDialog(self.services, parent=self.widget).exec()
        self.refresh()

    def open_edit(self):
        row = self._selected()
        if row is not None and "edit" in row.actions:
            IdeaEditorDialog(self.services, row, self.widget).exec()
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


_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_safe_markdown(markdown: str) -> str:
    source = html.escape(markdown, quote=False)
    source = _IMAGE.sub(lambda match: match.group(1), source)

    def safe_link(match: re.Match[str]) -> str:
        label, target = match.group(1), html.unescape(match.group(2)).strip()
        scheme = target.split(":", 1)[0].casefold() if ":" in target else ""
        if scheme and scheme not in {"http", "https", "mailto"}:
            return label
        return f"[{label}]({target})"

    source = _LINK.sub(safe_link, source)
    document = QTextDocument()
    document.setMarkdown(source)
    return document.toHtml()


def configure_safe_markdown_browser(browser: QTextBrowser, markdown: str) -> None:
    browser.setOpenExternalLinks(False)
    browser.setOpenLinks(False)
    browser.setHtml(render_safe_markdown(markdown))
