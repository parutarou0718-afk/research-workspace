from __future__ import annotations

import json

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

GATE1_COLUMNS = {
    "workspace_metadata": ("workspace_id", "created_at", "clean_shutdown", "watcher_generation", "updated_at"),
    "migration_batches": ("id", "source_revision", "target_revision", "status", "pre_migration_backup_path_hash", "counts_json", "exceptions_json", "started_at", "finished_at"),
    "source_snapshots": ("id", "sha256", "size_bytes", "mime_type", "storage_relative_path", "created_at", "created_by_operation_id"),
    "source_observations": ("id", "original_path", "normalized_path", "normalized_path_hash", "original_filename", "current_snapshot_id", "availability_status", "baseline_only", "size_bytes", "modified_at", "file_id_hint", "volume_serial_hint", "first_seen_at", "last_seen_at", "missing_at", "row_version"),
    "source_observation_events": ("id", "source_observation_id", "event_type", "snapshot_id", "path_before_hash", "path_after_hash", "facts_json", "observed_at"),
    "background_operations": ("id", "operation_type", "status", "work_plan_fingerprint", "permission_context_json", "result_summary_json", "error_code", "created_at", "started_at", "finished_at", "cancel_requested_at"),
    "operation_attempts": ("id", "operation_id", "attempt_number", "status", "error_code", "diagnostic_summary_json", "started_at", "finished_at", "next_attempt_at"),
    "import_batches": ("id", "operation_id", "status", "selected_count", "estimated_total_bytes", "estimated_added_bytes", "estimate_is_exact", "disclosure_accepted_at", "created_at", "finished_at"),
    "import_items": ("id", "batch_id", "source_observation_id", "snapshot_id", "parse_artifact_id", "state", "parse_status", "error_code", "created_at", "finished_at"),
    "parse_artifacts": ("id", "source_snapshot_id", "parser_id", "parser_version", "config_fingerprint", "contract_version", "status", "successful_attempt_id", "output_sha256", "derived_file_sha256", "derived_relative_path", "created_at", "updated_at"),
    "parse_attempts": ("id", "parse_artifact_id", "attempt_number", "status", "executor_version", "started_at", "finished_at", "error_code", "warnings_json", "output_sha256", "derived_file_sha256", "diagnostic_summary_json"),
    "snapshot_parse_preferences": ("source_snapshot_id", "parse_artifact_id", "row_version", "updated_at", "updated_by_operation_id"),
    "source_documents": ("id", "parse_artifact_id", "title", "metadata_json", "language", "block_count", "warnings_json", "created_at"),
    "parsed_blocks": ("id", "parse_artifact_id", "source_document_id", "block_index", "kind", "text", "locator_json", "metadata_json", "text_sha256"),
    "evidence_refs": ("id", "entity_type", "entity_id", "parse_artifact_id", "parsed_block_id", "locator_json", "quote_hash", "saved_excerpt", "created_at", "created_by_operation_id"),
    "legacy_source_documents_v01": ("id", "path", "sha256", "mime_type", "size_bytes", "modified_at", "imported_at", "read_only", "missing_at", "migration_batch_id", "source_schema_revision", "migration_reason", "preserved_at"),
    "legacy_evidence_refs_v01": ("id", "entity_type", "entity_id", "document_id", "version_id", "section", "page", "slide", "paragraph_id", "char_start", "char_end", "locator_json", "quote_hash", "created_at", "migration_batch_id", "source_schema_revision", "migration_reason", "preserved_at"),
    "domain_events": ("id", "schema_version", "event_type", "workspace_id", "command_id", "operation_id", "aggregate_type", "aggregate_id", "aggregate_version", "actor_type", "payload_json", "deduplication_key", "causation_id", "correlation_id", "created_at", "occurred_at", "processed_at"),
}

LATER_TABLES = {
    "monitoring_roots", "raw_file_events", "pending_path_checks", "paper_version_candidates",
    "application_commands", "audit_changes", "recovery_points", "backup_records",
    "export_records", "restore_operations",
}


def alembic_config(database_path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _upgrade(database_path):
    command.upgrade(alembic_config(database_path), "0001")
    command.upgrade(alembic_config(database_path), "0002")
    return create_engine(f"sqlite:///{database_path.as_posix()}")


def assert_gate1_schema(inspector) -> None:
    actual_tables = set(inspector.get_table_names())
    assert set(GATE1_COLUMNS) <= actual_tables
    assert LATER_TABLES.isdisjoint(actual_tables)
    for table, expected_columns in GATE1_COLUMNS.items():
        assert tuple(column["name"] for column in inspector.get_columns(table)) == expected_columns


def test_0002_creates_exact_gate1_table_and_column_inventory(database_path) -> None:
    engine = _upgrade(database_path)
    try:
        inspector = inspect(engine)
        assert_gate1_schema(inspector)
        assert "monitoring_root_id" not in GATE1_COLUMNS["source_observations"]
        assert "raw_file_event_id" not in GATE1_COLUMNS["source_observation_events"]
        assert "correlation_command_id" not in GATE1_COLUMNS["background_operations"]
        assert "updated_by_command_id" not in GATE1_COLUMNS["snapshot_parse_preferences"]
        assert "created_by_command_id" not in GATE1_COLUMNS["evidence_refs"]
    finally:
        engine.dispose()


def test_0002_installs_gate1_foreign_keys_uniques_checks_and_indexes(database_path) -> None:
    engine = _upgrade(database_path)
    try:
        inspector = inspect(engine)
        snapshot_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("source_snapshots")}
        artifact_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("parse_artifacts")}
        attempt_indexes = {item["name"]: item for item in inspector.get_indexes("parse_attempts")}
        observation_indexes = {item["name"] for item in inspector.get_indexes("source_observations")}
        assert ("sha256",) in snapshot_uniques
        assert ("storage_relative_path",) in snapshot_uniques
        assert ("source_snapshot_id", "parser_id", "parser_version", "config_fingerprint", "contract_version") in artifact_uniques
        assert "ux_parse_attempts_one_succeeded" in attempt_indexes
        assert bool(attempt_indexes["ux_parse_attempts_one_succeeded"]["unique"]) is True
        assert "ix_source_observations_normalized_path_hash" in observation_indexes

        with engine.connect() as connection:
            snapshot_fks = {
                (row["from"], row["table"], row["on_delete"])
                for row in connection.execute(text("PRAGMA foreign_key_list(source_snapshots)")).mappings()
            }
        assert snapshot_fks == {('created_by_operation_id', 'background_operations', 'RESTRICT')}
        assert any("row_version >= 1" in str(item["sqltext"]) for item in inspector.get_check_constraints("source_observations"))
        assert any("status IN" in str(item["sqltext"]) for item in inspector.get_check_constraints("parse_artifacts"))
    finally:
        engine.dispose()


def test_0002_accepts_complete_domain_event_v2_system_envelope(database_path) -> None:
    engine = _upgrade(database_path)
    event = {
        "id": "40000000-0000-0000-0000-000000000001",
        "schema_version": "2.0",
        "event_type": "maintenance.migration_completed",
        "workspace_id": "40000000-0000-0000-0000-000000000002",
        "command_id": None,
        "operation_id": "40000000-0000-0000-0000-000000000003",
        "aggregate_type": "MigrationBatch",
        "aggregate_id": "40000000-0000-0000-0000-000000000004",
        "aggregate_version": None,
        "actor_type": "system",
        "payload_json": json.dumps({"counts_digest": "a" * 64}, separators=(",", ":")),
        "deduplication_key": "migration-completed-1",
        "causation_id": None,
        "correlation_id": "40000000-0000-0000-0000-000000000005",
        "created_at": "2026-07-16T00:00:00Z",
        "occurred_at": "2026-07-16T00:00:00Z",
        "processed_at": None,
    }
    try:
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO domain_events
                (id,schema_version,event_type,workspace_id,command_id,operation_id,aggregate_type,aggregate_id,
                 aggregate_version,actor_type,payload_json,deduplication_key,causation_id,correlation_id,
                 created_at,occurred_at,processed_at)
                VALUES (:id,:schema_version,:event_type,:workspace_id,:command_id,:operation_id,:aggregate_type,:aggregate_id,
                 :aggregate_version,:actor_type,:payload_json,:deduplication_key,:causation_id,:correlation_id,
                 :created_at,:occurred_at,:processed_at)"""), event)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT schema_version FROM domain_events WHERE id=:id"), {"id": event["id"]}) == "2.0"
    finally:
        engine.dispose()
