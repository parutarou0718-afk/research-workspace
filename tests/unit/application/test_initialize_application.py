import json
from pathlib import Path

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.services.initialize_application import InitializeApplication
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


def _config(active: Path, pending: Path | None = None) -> AppConfig:
    return AppConfig("1.0", active.resolve(), pending.resolve() if pending else None, "INFO")


def test_first_run_uses_default_and_writes_exact_config(tmp_path):
    default = tmp_path / "default-data"
    path = tmp_path / "config" / "config.json"
    store = JsonConfigStore(path)

    result = InitializeApplication(store, default_data_directory=lambda: default).execute()

    assert result.ok is True
    assert result.value.config == _config(default)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": "1.0",
        "active_data_directory": str(default.resolve()),
        "pending_data_directory": None,
        "log_level": "INFO",
    }


def test_pending_switch_is_promoted_only_on_next_initialization(tmp_path):
    old = tmp_path / "old"
    pending = tmp_path / "pending"
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(_config(old, pending))

    result = InitializeApplication(store).execute()

    assert result.ok is True
    assert result.value.config == _config(pending)
    assert store.load() == _config(pending)


def test_invalid_pending_is_cleared_and_returns_recovery_with_both_paths(tmp_path):
    old = tmp_path / "old"
    pending = tmp_path / "bad"
    old.mkdir()
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(_config(old, pending))
    error = AppError("CONFIG_DIRECTORY_UNWRITABLE", "Directory cannot be used")

    def validate(path: Path):
        return Result.failure(error) if path == pending.resolve() else Result.success(path)

    result = InitializeApplication(store, validate_directory=validate).execute()

    assert result.ok is True
    assert result.value.config == _config(old)
    assert result.value.recovery is not None
    assert result.value.recovery.active_data_directory == old.resolve()
    assert result.value.recovery.failed_pending_data_directory == pending.resolve()
    assert result.value.recovery.error == error
    assert store.load() == _config(old)


def test_default_failure_returns_recoverable_error_without_config_write(tmp_path):
    store = JsonConfigStore(tmp_path / "config.json")
    error = AppError("CONFIG_DIRECTORY_UNWRITABLE", "Choose another directory")

    result = InitializeApplication(
        store,
        default_data_directory=lambda: tmp_path / "bad-default",
        validate_directory=lambda _: Result.failure(error),
    ).execute()

    assert result.ok is False
    assert result.error.code == error.code
    assert result.error.message == error.message
    assert result.error.details["attempted_data_directory"] == str(
        (tmp_path / "bad-default").resolve()
    )
    assert not store.path.exists()


def test_atomic_save_failure_preserves_previous_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    store = JsonConfigStore(path)
    original = _config(tmp_path / "old")
    store.save(original)

    def fail_replace(source, destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr("research_workspace.infrastructure.config.json_config_store.os.replace", fail_replace)

    try:
        store.save(_config(tmp_path / "new"))
    except OSError as exc:
        assert "replace failure" in str(exc)
    else:
        raise AssertionError("save should fail")

    assert store.load() == original
    assert list(tmp_path.glob(".config.json.*.tmp")) == []


def test_config_rejects_relative_and_empty_active_or_pending_paths(tmp_path):
    for active, pending in (
        ("relative-data", None),
        ("", None),
        (str((tmp_path / "active").resolve()), "relative-pending"),
        (str((tmp_path / "active").resolve()), ""),
    ):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "active_data_directory": active,
                    "pending_data_directory": pending,
                    "log_level": "INFO",
                }
            ),
            encoding="utf-8",
        )
        store = JsonConfigStore(path)
        try:
            store.load()
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid paths were accepted: {active!r}, {pending!r}")


def test_config_rejects_duplicate_json_members(tmp_path):
    path = tmp_path / "config.json"
    active = str((tmp_path / "active").resolve()).replace("\\", "\\\\")
    path.write_text(
        '{"schema_version":"1.0",'
        f'"active_data_directory":"{active}",'
        f'"active_data_directory":"{active}",'
        '"pending_data_directory":null,"log_level":"INFO"}',
        encoding="utf-8",
    )

    try:
        JsonConfigStore(path).load()
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate configuration member was accepted")


def test_corrupt_config_returns_structured_startup_failure_without_cwd_reinterpretation(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "active_data_directory": "",
                "pending_data_directory": None,
                "log_level": "INFO",
            }
        ),
        encoding="utf-8",
    )

    result = InitializeApplication(JsonConfigStore(path)).execute()

    assert result.ok is False
    assert result.error.code == "CONFIG_LOAD_FAILED"
    assert result.error.details == {"exception_type": "ValueError"}
