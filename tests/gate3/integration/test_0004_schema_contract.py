from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(path):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return config


EXPECTED_COLUMNS = {
    "application_commands": {
        "id", "command_type", "contract_version", "idempotency_key",
        "request_fingerprint", "actor_type", "actor_id",
        "permission_context_json", "status", "requested_at", "started_at",
        "committed_at", "failed_at", "recovery_point_id",
        "undo_of_command_id", "result_summary_json", "error_code",
        "migration_batch_id",
    },
    "audit_changes": {
        "id", "command_id", "change_index", "entity_type", "entity_id",
        "operation", "before_schema_version", "before_json",
        "after_schema_version", "after_json", "changed_fields_json",
        "before_row_version", "after_row_version", "created_at",
    },
    "recovery_points": {
        "id", "command_id", "status", "promoted_generation",
        "physical_state", "database_sha256", "schema_revision",
        "snapshot_count", "snapshot_manifest_hash", "manifest_json",
        "created_at", "verified_at", "promoted_at",
    },
    "recovery_slots": {
        "workspace_id", "slot_name", "recovery_point_id", "generation",
        "updated_at",
    },
    "legacy_paper_versions_v01": {
        "id", "legacy_row_id", "original_table", "original_row_json",
        "paper_id", "source_document_id", "parent_version_id", "is_current",
        "version_label", "created_at", "reason_code", "migration_batch_id",
        "source_schema_revision", "migrated_at",
    },
    "legacy_dependent_records_v01": {
        "id", "original_table", "legacy_row_id", "original_row_json",
        "dependency_ids_json", "reason_code", "migration_batch_id",
        "source_schema_revision", "migrated_at",
    },
}


def test_0004_creates_only_the_declared_gate3_schema(tmp_path) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    command.upgrade(_config(gate3_database_path), "0004")
    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_COLUMNS.keys() <= tables
        assert not {"backup_records", "export_records", "maintenance_operations"} & tables
        for table, expected in EXPECTED_COLUMNS.items():
            assert {column["name"] for column in inspector.get_columns(table)} == expected
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()


def test_0004_installs_command_restrict_fks_and_active_relation_index(
    tmp_path,
) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    command.upgrade(_config(gate3_database_path), "0004")
    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        paper_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], fk["options"].get("ondelete"))
            for fk in inspector.get_foreign_keys("papers")
        }
        assert (("created_by_command_id",), "application_commands", "RESTRICT") in paper_fks
        assert (("updated_by_command_id",), "application_commands", "RESTRICT") in paper_fks
        assert (("deleted_by_command_id",), "application_commands", "RESTRICT") in paper_fks
        assert (("current_version_id",), "paper_versions", "SET NULL") in paper_fks

        candidate_fks = inspector.get_foreign_keys("paper_version_candidates")
        assert any(
            fk["constrained_columns"] == ["decided_by_command_id"]
            and fk["referred_table"] == "application_commands"
            and fk["options"].get("ondelete") == "RESTRICT"
            for fk in candidate_fks
        )
        event_fks = inspector.get_foreign_keys("domain_events")
        assert any(
            fk["constrained_columns"] == ["command_id"]
            and fk["referred_table"] == "application_commands"
            and fk["options"].get("ondelete") == "RESTRICT"
            for fk in event_fks
        )
        relation_indexes = {
            item["name"]: item for item in inspector.get_indexes("entity_relations")
        }
        assert relation_indexes["ux_entity_relations_active_endpoints"]["unique"]
        assert "lifecycle_state" in str(
            relation_indexes["ux_entity_relations_active_endpoints"]
            .get("dialect_options", {})
            .get("sqlite_where")
        )
    finally:
        engine.dispose()
