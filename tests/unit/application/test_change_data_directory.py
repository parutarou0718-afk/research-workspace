from pathlib import Path

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.services.change_data_directory import ChangeDataDirectory
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


class MemoryConfigStore:
    def __init__(self, config: AppConfig | None):
        self.config = config
        self.save_calls: list[AppConfig] = []

    def load(self) -> AppConfig | None:
        return self.config

    def save(self, config: AppConfig) -> None:
        self.save_calls.append(config)
        self.config = config


def _config(path: Path) -> AppConfig:
    return AppConfig("1.0", path.resolve(), None, "INFO")


def test_cancelled_directory_choice_writes_nothing(tmp_path):
    store = MemoryConfigStore(_config(tmp_path / "old"))
    result = ChangeDataDirectory(store).execute(None)
    assert result.ok is True
    assert store.save_calls == []


def test_valid_switch_is_pending_until_restart(tmp_path):
    old_directory = tmp_path / "old"
    new_directory = tmp_path / "new"
    old_directory.mkdir()
    (old_directory / "research_workspace.db").write_bytes(b"old-data")
    store = MemoryConfigStore(_config(old_directory))

    result = ChangeDataDirectory(store).execute(new_directory)

    assert result.ok is True
    assert result.value.pending_data_directory == new_directory.resolve()
    assert result.value.active_data_directory == old_directory.resolve()
    assert (old_directory / "research_workspace.db").read_bytes() == b"old-data"
    assert not (new_directory / "research_workspace.db").exists()


def test_failed_validation_preserves_active_and_persisted_configuration(tmp_path):
    old = tmp_path / "old"
    selected = tmp_path / "unusable"
    original = _config(old)
    store = MemoryConfigStore(original)
    failure = AppError("CONFIG_DIRECTORY_UNWRITABLE", "Directory is not writable")
    service = ChangeDataDirectory(store, validate_directory=lambda _: Result.failure(failure))

    result = service.execute(selected)

    assert result.ok is False
    assert result.error == failure
    assert store.config == original
    assert store.save_calls == []


def test_write_probe_is_removed_after_success(tmp_path):
    selected = tmp_path / "selected"
    store = MemoryConfigStore(_config(tmp_path / "old"))

    assert ChangeDataDirectory(store).execute(selected).ok is True

    assert selected.is_dir()
    assert list(selected.iterdir()) == []


def test_first_run_recovery_choice_becomes_active_immediately(tmp_path):
    selected = tmp_path / "recovery-choice"
    store = MemoryConfigStore(None)

    result = ChangeDataDirectory(store).execute(selected)

    assert result.ok is True
    assert result.value == _config(selected)
    assert store.save_calls == [_config(selected)]
