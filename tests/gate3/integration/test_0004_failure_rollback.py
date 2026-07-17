from __future__ import annotations

import json
import sqlite3

from alembic import command
import pytest
from sqlalchemy import create_engine, inspect, text

from research_workspace.bootstrap import WorkspaceDataDirectoryService
from test_0004_schema_contract import _config


def test_successful_0004_preserves_v1_event_payload_bytes(tmp_path) -> None:
    database_path = tmp_path / "gate3-workspace.db"
    config = _config(database_path)
    command.upgrade(config, "0003")
    payload = '{ "legacy": true, "order": [3, 2, 1] }'
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO domain_events
            (id,schema_version,event_type,workspace_id,command_id,operation_id,
             aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
             deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "60000000-0000-0000-0000-000000000001", "1.0",
                "document.imported", None, None, None, "SourceDocument",
                "60000000-0000-0000-0000-000000000002", None, None, payload,
                "gate3-success-byte-preservation", None, None,
                "2026-07-17T00:00:00Z", None, None,
            ),
        )
        connection.commit()

    command.upgrade(config, "0004")

    with sqlite3.connect(database_path) as connection:
        stored = connection.execute(
            "SELECT payload_json FROM domain_events "
            "WHERE deduplication_key='gate3-success-byte-preservation'"
        ).fetchone()[0]
        assert stored.encode("utf-8") == payload.encode("utf-8")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_mid_0004_failure_restores_exact_startable_0003_and_keeps_backup(
    tmp_path,
) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    config = _config(gate3_database_path)
    command.upgrade(config, "0003")
    with sqlite3.connect(gate3_database_path) as connection:
        connection.execute(
            """INSERT INTO domain_events
            (id,schema_version,event_type,workspace_id,command_id,operation_id,
             aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
             deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "61000000-0000-0000-0000-000000000001", "1.0",
                "document.imported", None, None, None, "SourceDocument",
                "62000000-0000-0000-0000-000000000001", None, None,
                '{ "order": [3, 1, 2] }', "gate3-byte-preservation",
                None, None, "2026-07-17T00:00:00Z", None, None,
            ),
        )
        connection.commit()
    before = gate3_database_path.read_bytes()

    config.attributes["inject_0004_failure_after"] = "legacy_staging"
    with pytest.raises(RuntimeError, match="injected 0004 failure after legacy staging"):
        command.upgrade(config, "0004")

    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            payload = connection.scalar(text(
                "SELECT payload_json FROM domain_events "
                "WHERE deduplication_key='gate3-byte-preservation'"
            ))
            assert payload.encode() == b'{ "order": [3, 1, 2] }'
        assert "application_commands" not in inspector.get_table_names()
        assert "legacy_paper_versions_v01" not in inspector.get_table_names()
    finally:
        engine.dispose()

    backups = list(
        (gate3_database_path.parent / "staging" / "backup").glob("*/workspace.db")
    )
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
    assert before != b""


def test_bootstrap_accepts_only_complete_0004_workspace(tmp_path) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    command.upgrade(_config(gate3_database_path), "0004")
    selected = gate3_database_path.parent
    target = selected / "research_workspace.db"
    gate3_database_path.replace(target)

    service = object.__new__(WorkspaceDataDirectoryService)
    assert service.inspect(selected).kind == "existing"

    with sqlite3.connect(target) as connection:
        connection.execute("UPDATE alembic_version SET version_num='0005'")
        connection.commit()
    assert service.inspect(selected).kind == "invalid"

    with sqlite3.connect(target) as connection:
        connection.execute("UPDATE alembic_version SET version_num='0004'")
        connection.execute("DROP TABLE audit_changes")
        connection.commit()
    assert service.inspect(selected).kind == "invalid"
