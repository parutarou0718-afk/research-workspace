"""Submissions page controller."""

from PySide6.QtWidgets import QLabel, QScrollArea, QTableWidget

from research_workspace.presentation import load_ui_resource, require_child


class SubmissionsPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("submissions_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "submissionsScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.table = require_child(self.widget, QTableWidget, "submissionOverviewTable")
