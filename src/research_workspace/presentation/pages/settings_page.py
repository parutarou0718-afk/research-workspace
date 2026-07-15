"""Settings page controller."""

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QScrollArea

from research_workspace.presentation import load_ui_resource, require_child


class SettingsPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("settings_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "settingsScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.help_label = require_child(self.widget, QLabel, "dataDirectoryHelpLabel")
        self.choose_button = require_child(
            self.widget, QPushButton, "chooseDataDirectoryButton"
        )
        self.resolved_path_line_edit = require_child(
            self.widget, QLineEdit, "resolvedDataDirectoryLineEdit"
        )
        self.workspace_status_label = require_child(
            self.widget, QLabel, "workspaceStatusLabel"
        )
        self.confirm_button = require_child(
            self.widget, QPushButton, "confirmDataDirectoryButton"
        )
        self.pending_status_label = require_child(
            self.widget, QLabel, "pendingDirectoryStatusLabel"
        )
        self.restart_now_button = require_child(
            self.widget, QPushButton, "restartNowButton"
        )
        self.later_button = require_child(self.widget, QPushButton, "laterButton")
