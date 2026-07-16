"""Add Gate 1 immutable import and parse persistence.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from alembic import context, op
from sqlalchemy import text

from research_workspace.infrastructure.db.session import create_migration_safety_image

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SOURCE_REVISION = "0001_foundation_schema"
TARGET_REVISION = "0002_gate1_import_parse"
LEGACY_REASON = "NO_VERIFIED_SNAPSHOT_MAPPING"


def _database_path() -> Path:
    bind = op.get_bind()
    rows = bind.execute(text("PRAGMA database_list")).fetchall()
    main = next(row for row in rows if row[1] == "main")
    return Path(main[2]).resolve()


def _execute_all(statements: tuple[str, ...]) -> None:
    for statement in statements:
        op.execute(statement)


def _committed_revision(database_path: Path) -> str | None:
    """Return only state visible outside the active Alembic transaction."""
    with sqlite3.connect(database_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return None if row is None else str(row[0])


def upgrade() -> None:
    bind = op.get_bind()
    batch_id = uuid4()
    workspace_id = uuid4()
    now = bind.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')")).scalar_one()
    database_path = _database_path()
    committed_revision = _committed_revision(database_path)
    if committed_revision == "0001":
        safety = create_migration_safety_image(
            database_path, batch_id=batch_id, source_revision=SOURCE_REVISION
        )
        backup_identity = str(safety.database_path)
    elif committed_revision is None:
        # A fresh bootstrap has no prior committed workspace to preserve. Do not
        # create an empty artifact and mislabel it as a migration safety image.
        backup_identity = f"fresh-bootstrap:{batch_id}"
    else:
        raise RuntimeError(f"0002 requires committed revision 0001, got {committed_revision!r}")
    backup_path_hash = hashlib.sha256(backup_identity.encode("utf-8")).hexdigest()

    _execute_all(_GATE1_CORE_DDL)
    bind.execute(
        text("""INSERT INTO workspace_metadata
            (workspace_id,created_at,clean_shutdown,watcher_generation,updated_at)
            VALUES (:workspace_id,:now,1,0,:now)"""),
        {"workspace_id": str(workspace_id), "now": now},
    )
    bind.execute(
        text("""INSERT INTO migration_batches
            (id,source_revision,target_revision,status,pre_migration_backup_path_hash,
             counts_json,exceptions_json,started_at,finished_at)
            VALUES (:id,:source,:target,'running',:backup_hash,'{}','[]',:now,NULL)"""),
        {
            "id": str(batch_id),
            "source": SOURCE_REVISION,
            "target": TARGET_REVISION,
            "backup_hash": backup_path_hash,
            "now": now,
        },
    )

    op.rename_table("source_documents", "legacy_source_documents_v01")
    op.rename_table("evidence_refs", "legacy_evidence_refs_v01")
    for table_name in ("legacy_source_documents_v01", "legacy_evidence_refs_v01"):
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN migration_batch_id CHAR(36) "
            f"NOT NULL DEFAULT '{batch_id}'"
        )
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN source_schema_revision VARCHAR(128) "
            f"NOT NULL DEFAULT '{SOURCE_REVISION}'"
        )
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN migration_reason VARCHAR(128) "
            f"NOT NULL DEFAULT '{LEGACY_REASON}'"
        )
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN preserved_at TEXT NOT NULL DEFAULT '{now}'"
        )

    if context.get_context().config.attributes.get("inject_0002_failure_after") == "legacy_renames":
        raise RuntimeError("injected 0002 failure after legacy renames")

    _execute_all(_GATE1_IMPORT_PARSE_DDL)
    _rebuild_domain_events()

    legacy_sources = bind.execute(text("SELECT count(*) FROM legacy_source_documents_v01")).scalar_one()
    legacy_evidence = bind.execute(text("SELECT count(*) FROM legacy_evidence_refs_v01")).scalar_one()
    counts = {
        "active_evidence_refs": 0,
        "active_source_documents": 0,
        "legacy_evidence_refs": legacy_evidence,
        "legacy_source_documents": legacy_sources,
        "source_snapshots": 0,
    }
    bind.execute(
        text("""UPDATE migration_batches
            SET status='committed', counts_json=:counts, exceptions_json='[]', finished_at=:now
            WHERE id=:id"""),
        {
            "counts": json.dumps(counts, sort_keys=True, separators=(",", ":")),
            "now": now,
            "id": str(batch_id),
        },
    )


def _rebuild_domain_events() -> None:
    op.rename_table("domain_events", "domain_events_v01_staging")
    op.execute(_DOMAIN_EVENTS_DDL)
    op.execute("""INSERT INTO domain_events
        (id,schema_version,event_type,workspace_id,command_id,operation_id,
         aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
         deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at)
        SELECT id,'1.0',event_type,NULL,NULL,NULL,aggregate_type,aggregate_id,NULL,NULL,
               payload_json,deduplication_key,causation_id,correlation_id,created_at,NULL,processed_at
        FROM domain_events_v01_staging""")
    op.drop_table("domain_events_v01_staging")


def downgrade() -> None:
    raise RuntimeError("0002 downgrade is intentionally unsupported; restore the verified safety image")


_GATE1_CORE_DDL = (
    """CREATE TABLE workspace_metadata (
        workspace_id CHAR(36) NOT NULL PRIMARY KEY, created_at TEXT NOT NULL,
        clean_shutdown BOOLEAN DEFAULT 1 NOT NULL, watcher_generation INTEGER DEFAULT 0 NOT NULL,
        updated_at TEXT NOT NULL,
        CONSTRAINT ck_workspace_metadata_watcher_generation CHECK (watcher_generation >= 0))""",
    """CREATE TABLE migration_batches (
        id CHAR(36) NOT NULL PRIMARY KEY, source_revision VARCHAR(128) NOT NULL,
        target_revision VARCHAR(128) NOT NULL, status VARCHAR(64) NOT NULL,
        pre_migration_backup_path_hash CHAR(64) NOT NULL, counts_json TEXT NOT NULL,
        exceptions_json TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
        CONSTRAINT ck_migration_batches_status CHECK
          (status IN ('planned','running','validated','committed','failed','rolled_back')),
        CONSTRAINT ck_migration_batches_backup_hash CHECK
          (length(pre_migration_backup_path_hash)=64 AND pre_migration_backup_path_hash NOT GLOB '*[^0-9a-f]*'))""",
    """CREATE TABLE background_operations (
        id CHAR(36) NOT NULL PRIMARY KEY, operation_type VARCHAR(128) NOT NULL,
        status VARCHAR(64) NOT NULL, work_plan_fingerprint CHAR(64) NOT NULL,
        permission_context_json TEXT NOT NULL, result_summary_json TEXT, error_code VARCHAR(128),
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, cancel_requested_at TEXT,
        CONSTRAINT ck_background_operations_status CHECK
          (status IN ('planned','running','retry_wait','completed','failed','cancelled','manual_attention')),
        CONSTRAINT ck_background_operations_fingerprint CHECK
          (length(work_plan_fingerprint)=64 AND work_plan_fingerprint NOT GLOB '*[^0-9a-f]*'))""",
)


_GATE1_IMPORT_PARSE_DDL = (
    """CREATE TABLE source_snapshots (
        id CHAR(36) NOT NULL PRIMARY KEY, sha256 CHAR(64) NOT NULL,
        size_bytes INTEGER NOT NULL, mime_type VARCHAR(255) NOT NULL,
        storage_relative_path TEXT NOT NULL, created_at TEXT NOT NULL,
        created_by_operation_id CHAR(36) NOT NULL,
        CONSTRAINT uq_source_snapshots_sha256 UNIQUE(sha256),
        CONSTRAINT uq_source_snapshots_storage_path UNIQUE(storage_relative_path),
        CONSTRAINT ck_source_snapshots_sha256 CHECK
          (length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
        CONSTRAINT ck_source_snapshots_size CHECK (size_bytes >= 0),
        CONSTRAINT ck_source_snapshots_mime CHECK (length(trim(mime_type)) > 0),
        CONSTRAINT fk_source_snapshots_operation FOREIGN KEY(created_by_operation_id)
          REFERENCES background_operations(id) ON DELETE RESTRICT)""",
    """CREATE TABLE source_observations (
        id CHAR(36) NOT NULL PRIMARY KEY, original_path TEXT NOT NULL,
        normalized_path TEXT COLLATE NOCASE NOT NULL UNIQUE, normalized_path_hash CHAR(64) NOT NULL,
        original_filename VARCHAR(1024) NOT NULL, current_snapshot_id CHAR(36),
        availability_status VARCHAR(64) NOT NULL, baseline_only BOOLEAN DEFAULT 0 NOT NULL,
        size_bytes INTEGER, modified_at TEXT, file_id_hint VARCHAR(255), volume_serial_hint VARCHAR(255),
        first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, missing_at TEXT, row_version INTEGER DEFAULT 1 NOT NULL,
        CONSTRAINT ck_source_observations_status CHECK
          (availability_status IN ('available','missing','unavailable','permission_denied')),
        CONSTRAINT ck_source_observations_size CHECK (size_bytes IS NULL OR size_bytes >= 0),
        CONSTRAINT ck_source_observations_row_version CHECK (row_version >= 1),
        CONSTRAINT ck_source_observations_times CHECK (last_seen_at >= first_seen_at),
        CONSTRAINT fk_source_observations_snapshot FOREIGN KEY(current_snapshot_id)
          REFERENCES source_snapshots(id) ON DELETE RESTRICT)""",
    "CREATE INDEX ix_source_observations_normalized_path_hash ON source_observations(normalized_path_hash)",
    """CREATE TABLE source_observation_events (
        id CHAR(36) NOT NULL PRIMARY KEY, source_observation_id CHAR(36) NOT NULL,
        event_type VARCHAR(64) NOT NULL, snapshot_id CHAR(36), path_before_hash CHAR(64),
        path_after_hash CHAR(64), facts_json TEXT NOT NULL, observed_at TEXT NOT NULL,
        CONSTRAINT ck_source_observation_events_type CHECK
          (event_type IN ('baseline','verified','changed','moved','renamed','missing','restored','unavailable')),
        CONSTRAINT fk_source_observation_events_observation FOREIGN KEY(source_observation_id)
          REFERENCES source_observations(id) ON DELETE RESTRICT,
        CONSTRAINT fk_source_observation_events_snapshot FOREIGN KEY(snapshot_id)
          REFERENCES source_snapshots(id) ON DELETE RESTRICT)""",
    """CREATE TABLE operation_attempts (
        id CHAR(36) NOT NULL PRIMARY KEY, operation_id CHAR(36) NOT NULL,
        attempt_number INTEGER NOT NULL, status VARCHAR(64) NOT NULL, error_code VARCHAR(128),
        diagnostic_summary_json TEXT, started_at TEXT NOT NULL, finished_at TEXT, next_attempt_at TEXT,
        CONSTRAINT uq_operation_attempts UNIQUE(operation_id,attempt_number),
        CONSTRAINT ck_operation_attempts_number CHECK (attempt_number >= 1),
        CONSTRAINT ck_operation_attempts_status CHECK
          (status IN ('running','retry_scheduled','succeeded','failed','cancelled','outcome_unknown')),
        CONSTRAINT fk_operation_attempts_operation FOREIGN KEY(operation_id)
          REFERENCES background_operations(id) ON DELETE RESTRICT)""",
    """CREATE TABLE import_batches (
        id CHAR(36) NOT NULL PRIMARY KEY, operation_id CHAR(36) NOT NULL UNIQUE,
        status VARCHAR(64) NOT NULL, selected_count INTEGER NOT NULL,
        estimated_total_bytes INTEGER NOT NULL, estimated_added_bytes INTEGER,
        estimate_is_exact BOOLEAN NOT NULL, disclosure_accepted_at TEXT NOT NULL,
        created_at TEXT NOT NULL, finished_at TEXT,
        CONSTRAINT ck_import_batches_status CHECK
          (status IN ('planned','importing','parsing','completed','completed_with_failures','failed','cancelled')),
        CONSTRAINT ck_import_batches_counts CHECK
          (selected_count >= 0 AND estimated_total_bytes >= 0 AND
           (estimated_added_bytes IS NULL OR estimated_added_bytes >= 0)),
        CONSTRAINT fk_import_batches_operation FOREIGN KEY(operation_id)
          REFERENCES background_operations(id) ON DELETE RESTRICT)""",
    """CREATE TABLE parse_artifacts (
        id CHAR(36) NOT NULL PRIMARY KEY, source_snapshot_id CHAR(36) NOT NULL,
        parser_id VARCHAR(255) NOT NULL, parser_version VARCHAR(128) NOT NULL,
        config_fingerprint CHAR(64) NOT NULL, contract_version VARCHAR(32) NOT NULL,
        status VARCHAR(64) NOT NULL, successful_attempt_id CHAR(36) UNIQUE,
        output_sha256 CHAR(64), derived_file_sha256 CHAR(64), derived_relative_path TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        CONSTRAINT uq_parse_artifacts_revision UNIQUE(source_snapshot_id,parser_id,parser_version,config_fingerprint,contract_version),
        CONSTRAINT ck_parse_artifacts_status CHECK
          (status IN ('pending','running','succeeded','failed','cancelled')),
        CONSTRAINT fk_parse_artifacts_snapshot FOREIGN KEY(source_snapshot_id)
          REFERENCES source_snapshots(id) ON DELETE RESTRICT,
        CONSTRAINT fk_parse_artifacts_successful_attempt FOREIGN KEY(successful_attempt_id)
          REFERENCES parse_attempts(id) ON DELETE RESTRICT)""",
    """CREATE TABLE parse_attempts (
        id CHAR(36) NOT NULL PRIMARY KEY, parse_artifact_id CHAR(36) NOT NULL,
        attempt_number INTEGER NOT NULL, status VARCHAR(64) NOT NULL,
        executor_version VARCHAR(128) NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
        error_code VARCHAR(128), warnings_json TEXT NOT NULL, output_sha256 CHAR(64),
        derived_file_sha256 CHAR(64), diagnostic_summary_json TEXT,
        CONSTRAINT uq_parse_attempts_number UNIQUE(parse_artifact_id,attempt_number),
        CONSTRAINT ck_parse_attempts_number CHECK (attempt_number >= 1),
        CONSTRAINT ck_parse_attempts_status CHECK
          (status IN ('pending','running','succeeded','failed','cancelled')),
        CONSTRAINT fk_parse_attempts_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT)""",
    "CREATE UNIQUE INDEX ux_parse_attempts_one_succeeded ON parse_attempts(parse_artifact_id) WHERE status='succeeded'",
    """CREATE TABLE snapshot_parse_preferences (
        source_snapshot_id CHAR(36) NOT NULL PRIMARY KEY, parse_artifact_id CHAR(36) NOT NULL,
        row_version INTEGER NOT NULL, updated_at TEXT NOT NULL, updated_by_operation_id CHAR(36) NOT NULL,
        CONSTRAINT ck_snapshot_parse_preferences_version CHECK (row_version >= 1),
        CONSTRAINT fk_snapshot_parse_preferences_snapshot FOREIGN KEY(source_snapshot_id)
          REFERENCES source_snapshots(id) ON DELETE RESTRICT,
        CONSTRAINT fk_snapshot_parse_preferences_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_snapshot_parse_preferences_operation FOREIGN KEY(updated_by_operation_id)
          REFERENCES background_operations(id) ON DELETE RESTRICT)""",
    """CREATE TABLE source_documents (
        id CHAR(36) NOT NULL PRIMARY KEY, parse_artifact_id CHAR(36) NOT NULL UNIQUE,
        title VARCHAR(1000), metadata_json TEXT NOT NULL, language VARCHAR(64),
        block_count INTEGER NOT NULL, warnings_json TEXT NOT NULL, created_at TEXT NOT NULL,
        CONSTRAINT ck_source_documents_block_count CHECK (block_count >= 0),
        CONSTRAINT fk_source_documents_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT)""",
    """CREATE TABLE parsed_blocks (
        id CHAR(64) NOT NULL PRIMARY KEY, parse_artifact_id CHAR(36) NOT NULL,
        source_document_id CHAR(36) NOT NULL, block_index INTEGER NOT NULL,
        kind VARCHAR(64) NOT NULL, text TEXT NOT NULL, locator_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL, text_sha256 CHAR(64) NOT NULL,
        CONSTRAINT uq_parsed_blocks_index UNIQUE(parse_artifact_id,block_index),
        CONSTRAINT ck_parsed_blocks_index CHECK (block_index >= 0),
        CONSTRAINT ck_parsed_blocks_kind CHECK
          (kind IN ('paragraph','heading','list_item','table','image_alt')),
        CONSTRAINT ck_parsed_blocks_text CHECK (length(text) > 0),
        CONSTRAINT fk_parsed_blocks_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_parsed_blocks_document FOREIGN KEY(source_document_id)
          REFERENCES source_documents(id) ON DELETE RESTRICT)""",
    """CREATE TABLE evidence_refs (
        id CHAR(36) NOT NULL PRIMARY KEY, entity_type VARCHAR(64) NOT NULL,
        entity_id CHAR(36) NOT NULL, parse_artifact_id CHAR(36) NOT NULL,
        parsed_block_id CHAR(64) NOT NULL, locator_json TEXT NOT NULL,
        quote_hash CHAR(64) NOT NULL, saved_excerpt TEXT, created_at TEXT NOT NULL,
        created_by_operation_id CHAR(36) NOT NULL,
        CONSTRAINT ck_evidence_refs_excerpt CHECK
          (saved_excerpt IS NULL OR length(saved_excerpt) <= 20000),
        CONSTRAINT fk_evidence_refs_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT,
        CONSTRAINT fk_evidence_refs_block FOREIGN KEY(parsed_block_id)
          REFERENCES parsed_blocks(id) ON DELETE RESTRICT,
        CONSTRAINT fk_evidence_refs_operation FOREIGN KEY(created_by_operation_id)
          REFERENCES background_operations(id) ON DELETE RESTRICT)""",
    """CREATE TABLE import_items (
        id CHAR(36) NOT NULL PRIMARY KEY, batch_id CHAR(36) NOT NULL,
        source_observation_id CHAR(36) NOT NULL, snapshot_id CHAR(36), parse_artifact_id CHAR(36),
        state VARCHAR(64) NOT NULL, parse_status VARCHAR(64) NOT NULL, error_code VARCHAR(128),
        created_at TEXT NOT NULL, finished_at TEXT,
        CONSTRAINT ck_import_items_state CHECK
          (state IN ('pending','imported','duplicate_content','failed','cancelled')),
        CONSTRAINT ck_import_items_parse_status CHECK
          (parse_status IN ('not_requested','pending','succeeded','failed','cancelled')),
        CONSTRAINT fk_import_items_batch FOREIGN KEY(batch_id)
          REFERENCES import_batches(id) ON DELETE RESTRICT,
        CONSTRAINT fk_import_items_observation FOREIGN KEY(source_observation_id)
          REFERENCES source_observations(id) ON DELETE RESTRICT,
        CONSTRAINT fk_import_items_snapshot FOREIGN KEY(snapshot_id)
          REFERENCES source_snapshots(id) ON DELETE RESTRICT,
        CONSTRAINT fk_import_items_artifact FOREIGN KEY(parse_artifact_id)
          REFERENCES parse_artifacts(id) ON DELETE RESTRICT)""",
)


_DOMAIN_EVENTS_DDL = """CREATE TABLE domain_events (
    id CHAR(36) NOT NULL PRIMARY KEY, schema_version VARCHAR(16) NOT NULL,
    event_type VARCHAR(128) NOT NULL, workspace_id CHAR(36), command_id CHAR(36),
    operation_id CHAR(36), aggregate_type VARCHAR(128) NOT NULL, aggregate_id CHAR(36) NOT NULL,
    aggregate_version INTEGER, actor_type VARCHAR(64), payload_json TEXT NOT NULL,
    deduplication_key VARCHAR(255) NOT NULL UNIQUE, causation_id CHAR(36), correlation_id CHAR(36),
    created_at TEXT NOT NULL, occurred_at TEXT, processed_at TEXT,
    CONSTRAINT ck_domain_events_schema_version CHECK (schema_version IN ('1.0','2.0')),
    CONSTRAINT ck_domain_events_actor_type CHECK (actor_type IS NULL OR actor_type IN ('user','system')),
    CONSTRAINT ck_domain_events_v2_identity CHECK
      (schema_version='1.0' OR (workspace_id IS NOT NULL AND actor_type IS NOT NULL AND occurred_at IS NOT NULL AND
       ((actor_type='user' AND command_id IS NOT NULL) OR (actor_type='system' AND operation_id IS NOT NULL))))
)"""
