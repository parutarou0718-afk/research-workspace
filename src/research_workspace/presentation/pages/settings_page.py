"""Settings page controller."""

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
)

from research_workspace.presentation import load_ui_resource, require_child


# Caller/packager contract: this process code requests a fresh application launch.
RESTART_EXIT_CODE = 100

RESTART_CODE_PROPERTY = "researchWorkspaceRestartExitCode"


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
        self.error_label = require_child(
            self.widget, QLabel, "dataDirectoryErrorLabel"
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
        self._selected_directory: Path | None = None
        self.confirm_button.setEnabled(False)
        self.pending_status_label.clear()
        self.restart_now_button.setEnabled(False)
        self.later_button.setEnabled(False)
        self.choose_button.clicked.connect(self.choose_directory)
        self.confirm_button.clicked.connect(self.confirm_directory)
        self.restart_now_button.clicked.connect(self.restart_now)
        self.later_button.clicked.connect(self.later)

    def choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self.widget, "选择数据目录", self.resolved_path_line_edit.text()
        )
        if selected:
            self.select_directory(Path(selected))

    def select_directory(self, selected: Path) -> None:
        resolved = selected.expanduser().resolve()
        self._selected_directory = resolved
        self.resolved_path_line_edit.setText(str(resolved))
        inspection_method = getattr(
            self.services.change_data_directory, "inspect", None
        )
        inspection = inspection_method(resolved) if inspection_method is not None else None
        kind = inspection.kind if inspection is not None else (
            "existing" if (resolved / "research_workspace.db").is_file() else "new"
        )
        if kind == "existing":
            status = "现有 Research Workspace 工作台"
        elif kind == "new":
            status = "新的 Research Workspace 工作台（验证后初始化）"
        else:
            status = f"无效的 Research Workspace 工作台：{inspection.reason}"
        self.workspace_status_label.setText(status)
        self.error_label.clear()
        self.confirm_button.setEnabled(kind != "invalid")
        self.pending_status_label.clear()
        self.restart_now_button.setEnabled(False)
        self.later_button.setEnabled(False)

    def confirm_directory(self) -> None:
        if self._selected_directory is None:
            return
        service = getattr(self.services, "change_data_directory", None)
        if service is None:
            return
        result = service.execute(self._selected_directory)
        if not result.ok:
            self.error_label.setText(result.error.message)
            self.pending_status_label.clear()
            self.restart_now_button.setEnabled(False)
            self.later_button.setEnabled(False)
            return
        self.error_label.clear()
        self.pending_status_label.setText(
            "已验证。重启应用后切换；原目录保持不变。"
        )
        self.restart_now_button.setEnabled(True)
        self.later_button.setEnabled(True)

    def restart_now(self) -> None:
        application = QApplication.instance()
        if application is not None:
            application.setProperty(RESTART_CODE_PROPERTY, RESTART_EXIT_CODE)
        QApplication.quit()

    def later(self) -> None:
        self.restart_now_button.setEnabled(False)
        self.later_button.setEnabled(False)
