from pathlib import Path
import sqlite3
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from research_workspace.application.ports.config_store import AppConfig
from research_workspace import bootstrap
from research_workspace.presentation.pages import settings_page
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


SettingsPage = settings_page.SettingsPage


class ChangeDirectoryStub:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, selected):
        self.calls.append(selected)
        return self.result


def _success(old: Path, selected: Path):
    return Result.success(AppConfig("1.0", old.resolve(), selected.resolve(), "INFO"))


def test_selection_uses_production_inspection_for_existing_new_and_invalid(qtbot, tmp_path):
    selected = tmp_path / "selected" / ".." / "selected"
    resolved = selected.resolve()
    resolved.mkdir(parents=True)
    bootstrap._run_migrations(resolved / "research_workspace.db")
    new_directory = (tmp_path / "new").resolve()
    invalid_directory = (tmp_path / "invalid").resolve()
    invalid_directory.mkdir()
    with sqlite3.connect(invalid_directory / "research_workspace.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001')")
    service = bootstrap.WorkspaceDataDirectoryService(
        bootstrap.JsonConfigStore(tmp_path / "config.json")
    )
    controller = SettingsPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)

    controller.select_directory(selected)

    assert controller.resolved_path_line_edit.text() == str(resolved)
    assert controller.workspace_status_label.text() == "现有 Research Workspace 工作台"
    assert controller.confirm_button.isEnabled()
    controller.select_directory(new_directory)
    assert controller.workspace_status_label.text().startswith("新的")
    assert controller.confirm_button.isEnabled()
    controller.select_directory(invalid_directory)
    assert controller.workspace_status_label.text().startswith("无效")
    assert not controller.confirm_button.isEnabled()


def test_cancelled_selection_performs_no_write(qtbot, monkeypatch):
    service = ChangeDirectoryStub(Result.failure(AppError("unused", "unused")))
    controller = SettingsPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")

    qtbot.mouseClick(controller.choose_button, Qt.MouseButton.LeftButton)

    assert service.calls == []


def test_success_records_pending_path_and_offers_restart_actions(qtbot, tmp_path, monkeypatch):
    selected = (tmp_path / "new").resolve()
    service = ChangeDirectoryStub(_success(tmp_path / "old", selected))
    controller = SettingsPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)
    controller.select_directory(selected)

    qtbot.mouseClick(controller.confirm_button, Qt.MouseButton.LeftButton)

    assert service.calls == [selected]
    assert controller.pending_status_label.text() == "已验证。重启应用后切换；原目录保持不变。"
    assert controller.restart_now_button.isEnabled()
    assert controller.later_button.isEnabled()

    quit_calls = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(True))
    qtbot.mouseClick(controller.restart_now_button, Qt.MouseButton.LeftButton)
    assert quit_calls == [True]
    assert QApplication.instance().property(settings_page.RESTART_CODE_PROPERTY) == settings_page.RESTART_EXIT_CODE


def test_validation_failure_leaves_restart_actions_disabled(qtbot, tmp_path):
    error = AppError("CONFIG_DIRECTORY_UNWRITABLE", "Directory is not writable")
    service = ChangeDirectoryStub(Result.failure(error))
    controller = SettingsPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)
    controller.select_directory(tmp_path / "bad")

    qtbot.mouseClick(controller.confirm_button, Qt.MouseButton.LeftButton)

    assert controller.error_label.text() == error.message
    assert not controller.restart_now_button.isEnabled()
    assert not controller.later_button.isEnabled()


def test_startup_error_chooser_initializes_first_workspace(qtbot, tmp_path, monkeypatch):
    assert hasattr(bootstrap, "WorkspaceDataDirectoryService")
    selected = (tmp_path / "recovery-workspace").resolve()
    store = bootstrap.JsonConfigStore(tmp_path / "config.json")
    service = bootstrap.WorkspaceDataDirectoryService(store)
    controller = StartupErrorPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(selected))

    qtbot.mouseClick(controller.choose_button, Qt.MouseButton.LeftButton)

    assert (selected / "research_workspace.db").is_file()
    assert store.load().active_data_directory == selected
    assert controller.directory_status_label.text() == "目录已验证并保存，请重新启动应用。"
