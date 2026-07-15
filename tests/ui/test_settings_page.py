from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.presentation.pages import settings_page
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


def test_selection_displays_resolved_path_and_existing_or_new_status(qtbot, tmp_path, monkeypatch):
    selected = tmp_path / "selected" / ".." / "selected"
    resolved = selected.resolve()
    resolved.mkdir(parents=True)
    (resolved / "research_workspace.db").touch()
    service = ChangeDirectoryStub(_success(tmp_path / "old", resolved))
    controller = SettingsPage(SimpleNamespace(change_data_directory=service))
    qtbot.addWidget(controller.widget)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(selected))

    qtbot.mouseClick(controller.choose_button, Qt.MouseButton.LeftButton)

    assert controller.resolved_path_line_edit.text() == str(resolved)
    assert controller.workspace_status_label.text() == "现有 Research Workspace 工作台"
    assert service.calls == []


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
    assert controller.pending_status_label.text() == "已验证。重启应用后切换，当前目录保持不变。"
    assert controller.restart_now_button.isEnabled()
    assert controller.later_button.isEnabled()

    exit_codes = []
    monkeypatch.setattr(QApplication, "exit", lambda code=0: exit_codes.append(code))
    qtbot.mouseClick(controller.restart_now_button, Qt.MouseButton.LeftButton)
    assert exit_codes == [settings_page.RESTART_EXIT_CODE]


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
