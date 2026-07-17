"""Settings page controller."""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
)

from research_workspace.application.ports.ai_provider import AISettings
from research_workspace.presentation import load_ui_resource, require_child, set_feedback
from research_workspace.presentation.localization import zh_error


# Caller/packager contract: this process code requests a fresh application launch.
RESTART_EXIT_CODE = 100

RESTART_CODE_PROPERTY = "researchWorkspaceRestartExitCode"


class SettingsPage:
    def __init__(self, services):
        self.services = services
        self.widget = load_ui_resource("settings_page.ui")
        self.scroll_area = require_child(self.widget, QScrollArea, "settingsScrollArea")
        self.title_label = require_child(self.widget, QLabel, "pageTitleLabel")
        self.ai_provider_label = require_child(self.widget, QLabel, "aiProviderLabel")
        self.ai_provider_value_label = require_child(
            self.widget, QLabel, "aiProviderValueLabel"
        )
        self.ai_base_url_edit = require_child(
            self.widget, QLineEdit, "aiBaseUrlLineEdit"
        )
        self.ai_api_key_edit = require_child(
            self.widget, QLineEdit, "aiApiKeyLineEdit"
        )
        self.ai_model_edit = require_child(self.widget, QLineEdit, "aiModelLineEdit")
        self.save_ai_settings_button = require_child(
            self.widget, QPushButton, "saveAiSettingsButton"
        )
        self.test_ai_connection_button = require_child(
            self.widget, QPushButton, "testAiConnectionButton"
        )
        self.ai_settings_status_label = require_child(
            self.widget, QLabel, "aiSettingsStatusLabel"
        )
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
        self.error_label = require_child(self.widget, QLabel, "dataDirectoryErrorLabel")
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
        self._ai_test_handle = None
        self._ai_test_timer = QTimer(self.widget)
        self._ai_test_timer.setInterval(50)
        self._ai_test_timer.timeout.connect(self._poll_ai_connection_test)

        self.confirm_button.setEnabled(False)
        self.pending_status_label.clear()
        self.restart_now_button.setEnabled(False)
        self.later_button.setEnabled(False)
        self.choose_button.clicked.connect(self.choose_directory)
        self.confirm_button.clicked.connect(self.confirm_directory)
        self.restart_now_button.clicked.connect(self.restart_now)
        self.later_button.clicked.connect(self.later)
        self.save_ai_settings_button.clicked.connect(self.save_ai_settings)
        self.test_ai_connection_button.clicked.connect(self.test_ai_connection)
        self._load_ai_settings()

    def _ai_store(self):
        return getattr(self.services, "ai_settings_store", None)

    def _load_ai_settings(self) -> None:
        store = self._ai_store()
        if store is None:
            return
        settings = store.load()
        if settings is None:
            return
        self.ai_base_url_edit.setText(settings.base_url)
        self.ai_api_key_edit.setText(settings.api_key)
        self.ai_model_edit.setText(settings.model)

    def _current_ai_settings(self) -> AISettings:
        return AISettings(
            "openai_compatible",
            self.ai_base_url_edit.text().strip(),
            self.ai_api_key_edit.text().strip(),
            self.ai_model_edit.text().strip(),
        )

    def save_ai_settings(self) -> None:
        store = self._ai_store()
        if store is None:
            set_feedback(self.ai_settings_status_label, "error", "AI 设置存储不可用。")
            return
        try:
            store.save(self._current_ai_settings())
        except ValueError as exc:
            set_feedback(self.ai_settings_status_label, "error", zh_error(str(exc)))
            return
        set_feedback(self.ai_settings_status_label, "success", "AI 设置已保存。")

    def test_ai_connection(self) -> None:
        tester = getattr(self.services, "ai_connection_tester", None)
        test_async = getattr(tester, "test_async", None)
        if test_async is None:
            set_feedback(self.ai_settings_status_label, "error", "连接测试不可用。")
            return
        try:
            settings = self._current_ai_settings()
        except ValueError as exc:
            set_feedback(self.ai_settings_status_label, "error", zh_error(str(exc)))
            return
        set_feedback(self.ai_settings_status_label, "working", "正在测试连接…")
        self.test_ai_connection_button.setEnabled(False)
        self._ai_test_handle = test_async(settings)
        self._ai_test_timer.start()

    def _poll_ai_connection_test(self) -> None:
        handle = self._ai_test_handle
        if handle is None or not handle.done:
            return
        self._ai_test_timer.stop()
        self.test_ai_connection_button.setEnabled(True)
        if handle.error is None:
            set_feedback(self.ai_settings_status_label, "success", "连接成功。")
            return
        set_feedback(
            self.ai_settings_status_label,
            "error",
            zh_error(getattr(handle.error, "message", str(handle.error))),
        )

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
            status = "已有研究工作台"
        elif kind == "new":
            status = "将在这里初始化新的研究工作台。"
        else:
            status = f"无效的研究工作台：{inspection.reason}"
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
            "目录已验证。重启后使用该目录；当前数据不会被修改。"
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
