import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text


def alembic_config(database_path):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _seed_gate1(database_path):
    config = alembic_config(database_path)
    command.upgrade(config, "0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    payload = '{ "legacy": true, "order": [3, 2, 1] }'
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO source_observations
                    (id,original_path,normalized_path,normalized_path_hash,original_filename,
                     current_snapshot_id,availability_status,baseline_only,size_bytes,modified_at,
                     file_id_hint,volume_serial_hint,first_seen_at,last_seen_at,missing_at,row_version)
                    VALUES
                    ('10000000-0000-0000-0000-000000000001','C:/Research/paper.pdf',
                     'c:/research/paper.pdf',:path_hash,'paper.pdf',NULL,'available',1,123,
                     '2026-07-17T00:00:00Z',NULL,NULL,'2026-07-17T00:00:00Z',
                     '2026-07-17T00:00:00Z',NULL,1)"""
                ),
                {"path_hash": "a" * 64},
            )
            connection.execute(
                text(
                    """INSERT INTO domain_events
                    (id,schema_version,event_type,workspace_id,command_id,operation_id,
                     aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
                     deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at)
                    VALUES
                    ('20000000-0000-0000-0000-000000000001','1.0','document.imported',
                     NULL,NULL,NULL,'SourceDocument','10000000-0000-0000-0000-000000000001',
                     NULL,NULL,:payload,'gate2-conservation',NULL,NULL,
                     '2026-07-17T00:00:00Z',NULL,NULL)"""
                ),
                {"payload": payload},
            )
    finally:
        engine.dispose()
    return config, payload


def test_0002_upgrades_to_0003_without_changing_gate1_facts(gate2_database_path) -> None:
    config, payload = _seed_gate1(gate2_database_path)
    command.upgrade(config, "0003")

    with sqlite3.connect(gate2_database_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
        assert connection.execute("SELECT count(*) FROM source_observations").fetchone()[0] == 1
        stored = connection.execute(
            "SELECT payload_json FROM domain_events WHERE deduplication_key='gate2-conservation'"
        ).fetchone()[0]
        assert stored.encode("utf-8") == payload.encode("utf-8")
        assert connection.execute("SELECT count(*) FROM source_snapshots").fetchone()[0] == 0


def test_0003_downgrade_restores_exact_0002_gate_boundary(gate2_database_path) -> None:
    config, _ = _seed_gate1(gate2_database_path)
    command.upgrade(config, "0003")
    command.downgrade(config, "0002")

    engine = create_engine(f"sqlite:///{gate2_database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert not {
            "monitoring_roots", "raw_file_events", "raw_event_pending_links",
            "pending_path_checks", "reconciliation_runs", "paper_version_candidates",
        } & tables
        assert "monitoring_root_id" not in {
            column["name"] for column in inspect(engine).get_columns("source_observations")
        }
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            assert connection.scalar(text("SELECT count(*) FROM source_observations")) == 1
    finally:
        engine.dispose()


def test_mid_0003_failure_rolls_back_to_startable_0002(gate2_database_path) -> None:
    config, payload = _seed_gate1(gate2_database_path)
    config.attributes["inject_0003_failure_after"] = "gate2_tables"
    with pytest.raises(RuntimeError, match="injected 0003 failure after gate2 tables"):
        command.upgrade(config, "0003")

    engine = create_engine(f"sqlite:///{gate2_database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            assert connection.scalar(text("SELECT count(*) FROM source_observations")) == 1
            stored = connection.scalar(
                text("SELECT payload_json FROM domain_events WHERE deduplication_key='gate2-conservation'")
            )
            assert stored.encode("utf-8") == payload.encode("utf-8")
        assert "monitoring_roots" not in inspector.get_table_names()
    finally:
        engine.dispose()
