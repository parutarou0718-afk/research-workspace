"""Papers page controller."""

from PySide6.QtWidgets import QLabel, QScrollArea

from research_workspace.presentation import load_ui_resource, require_child


class PapersPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("papers_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "papersScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
