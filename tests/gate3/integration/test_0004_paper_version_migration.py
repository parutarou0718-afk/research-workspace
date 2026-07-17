from __future__ import annotations

import json

from alembic import command
from sqlalchemy import create_engine, text

from test_0004_schema_contract import _config


def _seed_versions(path) -> None:
    command.upgrade(_config(path), "0003")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                """INSERT INTO background_operations
                (id,operation_type,status,work_plan_fingerprint,permission_context_json,
                 created_at)
                VALUES
                ('41000000-0000-0000-0000-000000000001','source.snapshot_import',
                 'completed',:hash,'{}','2026-07-17T00:00:00Z')"""
            ), {"hash": "1" * 64})
            connection.execute(text(
                """INSERT INTO source_snapshots
                (id,sha256,size_bytes,mime_type,storage_relative_path,created_at,
                 created_by_operation_id)
                VALUES
                ('42000000-0000-0000-0000-000000000001',:hash,10,
                 'application/pdf','sources/sha256/aa/proven.pdf',
                 '2026-07-17T00:00:00Z',
                 '41000000-0000-0000-0000-000000000001'),
                ('42000000-0000-0000-0000-000000000002',:child_hash,11,
                 'application/pdf','sources/sha256/cc/child.pdf',
                 '2026-07-17T00:00:00Z',
                 '41000000-0000-0000-0000-000000000001')"""
            ), {"hash": "a" * 64, "child_hash": "c" * 64})
            connection.execute(text(
                """INSERT INTO legacy_source_documents_v01
                (id,path,sha256,mime_type,size_bytes,modified_at,imported_at,
                 read_only,missing_at,migration_batch_id,source_schema_revision,
                 migration_reason,preserved_at)
                VALUES
                ('43000000-0000-0000-0000-000000000001','C:/same.pdf',:proven,
                 'application/pdf',10,'2026-07-16T00:00:00Z',
                 '2026-07-16T00:00:00Z',1,NULL,
                 '44000000-0000-0000-0000-000000000001',
                 '0001_foundation_schema','NO_VERIFIED_SNAPSHOT_MAPPING',
                 '2026-07-17T00:00:00Z'),
                ('43000000-0000-0000-0000-000000000002','C:/looks-same.pdf',:unknown,
                 'application/pdf',10,'2026-07-16T00:00:00Z',
                 '2026-07-16T00:00:00Z',1,NULL,
                 '44000000-0000-0000-0000-000000000001',
                 '0001_foundation_schema','NO_VERIFIED_SNAPSHOT_MAPPING',
                 '2026-07-17T00:00:00Z'),
                ('43000000-0000-0000-0000-000000000003','C:/child.pdf',:child,
                 'application/pdf',11,'2026-07-16T00:00:00Z',
                 '2026-07-16T00:00:00Z',1,NULL,
                 '44000000-0000-0000-0000-000000000001',
                 '0001_foundation_schema','NO_VERIFIED_SNAPSHOT_MAPPING',
                 '2026-07-17T00:00:00Z')"""
            ), {"proven": "a" * 64, "unknown": "b" * 64, "child": "c" * 64})
            connection.execute(text(
                """INSERT INTO papers
                (id,title,status,current_version_id,created_at,updated_at,deleted_at)
                VALUES
                ('45000000-0000-0000-0000-000000000001','Mapped','active',NULL,
                 '2026-07-16T00:00:00Z','2026-07-16T00:00:00Z',NULL),
                ('45000000-0000-0000-0000-000000000002','Legacy','active',NULL,
                 '2026-07-16T00:00:00Z','2026-07-16T00:00:00Z',NULL)"""
            ))
            connection.execute(text(
                """INSERT INTO paper_versions
                (id,paper_id,source_document_id,version_label,parent_version_id,
                 is_current,created_at)
                VALUES
                ('46000000-0000-0000-0000-000000000001',
                 '45000000-0000-0000-0000-000000000001',
                 '43000000-0000-0000-0000-000000000001','Draft',NULL,1,
                 '2026-07-16T00:00:00Z'),
                ('46000000-0000-0000-0000-000000000002',
                 '45000000-0000-0000-0000-000000000002',
                 '43000000-0000-0000-0000-000000000002','Draft',NULL,1,
                 '2026-07-16T00:00:00Z'),
                ('46000000-0000-0000-0000-000000000003',
                 '45000000-0000-0000-0000-000000000001',
                 '43000000-0000-0000-0000-000000000003','Revision',
                 '46000000-0000-0000-0000-000000000001',0,
                 '2026-07-16T00:00:00Z')"""
            ))
            connection.execute(text(
                """UPDATE papers SET current_version_id =
                CASE id
                  WHEN '45000000-0000-0000-0000-000000000001'
                    THEN '46000000-0000-0000-0000-000000000001'
                  ELSE '46000000-0000-0000-0000-000000000002'
                END"""
            ))
    finally:
        engine.dispose()


def test_0004_maps_only_hash_proven_versions_and_conserves_every_old_row(
    tmp_path,
) -> None:
    gate3_database_path = tmp_path / "gate3-workspace.db"
    _seed_versions(gate3_database_path)
    command.upgrade(_config(gate3_database_path), "0004")
    engine = create_engine(f"sqlite:///{gate3_database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            migrated = connection.scalar(text("SELECT count(*) FROM paper_versions"))
            legacy = connection.scalar(text("SELECT count(*) FROM legacy_paper_versions_v01"))
            assert migrated == 2
            assert legacy == 1
            assert migrated + legacy == 3
            rows = connection.execute(text(
                "SELECT source_snapshot_id,version_label,normalized_version_label "
                "FROM paper_versions ORDER BY id"
            )).all()
            assert rows[0] == (
                "42000000-0000-0000-0000-000000000001", "Draft", "draft"
            )
            assert rows[1] == (
                "42000000-0000-0000-0000-000000000002", "Revision", "revision"
            )
            legacy_row = connection.execute(text(
                "SELECT legacy_row_id,reason_code,original_row_json "
                "FROM legacy_paper_versions_v01"
            )).one()
            assert legacy_row[0] == "46000000-0000-0000-0000-000000000002"
            assert legacy_row[1] == "NO_VERIFIED_SNAPSHOT_MAPPING"
            assert json.loads(legacy_row[2])["source_document_id"].endswith("0002")
            currents = dict(connection.execute(text(
                "SELECT id,current_version_id FROM papers ORDER BY id"
            )).all())
            assert currents["45000000-0000-0000-0000-000000000001"].endswith("0001")
            assert currents["45000000-0000-0000-0000-000000000002"] is None
            counts = json.loads(connection.execute(text(
                "SELECT counts_json FROM migration_batches "
                "WHERE target_revision='0004_gate3_protected_crud'"
            )).scalar_one())
            edge = connection.execute(text(
                """SELECT source_id,target_id FROM entity_relations
                WHERE relation_type='version_successor_of'"""
            )).one()
            assert edge == (
                "46000000-0000-0000-0000-000000000003",
                "46000000-0000-0000-0000-000000000001",
            )
            assert counts["old_paper_versions"] == 3
            assert counts["migrated_paper_versions"] == 2
            assert counts["legacy_paper_versions"] == 1
    finally:
        engine.dispose()
