from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, text

from test_0004_schema_contract import _config


def test_0004_preserves_unmappable_relation_and_observation_without_loss(
    tmp_path,
) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    command.upgrade(_config(gate3_database_path), "0003")
    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            """INSERT INTO entity_relations
            (id,source_type,source_id,relation_type,target_type,target_id,
             confidence,confirmation_state,created_by_actor_type,
             created_by_actor_id,created_at,updated_at)
            VALUES
            ('51000000-0000-0000-0000-000000000001','PaperVersion',
             '52000000-0000-0000-0000-000000000001','related_to','Paper',
             '53000000-0000-0000-0000-000000000001',NULL,'confirmed','user',
             'legacy-user','2026-07-16T00:00:00Z','2026-07-16T00:00:00Z')"""
        ))
        connection.execute(text(
            """INSERT INTO relation_observations
            (id,relation_id,observed_by_actor_type,observed_by_actor_id,
             provenance_type,confidence,origin_task_id,evidence_ref_id,
             provider_id,model_id,observed_at,observation_key)
            VALUES
            ('54000000-0000-0000-0000-000000000001',
             '51000000-0000-0000-0000-000000000001','user','legacy-user',
             'manual',NULL,NULL,NULL,NULL,NULL,'2026-07-16T00:00:00Z','legacy-observation')"""
        ))
    engine.dispose()

    command.upgrade(_config(gate3_database_path), "0004")
    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            old_relations = connection.scalar(text(
                "SELECT count(*) FROM legacy_dependent_records_v01 "
                "WHERE original_table='entity_relations'"
            ))
            assert connection.scalar(text("SELECT count(*) FROM entity_relations")) == 0
            assert old_relations == 1
            assert connection.scalar(text("SELECT count(*) FROM relation_observations")) == 0
            assert connection.scalar(text(
                "SELECT count(*) FROM legacy_relation_observations_v01"
            )) == 1
            assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()
