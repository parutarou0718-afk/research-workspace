"""Startup-error page controller."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QLabel, QLineEdit, QPushButton, QScrollArea

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
        self.choose_button.clicked.connect(self.choose_directory)

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self.widget, "选择数据目录", self.selected_path_line_edit.text()
        )
        if not selected:
            return
        resolved = Path(selected).expanduser().resolve()
        self.selected_path_line_edit.setText(str(resolved))
        service = getattr(self.services, "change_data_directory", None)
        if service is None:
            return
        result = service.execute(resolved)
        if result.ok:
            self.directory_status_label.setText("目录已验证并保存，请重新启动应用。")
        else:
            self.directory_status_label.setText(result.error.message)
