"""Read-only relations page shell.

The page is intentionally presentation-only in UI-01A: it exposes a navigation
destination for existing relation facts without adding decision or mutation
behavior.
"""

from PySide6.QtWidgets import QLabel, QScrollArea, QTableWidget

from research_workspace.presentation import load_ui_resource, require_child


class RelationsPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("relations_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "relationsScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.relations_table = require_child(self.widget, QTableWidget, "relationsTable")
        self.relations_table.setShowGrid(False)
        for column in range(self.relations_table.columnCount()):
            self.relations_table.setColumnWidth(column, 180)
