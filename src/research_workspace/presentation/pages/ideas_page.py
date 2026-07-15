"""Ideas page controller."""

from PySide6.QtWidgets import QLabel, QScrollArea

from research_workspace.presentation import load_ui_resource, require_child


class IdeasPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("ideas_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "ideasScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
