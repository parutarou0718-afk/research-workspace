from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text

SOURCE_COLUMNS = (
    "id", "path", "sha256", "mime_type", "size_bytes", "modified_at",
    "imported_at", "read_only", "missing_at",
)
EVIDENCE_COLUMNS = (
    "id", "entity_type", "entity_id", "document_id", "version_id", "section",
    "page", "slide", "paragraph_id", "char_start", "char_end", "locator_json",
    "quote_hash", "created_at",
)
EVENT_V1_COLUMNS = (
    "id", "event_type", "aggregate_type", "aggregate_id", "payload_json",
    "deduplication_key", "causation_id", "correlation_id", "created_at", "processed_at",
)


def alembic_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def rows(database_path: Path, sql: str) -> tuple[dict[str, object], ...]:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            return tuple(dict(row) for row in connection.execute(text(sql)).mappings())
    finally:
        engine.dispose()


def _project(records, columns):
    return tuple({column: record[column] for column in columns} for record in records)


def test_0002_preserves_v01_rows_without_inventing_snapshots(v01_database) -> None:
    command.upgrade(alembic_config(v01_database.path), "0002")

    assert rows(v01_database.path, "SELECT count(*) AS n FROM source_snapshots")[0]["n"] == 0
    assert rows(v01_database.path, "SELECT count(*) AS n FROM source_documents")[0]["n"] == 0
    assert rows(v01_database.path, "SELECT count(*) AS n FROM evidence_refs")[0]["n"] == 0

    legacy_sources = rows(v01_database.path, "SELECT * FROM legacy_source_documents_v01 ORDER BY id")
    legacy_evidence = rows(v01_database.path, "SELECT * FROM legacy_evidence_refs_v01 ORDER BY id")
    assert _project(legacy_sources, SOURCE_COLUMNS) == v01_database.source_rows
    assert _project(legacy_evidence, EVIDENCE_COLUMNS) == v01_database.evidence_rows
    assert {row["migration_reason"] for row in legacy_sources + legacy_evidence} == {"NO_VERIFIED_SNAPSHOT_MAPPING"}
    assert {row["source_schema_revision"] for row in legacy_sources + legacy_evidence} == {"0001_foundation_schema"}
    assert len({row["migration_batch_id"] for row in legacy_sources + legacy_evidence}) == 1


def test_0002_preserves_domain_event_v1_storage_bytes(v01_database) -> None:
    before = v01_database.event_rows
    command.upgrade(alembic_config(v01_database.path), "0002")
    after = rows(v01_database.path, "SELECT * FROM domain_events ORDER BY id")
    assert _project(after, EVENT_V1_COLUMNS) == before
    assert after[0]["payload_json"].encode("utf-8") == before[0]["payload_json"].encode("utf-8")
    assert after[0]["schema_version"] == "1.0"
    for new_only in ("workspace_id", "command_id", "operation_id", "aggregate_version", "actor_type", "occurred_at"):
        assert after[0][new_only] is None


def test_0002_records_truthful_conservation_and_verified_internal_backup(v01_database) -> None:
    command.upgrade(alembic_config(v01_database.path), "0002")
    batch = rows(v01_database.path, "SELECT * FROM migration_batches")[0]
    counts = json.loads(batch["counts_json"])
    assert batch["source_revision"] == "0001_foundation_schema"
    assert batch["target_revision"] == "0002_gate1_import_parse"
    assert batch["status"] == "committed"
    assert counts == {
        "active_evidence_refs": 0,
        "active_source_documents": 0,
        "legacy_evidence_refs": len(v01_database.evidence_rows),
        "legacy_source_documents": len(v01_database.source_rows),
        "source_snapshots": 0,
    }

    backup_dirs = list((v01_database.path.parent / "staging" / "backup").glob("*"))
    assert len(backup_dirs) == 1
    backup_path = backup_dirs[0] / "workspace.db"
    verification = json.loads((backup_dirs[0] / "verification.json").read_text(encoding="utf-8"))
    assert verification["package_type"] == "internal_migration_safety_image"
    assert verification["source_revision"] == "0001_foundation_schema"
    assert verification["database_sha256"] == hashlib.sha256(backup_path.read_bytes()).hexdigest()
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001"


def test_0002_failure_after_legacy_rename_leaves_v01_startable(v01_database) -> None:
    config = alembic_config(v01_database.path)
    config.attributes["inject_0002_failure_after"] = "legacy_renames"
    with pytest.raises(RuntimeError, match="injected 0002 failure after legacy renames"):
        command.upgrade(config, "0002")

    engine = create_engine(f"sqlite:///{v01_database.path.as_posix()}")
    try:
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            assert connection.scalar(text("SELECT count(*) FROM source_documents")) == len(v01_database.source_rows)
            assert connection.scalar(text("SELECT count(*) FROM evidence_refs")) == len(v01_database.evidence_rows)
        assert "legacy_source_documents_v01" not in inspector.get_table_names()
        assert "source_snapshots" not in inspector.get_table_names()
    finally:
        engine.dispose()

    backup_paths = list((v01_database.path.parent / "staging" / "backup").glob("*/workspace.db"))
    assert len(backup_paths) == 1
    with sqlite3.connect(backup_paths[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT count(*) FROM source_documents").fetchone()[0] == len(v01_database.source_rows)
