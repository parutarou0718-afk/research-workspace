from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, inspect, text

from research_workspace.infrastructure.db.models import PaperVersionCandidateModel


def alembic_config(database_path):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


GATE2_TABLES = {
    "monitoring_roots",
    "raw_file_events",
    "raw_event_pending_links",
    "pending_path_checks",
    "reconciliation_runs",
    "paper_version_candidates",
}

RULE_IDS = {
    "R1_SOURCE_CONTINUITY",
    "R2_REPLACE_CONTINUITY",
    "R3_PAPER_TITLE_TIME",
    "R4_NAME_TITLE_TEXT",
    "R5_ZERO_TEXT_LINEAGE",
}

EXPECTED_COLUMNS = {
    "monitoring_roots": {
        "id", "original_path", "normalized_path", "normalized_path_hash", "status",
        "recursive", "config_json", "config_fingerprint", "watcher_generation",
        "last_event_at", "last_reconciled_at", "created_at", "updated_at", "removed_at",
    },
    "raw_file_events": {
        "id", "monitoring_root_id", "provider", "event_type", "source_path",
        "destination_path", "source_path_hash", "destination_path_hash", "observed_at",
        "ingested_at", "raw_sequence_json", "correlation_hint", "deduplication_key",
    },
    "raw_event_pending_links": {"raw_file_event_id", "pending_path_check_id", "linked_at"},
    "pending_path_checks": {
        "id", "monitoring_root_id", "normalized_path", "normalized_path_hash",
        "first_event_at", "last_event_at", "merged_event_types_json", "state",
        "stability_attempt_count", "next_check_at", "last_failure_code",
        "source_observation_id", "row_version",
    },
    "reconciliation_runs": {
        "id", "monitoring_root_id", "operation_id", "reason", "status",
        "checkpoint_json", "items_seen", "items_estimated",
        "items_suspected_changed", "started_at", "finished_at",
    },
    "paper_version_candidates": {
        "id", "earlier_snapshot_id", "later_snapshot_id", "detector_id",
        "detector_version", "rule_id", "rule_config_fingerprint",
        "direction_rationale_json", "signals_json", "input_observation_ids_json",
        "status", "superseded_by_candidate_id", "row_version", "created_at",
        "decided_at",
    },
}


def _upgrade(database_path):
    command.upgrade(alembic_config(database_path), "0003")


def test_0003_creates_only_declared_gate2_schema(gate2_database_path) -> None:
    _upgrade(gate2_database_path)
    engine = create_engine(f"sqlite:///{gate2_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert GATE2_TABLES <= tables
        for table, columns in EXPECTED_COLUMNS.items():
            assert {column["name"] for column in inspector.get_columns(table)} == columns
        assert "monitoring_root_id" in {
            column["name"] for column in inspector.get_columns("source_observations")
        }
        assert "raw_file_event_id" in {
            column["name"] for column in inspector.get_columns("source_observation_events")
        }
        assert not {"application_commands", "recovery_points", "backup_records"} & tables
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
    finally:
        engine.dispose()


def test_0003_installs_required_uniques_foreign_keys_and_indexes(gate2_database_path) -> None:
    _upgrade(gate2_database_path)
    engine = create_engine(f"sqlite:///{gate2_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        candidate_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("paper_version_candidates")
        }
        assert (
            "earlier_snapshot_id", "later_snapshot_id", "detector_id",
            "detector_version", "rule_config_fingerprint",
        ) in candidate_uniques
        raw_indexes = {
            tuple(item["column_names"]) for item in inspector.get_indexes("raw_file_events")
        }
        assert {
            ("monitoring_root_id", "observed_at"),
            ("source_path_hash", "observed_at"),
            ("correlation_hint",),
        } <= raw_indexes
        candidate_indexes = {
            tuple(item["column_names"])
            for item in inspector.get_indexes("paper_version_candidates")
        }
        assert {("earlier_snapshot_id",), ("later_snapshot_id",)} <= candidate_indexes
        source_fks = inspector.get_foreign_keys("source_observations")
        assert any(
            fk["constrained_columns"] == ["monitoring_root_id"]
            and fk["referred_table"] == "monitoring_roots"
            for fk in source_fks
        )
    finally:
        engine.dispose()


def test_candidate_rule_check_uses_normative_stable_identifiers(gate2_database_path) -> None:
    _upgrade(gate2_database_path)
    engine = create_engine(f"sqlite:///{gate2_database_path.as_posix()}")
    try:
        database_checks = inspect(engine).get_check_constraints("paper_version_candidates")
        database_rule = next(
            item["sqltext"] for item in database_checks if item["name"] == "ck_paper_version_candidates_rule"
        )
        assert all(f"'{rule_id}'" in database_rule for rule_id in RULE_IDS)
        assert "'R1'" not in database_rule

        model_rule = next(
            constraint
            for constraint in PaperVersionCandidateModel.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and constraint.name.endswith("_rule_id_enum")
        )
        model_sql = str(model_rule.sqltext)
        assert all(f"'{rule_id}'" in model_sql for rule_id in RULE_IDS)
        assert "'R1'" not in model_sql
    finally:
        engine.dispose()
