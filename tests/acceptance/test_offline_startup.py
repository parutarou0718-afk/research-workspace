from dataclasses import FrozenInstanceError
from pathlib import Path
import socket

import pytest

from research_workspace.application.ports.config_store import AppConfig
from research_workspace import bootstrap
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore


def test_application_starts_with_network_disabled(isolated_app_dirs, monkeypatch):
    def block_socket_creation(*args, **kwargs):
        raise AssertionError("network socket creation is forbidden")

    monkeypatch.setattr(socket, "socket", block_socket_creation)
    assert hasattr(bootstrap, "bootstrap_application")
    result = bootstrap.bootstrap_application()

    assert result.ok is True, result.error.error_label.text() if result.error else ""
    assert result.window.objectName() == "mainWindow"
    assert result.error is None
    data_directory = Path(result.window.services.config.active_data_directory)
    assert (data_directory / "research_workspace.db").is_file()
    assert all((data_directory / name).is_dir() for name in ("logs", "derived", "exports", "backups"))
    result.window.close()
    assert result.window.services.closed is True


def test_bootstrap_result_is_frozen_and_has_exactly_one_presentation(isolated_app_dirs):
    assert hasattr(bootstrap, "BootstrapResult")
    assert hasattr(bootstrap, "bootstrap_application")
    result = bootstrap.bootstrap_application()

    assert isinstance(result, bootstrap.BootstrapResult)
    assert (result.window is None) != (result.error is None)
    with pytest.raises(FrozenInstanceError):
        result.ok = False
    result.window.close()


def test_directory_switch_initializes_database_before_saving_pending(tmp_path):
    assert hasattr(bootstrap, "WorkspaceDataDirectoryService")
    active = (tmp_path / "active").resolve()
    selected = (tmp_path / "selected").resolve()
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(AppConfig("1.0", active, None, "INFO"))
    service = bootstrap.WorkspaceDataDirectoryService(store)

    result = service.execute(selected)

    assert result.ok is True
    assert (selected / "research_workspace.db").is_file()
    assert service.inspect(selected).kind == "existing"
    assert store.load().active_data_directory == active
    assert store.load().pending_data_directory == selected


def test_corrupt_target_database_does_not_mutate_configuration(tmp_path):
    assert hasattr(bootstrap, "WorkspaceDataDirectoryService")
    active = (tmp_path / "active").resolve()
    selected = (tmp_path / "corrupt").resolve()
    selected.mkdir()
    (selected / "research_workspace.db").write_bytes(b"not a sqlite database")
    original = AppConfig("1.0", active, None, "INFO")
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(original)

    result = bootstrap.WorkspaceDataDirectoryService(store).execute(selected)

    assert result.ok is False
    assert result.error.code == "CONFIG_WORKSPACE_INVALID"
    assert store.load() == original


def test_corrupt_pending_is_cleared_and_recovery_shows_paths_and_reason(isolated_app_dirs):
    active = (isolated_app_dirs["root"] / "active").resolve()
    pending = (isolated_app_dirs["root"] / "corrupt-pending").resolve()
    active.mkdir()
    bootstrap._run_migrations(active / "research_workspace.db")
    pending.mkdir()
    (pending / "research_workspace.db").write_bytes(b"corrupt")
    store = bootstrap.JsonConfigStore()
    store.save(AppConfig("1.0", active, pending, "INFO"))

    result = bootstrap.bootstrap_application()

    assert result.ok is False
    assert result.error.widget.objectName() == "startupErrorPage"
    assert str(active) in result.error.error_label.text()
    assert str(pending) in result.error.error_label.text()
    assert "CONFIG_WORKSPACE_INVALID" in result.error.error_label.text()
    assert store.load() == AppConfig("1.0", active, None, "INFO")
