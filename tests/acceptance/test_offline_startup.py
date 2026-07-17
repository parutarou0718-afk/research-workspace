from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import socket
import sqlite3

import pytest

from research_workspace.application.ports.config_store import AppConfig
from research_workspace import bootstrap
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore


EXPECTED_WORKSPACE_TABLES = frozenset(
    {
        "alembic_version",
        "audit_logs",
        "audit_changes",
        "application_commands",
        "background_operations",
        "conferences",
        "domain_events",
        "entity_relations",
        "evidence_refs",
        "grants",
        "ideas",
        "import_batches",
        "import_items",
        "legacy_evidence_refs_v01",
        "legacy_dependent_records_v01",
        "legacy_paper_versions_v01",
        "legacy_relation_observations_v01",
        "legacy_source_documents_v01",
        "migration_batches",
        "notes",
        "operation_attempts",
        "paper_versions",
        "paper_version_candidates",
        "papers",
        "parse_artifacts",
        "parse_attempts",
        "parsed_blocks",
        "relation_observations",
        "reconciliation_runs",
        "recovery_points",
        "recovery_slots",
        "raw_event_pending_links",
        "raw_file_events",
        "snapshot_parse_preferences",
        "source_documents",
        "source_observation_events",
        "source_observations",
        "source_snapshots",
        "submissions",
        "task_attempts",
        "task_effects",
        "tasks",
        "workspace_metadata",
        "monitoring_roots",
        "pending_path_checks",
    }
)


def _table_inventory(database_path: Path) -> frozenset[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return frozenset(row[0] for row in rows)


def _write_revision_only_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001')")


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
    assert _table_inventory(selected / "research_workspace.db") == EXPECTED_WORKSPACE_TABLES
    assert store.load().active_data_directory == active
    assert store.load().pending_data_directory == selected


def test_production_inspection_classifies_new_and_exact_prepared_workspace(tmp_path):
    service = bootstrap.WorkspaceDataDirectoryService(
        JsonConfigStore(tmp_path / "config.json")
    )
    new_directory = (tmp_path / "new").resolve()
    prepared_directory = (tmp_path / "prepared").resolve()
    prepared_directory.mkdir()
    bootstrap._run_migrations(prepared_directory / "research_workspace.db")

    assert service.inspect(new_directory).kind == "new"
    assert service.inspect(prepared_directory).kind == "existing"
    assert _table_inventory(prepared_directory / "research_workspace.db") == EXPECTED_WORKSPACE_TABLES


def test_production_inspection_accepts_only_exact_gate3_revision(tmp_path):
    service = bootstrap.WorkspaceDataDirectoryService(
        JsonConfigStore(tmp_path / "config.json")
    )
    valid = (tmp_path / "valid-0004").resolve()
    valid.mkdir()
    bootstrap._run_migrations(valid / "research_workspace.db")

    assert service.inspect(valid).kind == "existing"

    for revision in ("0002", "0003", "0005", "unknown-future"):
        candidate = (tmp_path / revision).resolve()
        candidate.mkdir()
        shutil.copy2(valid / "research_workspace.db", candidate / "research_workspace.db")
        with sqlite3.connect(candidate / "research_workspace.db") as connection:
            connection.execute("UPDATE alembic_version SET version_num=?", (revision,))
        assert service.inspect(candidate).kind == "invalid"


def test_production_inspection_rejects_partial_0004_inventory(tmp_path):
    selected = (tmp_path / "partial-0004").resolve()
    selected.mkdir()
    with sqlite3.connect(selected / "research_workspace.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0004')")
        connection.execute("CREATE TABLE workspace_metadata (workspace_id CHAR(36) PRIMARY KEY)")

    service = bootstrap.WorkspaceDataDirectoryService(
        JsonConfigStore(tmp_path / "config.json")
    )
    assert service.inspect(selected).kind == "invalid"


def test_revision_only_database_is_invalid_and_never_saved(tmp_path):
    active = (tmp_path / "active").resolve()
    selected = (tmp_path / "revision-only").resolve()
    _write_revision_only_database(selected / "research_workspace.db")
    original = AppConfig("1.0", active, None, "INFO")
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(original)
    service = bootstrap.WorkspaceDataDirectoryService(store)

    inspection = service.inspect(selected)
    result = service.execute(selected)

    assert inspection.kind == "invalid"
    assert result.ok is False
    assert result.error.code == "CONFIG_WORKSPACE_INVALID"
    assert store.load() == original


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
