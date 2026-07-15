"""Startup-error page controller."""

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QScrollArea

from research_workspace.presentation import load_ui_resource, require_child


class StartupErrorPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("startup_error_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "startupErrorScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.error_label = require_child(self.widget, QLabel, "startupErrorLabel")
        self.selected_path_line_edit = require_child(
            self.widget, QLineEdit, "selectedDataDirectoryLineEdit"
        )
        self.directory_status_label = require_child(
            self.widget, QLabel, "dataDirectoryStatusLabel"
        )
        self.choose_button = require_child(
            self.widget, QPushButton, "chooseDataDirectoryButton"
        )
