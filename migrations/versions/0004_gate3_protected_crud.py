"""Add Gate 3 protected CRUD, audit, recovery, and formal version graph.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata
from uuid import NAMESPACE_URL, uuid4, uuid5

from alembic import context, op
from sqlalchemy import text

from research_workspace.infrastructure.db.session import create_migration_safety_image


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SOURCE_REVISION = "0003_gate2_monitoring"
TARGET_REVISION = "0004_gate3_protected_crud"


def _database_path() -> Path:
    rows = op.get_bind().exec_driver_sql("PRAGMA database_list").all()
    return Path(next(row for row in rows if row[1] == "main")[2]).resolve()


def _committed_revision(path: Path) -> str | None:
    with sqlite3.connect(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return None if row is None else str(row[0])


def _now(bind) -> str:
    return bind.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')")).scalar_one()


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.strip())
    return " ".join(normalized.split()).casefold()


def _json_row(row) -> str:
    return json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def upgrade() -> None:
    bind = op.get_bind()
    database_path = _database_path()
    committed_revision = _committed_revision(database_path)
    if committed_revision not in {None, "0003"}:
        raise RuntimeError("0004 requires committed revision 0003")
    batch_id = uuid4()
    safety = (
        create_migration_safety_image(
            database_path, batch_id=batch_id, source_revision=SOURCE_REVISION
        )
        if committed_revision == "0003"
        else None
    )
    now = _now(bind)
    backup_identity = (
        str(safety.database_path) if safety is not None else f"fresh-bootstrap:{batch_id}"
    )
    backup_hash = hashlib.sha256(backup_identity.encode()).hexdigest()

    for ddl in _CORE_DDL:
        op.execute(ddl)
    bind.execute(
        text(
            """INSERT INTO migration_batches
            (id,source_revision,target_revision,status,pre_migration_backup_path_hash,
             counts_json,exceptions_json,started_at,finished_at)
            VALUES (:id,:source,:target,'running',:backup,'{}','[]',:now,NULL)"""
        ),
        {
            "id": str(batch_id), "source": SOURCE_REVISION, "target": TARGET_REVISION,
            "backup": backup_hash, "now": now,
        },
    )
    command_id = uuid5(NAMESPACE_URL, f"research-workspace:migration:{batch_id}")
    workspace_id = bind.execute(text("SELECT workspace_id FROM workspace_metadata")).scalar_one()
    permission = json.dumps(
        {
            "schema_version": "1.0", "actor_type": "system", "actor_id": None,
            "workspace_id": workspace_id, "capabilities": [], "scope_refs": [],
            "path_scopes": [], "network_allowed": False, "granted_at": now,
            "policy_version": "migration-0004",
            "authorization_decision_id": str(
                uuid5(NAMESPACE_URL, f"research-workspace:migration-auth:{batch_id}")
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    bind.execute(
        text(
            """INSERT INTO application_commands
            (id,command_type,contract_version,idempotency_key,request_fingerprint,
             actor_type,actor_id,permission_context_json,status,requested_at,
             started_at,committed_at,failed_at,recovery_point_id,undo_of_command_id,
             result_summary_json,error_code,migration_batch_id)
            VALUES (:id,'system.migration_adopt_v01','1.0',:key,:fingerprint,
                    'system',NULL,:permission,'committed',:now,:now,:now,NULL,NULL,
                    NULL,:result,NULL,:batch)"""
        ),
        {
            "id": str(command_id), "key": f"migration-adopt:{batch_id}",
            "fingerprint": hashlib.sha256(str(batch_id).encode()).hexdigest(),
            "permission": permission,
            "result": '{"affected_count":0,"affected_entity_ids":[],"replayed":false}',
            "batch": str(batch_id), "now": now,
        },
    )

    for old, staging in _STAGING_TABLES:
        op.rename_table(old, staging)
    if context.config.attributes.get("inject_0004_failure_after") == "legacy_staging":
        raise RuntimeError("injected 0004 failure after legacy staging")

    for ddl in _REPLACEMENT_DDL:
        op.execute(ddl)

    old_versions = tuple(bind.execute(text("SELECT * FROM paper_versions_v01_staging")).mappings())
    old_relations = tuple(bind.execute(text("SELECT * FROM entity_relations_v01_staging")).mappings())
    old_observations = tuple(
        bind.execute(text("SELECT * FROM relation_observations_v01_staging")).mappings()
    )

    bind.execute(
        text(
            """INSERT INTO papers
            (id,title,status,current_version_id,created_at,updated_at,deleted_at,
             row_version,created_by_command_id,updated_by_command_id,deleted_by_command_id)
            SELECT id,title,status,NULL,created_at,updated_at,deleted_at,1,:command,:command,
                   CASE WHEN deleted_at IS NULL THEN NULL ELSE :command END
            FROM papers_v01_staging"""
        ),
        {"command": str(command_id)},
    )
    bind.execute(
        text(
            """INSERT INTO ideas
            (id,title,content,status,origin_type,created_at,updated_at,deleted_at,
             row_version,created_by_command_id,updated_by_command_id,deleted_by_command_id)
            SELECT id,title,content,status,origin_type,created_at,updated_at,deleted_at,
                   1,:command,:command,
                   CASE WHEN deleted_at IS NULL THEN NULL ELSE :command END
            FROM ideas_v01_staging"""
        ),
        {"command": str(command_id)},
    )

    snapshot_by_document = {
        row.legacy_id: row.snapshot_id
        for row in bind.execute(
            text(
                """SELECT legacy.id AS legacy_id, snapshot.id AS snapshot_id
                FROM legacy_source_documents_v01 legacy
                JOIN source_snapshots snapshot ON snapshot.sha256=legacy.sha256"""
            )
        )
    }
    migrated_versions: set[str] = set()
    label_keys: set[tuple[str, str]] = set()
    snapshot_keys: set[tuple[str, str]] = set()
    exceptions: list[dict[str, str]] = []
    for row in old_versions:
        source_snapshot_id = snapshot_by_document.get(row["source_document_id"])
        normalized_label = _normalize_label(row["version_label"])
        reason = None
        if source_snapshot_id is None:
            reason = "NO_VERIFIED_SNAPSHOT_MAPPING"
        elif (row["paper_id"], source_snapshot_id) in snapshot_keys:
            reason = "DUPLICATE_SNAPSHOT_MEMBERSHIP"
        elif (row["paper_id"], normalized_label) in label_keys:
            reason = "DUPLICATE_VERSION_LABEL"
        if reason:
            legacy_id = uuid5(NAMESPACE_URL, f"legacy-paper-version:{batch_id}:{row['id']}")
            bind.execute(
                text(
                    """INSERT INTO legacy_paper_versions_v01
                    (id,legacy_row_id,original_table,original_row_json,paper_id,
                     source_document_id,parent_version_id,is_current,version_label,
                     created_at,reason_code,migration_batch_id,source_schema_revision,
                     migrated_at)
                    VALUES (:id,:legacy,'paper_versions',:original,:paper,:source,:parent,
                            :current,:label,:created,:reason,:batch,'0001_foundation_schema',
                            :now)"""
                ),
                {
                    "id": str(legacy_id), "legacy": row["id"], "original": _json_row(row),
                    "paper": row["paper_id"], "source": row["source_document_id"],
                    "parent": row["parent_version_id"], "current": row["is_current"],
                    "label": row["version_label"], "created": row["created_at"],
                    "reason": reason, "batch": str(batch_id), "now": now,
                },
            )
            exceptions.append({"entity_id": row["id"], "reason_code": reason})
            continue
        bind.execute(
            text(
                """INSERT INTO paper_versions
                (id,paper_id,source_snapshot_id,context_parse_artifact_id,version_label,
                 normalized_version_label,lifecycle_state,row_version,created_at,
                 confirmed_by_command_id,updated_at,updated_by_command_id,retracted_at,
                 retracted_by_command_id)
                VALUES (:id,:paper,:snapshot,NULL,:label,:normalized,'active',1,:created,
                        :command,:created,:command,NULL,NULL)"""
            ),
            {
                "id": row["id"], "paper": row["paper_id"], "snapshot": source_snapshot_id,
                "label": row["version_label"].strip(), "normalized": normalized_label,
                "created": row["created_at"], "command": str(command_id),
            },
        )
        migrated_versions.add(row["id"])
        label_keys.add((row["paper_id"], normalized_label))
        snapshot_keys.add((row["paper_id"], source_snapshot_id))

    current_by_paper: dict[str, list[str]] = {}
    for row in old_versions:
        if row["is_current"] and row["id"] in migrated_versions:
            current_by_paper.setdefault(row["paper_id"], []).append(row["id"])
    for paper_id, current_ids in current_by_paper.items():
        if len(current_ids) == 1:
            bind.execute(
                text("UPDATE papers SET current_version_id=:version WHERE id=:paper"),
                {"version": current_ids[0], "paper": paper_id},
            )
        else:
            exceptions.append(
                {"entity_id": paper_id, "reason_code": "MULTIPLE_LEGACY_CURRENT_VERSIONS"}
            )

    bind.execute(
        text(
            """INSERT INTO submissions
            (id,paper_id,venue,status,submitted_at,deadline_at,active_version_id,
             created_at,updated_at,deleted_at,row_version,created_by_command_id,
             updated_by_command_id,deleted_by_command_id)
            SELECT id,paper_id,venue,status,submitted_at,deadline_at,
                   CASE WHEN active_version_id IN
                     (SELECT id FROM paper_versions) THEN active_version_id ELSE NULL END,
                   created_at,updated_at,deleted_at,1,:command,:command,
                   CASE WHEN deleted_at IS NULL THEN NULL ELSE :command END
            FROM submissions_v01_staging"""
        ),
        {"command": str(command_id)},
    )
    _migrate_parent_edges(bind, old_versions, migrated_versions, command_id, now, exceptions)
    migrated_relations = _migrate_relations(
        bind, old_relations, migrated_versions, command_id, batch_id, now, exceptions
    )
    _migrate_observations(
        bind, old_observations, migrated_relations, batch_id, now, exceptions
    )
    _migrate_notes(bind, batch_id, now, exceptions)
    _rebuild_legacy_evidence(bind)
    _rebuild_candidates(bind)
    _rebuild_domain_events(bind)

    op.execute("PRAGMA defer_foreign_keys=ON")
    for staging in (
        "relation_observations_v01_staging", "entity_relations_v01_staging",
        "submissions_v01_staging", "ideas_v01_staging", "notes_v01_staging",
        "paper_versions_v01_staging", "papers_v01_staging",
        "paper_version_candidates_v02_staging", "domain_events_v02_staging",
    ):
        op.drop_table(staging)

    counts = {
        "old_paper_versions": len(old_versions),
        "migrated_paper_versions": len(migrated_versions),
        "legacy_paper_versions": len(old_versions) - len(migrated_versions),
        "old_entity_relations": len(old_relations),
        "migrated_entity_relations": len(migrated_relations),
        "legacy_entity_relations": len(old_relations) - len(migrated_relations),
        "old_relation_observations": len(old_observations),
        "migrated_relation_observations": bind.execute(
            text("SELECT count(*) FROM relation_observations")
        ).scalar_one(),
        "legacy_relation_observations": bind.execute(
            text("SELECT count(*) FROM legacy_relation_observations_v01")
        ).scalar_one(),
    }
    bind.execute(
        text(
            """UPDATE migration_batches SET status='committed',counts_json=:counts,
               exceptions_json=:exceptions,finished_at=:now WHERE id=:id"""
        ),
        {
            "counts": json.dumps(counts, sort_keys=True, separators=(",", ":")),
            "exceptions": json.dumps(exceptions, sort_keys=True, separators=(",", ":")),
            "now": now, "id": str(batch_id),
        },
    )


def _migrate_parent_edges(bind, rows, migrated, command_id, now, exceptions) -> None:
    papers = {row["id"]: row["paper_id"] for row in rows}
    for row in rows:
        parent = row["parent_version_id"]
        if not parent:
            continue
        if row["id"] not in migrated or parent not in migrated or papers.get(parent) != row["paper_id"]:
            exceptions.append(
                {"entity_id": row["id"], "reason_code": "INVALID_PARENT_REFERENCE"}
            )
            continue
        relation_id = uuid5(NAMESPACE_URL, f"legacy-parent:{row['id']}:{parent}")
        bind.execute(
            text(
                """INSERT OR IGNORE INTO entity_relations
                (id,source_type,source_id,relation_type,target_type,target_id,
                 confidence,confirmation_state,lifecycle_state,
                 superseded_by_relation_id,created_by_actor_type,created_by_actor_id,
                 created_by_command_id,row_version,created_at,updated_at,retracted_at,
                 retracted_by_command_id)
                VALUES (:id,'PaperVersion',:source,'version_successor_of',
                        'PaperVersion',:target,NULL,'confirmed','active',NULL,
                        'system',NULL,:command,1,:now,:now,NULL,NULL)"""
            ),
            {
                "id": str(relation_id), "source": row["id"], "target": parent,
                "command": str(command_id), "now": now,
            },
        )


def _legacy_dependent(bind, table, row, reason, batch_id, now) -> None:
    legacy_id = uuid5(NAMESPACE_URL, f"legacy-dependent:{batch_id}:{table}:{row['id']}")
    bind.execute(
        text(
            """INSERT INTO legacy_dependent_records_v01
            (id,original_table,legacy_row_id,original_row_json,dependency_ids_json,
             reason_code,migration_batch_id,source_schema_revision,migrated_at)
            VALUES (:id,:table,:row,:original,:dependencies,:reason,:batch,
                    '0001_foundation_schema',:now)"""
        ),
        {
            "id": str(legacy_id), "table": table, "row": row["id"],
            "original": _json_row(row),
            "dependencies": json.dumps(
                {key: value for key, value in row.items() if key.endswith("_id")},
                sort_keys=True, separators=(",", ":"),
            ),
            "reason": reason, "batch": str(batch_id), "now": now,
        },
    )


def _migrate_relations(bind, rows, migrated_versions, command_id, batch_id, now, exceptions):
    migrated: set[str] = set()
    for row in sorted(rows, key=lambda item: item["id"]):
        endpoints_ok = all(
            kind != "PaperVersion" or entity_id in migrated_versions
            for kind, entity_id in (
                (row["source_type"], row["source_id"]),
                (row["target_type"], row["target_id"]),
            )
        )
        if not endpoints_ok:
            _legacy_dependent(
                bind, "entity_relations", row, "UNMAPPABLE_DEPENDENT_REFERENCE",
                batch_id, now,
            )
            exceptions.append(
                {"entity_id": row["id"], "reason_code": "UNMAPPABLE_DEPENDENT_REFERENCE"}
            )
            continue
        try:
            bind.execute(
                text(
                    """INSERT INTO entity_relations
                    (id,source_type,source_id,relation_type,target_type,target_id,
                     confidence,confirmation_state,lifecycle_state,
                     superseded_by_relation_id,created_by_actor_type,
                     created_by_actor_id,created_by_command_id,row_version,created_at,
                     updated_at,retracted_at,retracted_by_command_id)
                    VALUES (:id,:source_type,:source_id,:relation_type,:target_type,
                            :target_id,:confidence,:confirmation,'active',NULL,:actor_type,
                            :actor_id,NULL,1,:created,:updated,NULL,NULL)"""
                ),
                {
                    "id": row["id"], "source_type": row["source_type"],
                    "source_id": row["source_id"], "relation_type": row["relation_type"],
                    "target_type": row["target_type"], "target_id": row["target_id"],
                    "confidence": row["confidence"],
                    "confirmation": row["confirmation_state"],
                    "actor_type": row["created_by_actor_type"],
                    "actor_id": row["created_by_actor_id"],
                    "created": row["created_at"], "updated": row["updated_at"],
                },
            )
        except Exception:
            _legacy_dependent(
                bind, "entity_relations", row, "DUPLICATE_CANONICAL_RELATION",
                batch_id, now,
            )
            exceptions.append(
                {"entity_id": row["id"], "reason_code": "DUPLICATE_CANONICAL_RELATION"}
            )
            continue
        migrated.add(row["id"])
    return migrated


def _migrate_observations(bind, rows, migrated_relations, batch_id, now, exceptions):
    for row in rows:
        evidence_ok = row["evidence_ref_id"] is None or bind.execute(
            text("SELECT 1 FROM evidence_refs WHERE id=:id"),
            {"id": row["evidence_ref_id"]},
        ).first()
        if row["relation_id"] in migrated_relations and evidence_ok:
            bind.execute(
                text(
                    """INSERT INTO relation_observations
                    (id,relation_id,observed_by_actor_type,observed_by_actor_id,
                     provenance_type,confidence,origin_task_id,origin_operation_id,
                     evidence_ref_id,provider_id,model_id,observed_at,observation_key)
                    VALUES (:id,:relation,:actor_type,:actor_id,:provenance,:confidence,
                            :task,NULL,:evidence,:provider,:model,:observed,:key)"""
                ),
                {
                    "id": row["id"], "relation": row["relation_id"],
                    "actor_type": row["observed_by_actor_type"],
                    "actor_id": row["observed_by_actor_id"],
                    "provenance": row["provenance_type"], "confidence": row["confidence"],
                    "task": row["origin_task_id"], "evidence": row["evidence_ref_id"],
                    "provider": row["provider_id"], "model": row["model_id"],
                    "observed": row["observed_at"], "key": row["observation_key"],
                },
            )
        else:
            values = dict(row)
            values.update(
                {
                    "reason": "UNMAPPABLE_DEPENDENT_REFERENCE",
                    "batch": str(batch_id), "revision": "0001_foundation_schema",
                    "now": now,
                }
            )
            bind.execute(text(_LEGACY_OBSERVATION_INSERT), values)
            exceptions.append(
                {"entity_id": row["id"], "reason_code": "UNMAPPABLE_DEPENDENT_REFERENCE"}
            )


def _migrate_notes(bind, batch_id, now, exceptions):
    rows = bind.execute(text("SELECT * FROM notes_v01_staging")).mappings()
    for row in rows:
        source_document = None
        if row["source_document_id"]:
            source_document = bind.execute(
                text(
                    """SELECT document.id FROM legacy_source_documents_v01 legacy
                    JOIN source_snapshots snapshot ON snapshot.sha256=legacy.sha256
                    JOIN parse_artifacts artifact ON artifact.source_snapshot_id=snapshot.id
                                                AND artifact.status='succeeded'
                    JOIN source_documents document ON document.parse_artifact_id=artifact.id
                    WHERE legacy.id=:legacy LIMIT 1"""
                ),
                {"legacy": row["source_document_id"]},
            ).scalar()
            if source_document is None:
                _legacy_dependent(
                    bind, "notes", row, "UNMAPPABLE_DEPENDENT_REFERENCE", batch_id, now
                )
                exceptions.append(
                    {"entity_id": row["id"], "reason_code": "UNMAPPABLE_DEPENDENT_REFERENCE"}
                )
        bind.execute(
            text(
                """INSERT INTO notes
                (id,title,content,source_document_id,created_at,updated_at,deleted_at)
                VALUES (:id,:title,:content,:source,:created,:updated,:deleted)"""
            ),
            {
                "id": row["id"], "title": row["title"], "content": row["content"],
                "source": source_document, "created": row["created_at"],
                "updated": row["updated_at"], "deleted": row["deleted_at"],
            },
        )


def _rebuild_legacy_evidence(bind):
    op.rename_table("legacy_evidence_refs_v01", "legacy_evidence_refs_v01_staging")
    op.execute(_LEGACY_EVIDENCE_DDL)
    op.execute(
        """INSERT INTO legacy_evidence_refs_v01
        SELECT id,entity_type,entity_id,document_id,version_id,section,page,slide,
               paragraph_id,char_start,char_end,locator_json,quote_hash,created_at,
               migration_batch_id,source_schema_revision,migration_reason,preserved_at
        FROM legacy_evidence_refs_v01_staging"""
    )
    op.drop_table("legacy_evidence_refs_v01_staging")


def _rebuild_candidates(bind):
    op.execute(
        """INSERT INTO paper_version_candidates
        (id,earlier_snapshot_id,later_snapshot_id,detector_id,detector_version,
         rule_id,rule_config_fingerprint,direction_rationale_json,signals_json,
         input_observation_ids_json,status,superseded_by_candidate_id,row_version,
         created_at,decided_at,decided_by_command_id)
        SELECT id,earlier_snapshot_id,later_snapshot_id,detector_id,detector_version,
               rule_id,rule_config_fingerprint,direction_rationale_json,signals_json,
               input_observation_ids_json,status,superseded_by_candidate_id,row_version,
               created_at,decided_at,NULL
        FROM paper_version_candidates_v02_staging"""
    )


def _rebuild_domain_events(bind):
    op.execute(
        """INSERT INTO domain_events
        (id,schema_version,event_type,workspace_id,command_id,operation_id,
         aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
         deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at)
        SELECT id,schema_version,event_type,workspace_id,command_id,operation_id,
               aggregate_type,aggregate_id,aggregate_version,actor_type,payload_json,
               deduplication_key,causation_id,correlation_id,created_at,occurred_at,processed_at
        FROM domain_events_v02_staging"""
    )


def downgrade() -> None:
    raise RuntimeError("0004 downgrade is intentionally unsupported; restore the safety image")


_STAGING_TABLES = (
    ("papers", "papers_v01_staging"),
    ("paper_versions", "paper_versions_v01_staging"),
    ("ideas", "ideas_v01_staging"),
    ("submissions", "submissions_v01_staging"),
    ("notes", "notes_v01_staging"),
    ("entity_relations", "entity_relations_v01_staging"),
    ("relation_observations", "relation_observations_v01_staging"),
    ("paper_version_candidates", "paper_version_candidates_v02_staging"),
    ("domain_events", "domain_events_v02_staging"),
)

_CORE_DDL = (
    """CREATE TABLE application_commands (
      id CHAR(36) PRIMARY KEY NOT NULL, command_type VARCHAR(128) NOT NULL,
      contract_version VARCHAR(32) NOT NULL, idempotency_key VARCHAR(255) NOT NULL UNIQUE,
      request_fingerprint CHAR(64) NOT NULL, actor_type VARCHAR(64) NOT NULL,
      actor_id VARCHAR(255), permission_context_json TEXT NOT NULL,
      status VARCHAR(64) NOT NULL, requested_at TEXT NOT NULL, started_at TEXT,
      committed_at TEXT, failed_at TEXT, recovery_point_id CHAR(36),
      undo_of_command_id CHAR(36) UNIQUE, result_summary_json TEXT,
      error_code VARCHAR(128), migration_batch_id CHAR(36),
      CONSTRAINT ck_application_commands_version CHECK(contract_version='1.0'),
      CONSTRAINT ck_application_commands_actor CHECK(actor_type IN ('user','system')),
      CONSTRAINT ck_application_commands_status CHECK(status IN ('pending','running','committed','failed','cancelled')),
      CONSTRAINT ck_application_commands_hash CHECK(length(request_fingerprint)=64 AND request_fingerprint NOT GLOB '*[^0-9a-f]*'),
      FOREIGN KEY(recovery_point_id) REFERENCES recovery_points(id) ON DELETE RESTRICT,
      FOREIGN KEY(undo_of_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(migration_batch_id) REFERENCES migration_batches(id) ON DELETE RESTRICT)""",
    """CREATE TABLE audit_changes (
      id CHAR(36) PRIMARY KEY NOT NULL, command_id CHAR(36) NOT NULL,
      change_index INTEGER NOT NULL, entity_type VARCHAR(64) NOT NULL,
      entity_id CHAR(36) NOT NULL, operation VARCHAR(64) NOT NULL,
      before_schema_version VARCHAR(32), before_json TEXT,
      after_schema_version VARCHAR(32), after_json TEXT,
      changed_fields_json TEXT NOT NULL, before_row_version INTEGER,
      after_row_version INTEGER, created_at TEXT NOT NULL,
      UNIQUE(command_id,change_index),
      CHECK(change_index>=0),
      CHECK(operation IN ('create','update','soft_delete','restore','confirm','reject','reconsider','retract','undo')),
      FOREIGN KEY(command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE recovery_points (
      id CHAR(36) PRIMARY KEY NOT NULL, command_id CHAR(36) NOT NULL UNIQUE,
      status VARCHAR(64) NOT NULL, promoted_generation INTEGER,
      physical_state VARCHAR(64) NOT NULL, database_sha256 CHAR(64) NOT NULL,
      schema_revision VARCHAR(128) NOT NULL, snapshot_count INTEGER NOT NULL,
      snapshot_manifest_hash CHAR(64) NOT NULL, manifest_json TEXT NOT NULL,
      created_at TEXT NOT NULL, verified_at TEXT, promoted_at TEXT,
      CHECK(status IN ('staging','verified','promoted','rotation_failed','invalid')),
      CHECK(physical_state IN ('staging','active_current','active_previous','superseded','historical_unavailable_after_restore','invalid')),
      CHECK(promoted_generation IS NULL OR promoted_generation>=1),
      CHECK(snapshot_count>=0),
      FOREIGN KEY(command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE recovery_slots (
      workspace_id CHAR(36) NOT NULL, slot_name VARCHAR(32) NOT NULL,
      recovery_point_id CHAR(36) NOT NULL UNIQUE, generation INTEGER NOT NULL,
      updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id,slot_name),
      CHECK(slot_name IN ('current','previous')), CHECK(generation>=1),
      FOREIGN KEY(workspace_id) REFERENCES workspace_metadata(workspace_id) ON DELETE RESTRICT,
      FOREIGN KEY(recovery_point_id) REFERENCES recovery_points(id) ON DELETE RESTRICT)""",
    """CREATE TABLE legacy_paper_versions_v01 (
      id CHAR(36) PRIMARY KEY NOT NULL, legacy_row_id CHAR(36) NOT NULL,
      original_table VARCHAR(128) NOT NULL, original_row_json TEXT NOT NULL,
      paper_id CHAR(36) NOT NULL, source_document_id CHAR(36) NOT NULL,
      parent_version_id CHAR(36), is_current BOOLEAN NOT NULL,
      version_label VARCHAR(128) NOT NULL, created_at TEXT NOT NULL,
      reason_code VARCHAR(128) NOT NULL, migration_batch_id CHAR(36) NOT NULL,
      source_schema_revision VARCHAR(128) NOT NULL, migrated_at TEXT NOT NULL,
      UNIQUE(migration_batch_id,legacy_row_id),
      FOREIGN KEY(migration_batch_id) REFERENCES migration_batches(id) ON DELETE RESTRICT)""",
    "CREATE INDEX ix_legacy_paper_versions_linkage ON legacy_paper_versions_v01(paper_id,source_document_id,parent_version_id)",
    """CREATE TABLE legacy_dependent_records_v01 (
      id CHAR(36) PRIMARY KEY NOT NULL, original_table VARCHAR(128) NOT NULL,
      legacy_row_id CHAR(36) NOT NULL, original_row_json TEXT NOT NULL,
      dependency_ids_json TEXT NOT NULL, reason_code VARCHAR(128) NOT NULL,
      migration_batch_id CHAR(36) NOT NULL, source_schema_revision VARCHAR(128) NOT NULL,
      migrated_at TEXT NOT NULL, UNIQUE(original_table,legacy_row_id,migration_batch_id),
      FOREIGN KEY(migration_batch_id) REFERENCES migration_batches(id) ON DELETE RESTRICT)""",
)

_REPLACEMENT_DDL = (
    """CREATE TABLE papers (
      id CHAR(36) PRIMARY KEY NOT NULL,title VARCHAR(500) NOT NULL,
      status VARCHAR(64) NOT NULL,current_version_id CHAR(36),created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,deleted_at TEXT,row_version INTEGER NOT NULL,
      created_by_command_id CHAR(36) NOT NULL,updated_by_command_id CHAR(36) NOT NULL,
      deleted_by_command_id CHAR(36),
      CHECK(length(trim(title)) BETWEEN 1 AND 500),CHECK(row_version>=1),
      CHECK((deleted_at IS NULL)=(deleted_by_command_id IS NULL)),
      FOREIGN KEY(current_version_id) REFERENCES paper_versions(id) ON DELETE SET NULL,
      FOREIGN KEY(created_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(updated_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(deleted_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE paper_versions (
      id CHAR(36) PRIMARY KEY NOT NULL,paper_id CHAR(36) NOT NULL,
      source_snapshot_id CHAR(36) NOT NULL,context_parse_artifact_id CHAR(36),
      version_label VARCHAR(200) NOT NULL,normalized_version_label VARCHAR(200) NOT NULL,
      lifecycle_state VARCHAR(64) NOT NULL,row_version INTEGER NOT NULL,
      created_at TEXT NOT NULL,confirmed_by_command_id CHAR(36) NOT NULL,
      updated_at TEXT NOT NULL,updated_by_command_id CHAR(36) NOT NULL,
      retracted_at TEXT,retracted_by_command_id CHAR(36),
      UNIQUE(paper_id,source_snapshot_id),UNIQUE(paper_id,normalized_version_label),
      CHECK(lifecycle_state IN ('active','retracted')),CHECK(row_version>=1),
      CHECK((lifecycle_state='active' AND retracted_at IS NULL AND retracted_by_command_id IS NULL)
         OR (lifecycle_state='retracted' AND retracted_at IS NOT NULL AND retracted_by_command_id IS NOT NULL)),
      FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE RESTRICT,
      FOREIGN KEY(source_snapshot_id) REFERENCES source_snapshots(id) ON DELETE RESTRICT,
      FOREIGN KEY(context_parse_artifact_id) REFERENCES parse_artifacts(id) ON DELETE RESTRICT,
      FOREIGN KEY(confirmed_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(updated_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(retracted_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE ideas (
      id CHAR(36) PRIMARY KEY NOT NULL,title VARCHAR(500) NOT NULL,content TEXT NOT NULL,
      status VARCHAR(64) NOT NULL,origin_type VARCHAR(64) NOT NULL,created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,deleted_at TEXT,row_version INTEGER NOT NULL,
      created_by_command_id CHAR(36) NOT NULL,updated_by_command_id CHAR(36) NOT NULL,
      deleted_by_command_id CHAR(36),CHECK(length(trim(title)) BETWEEN 1 AND 500),
      CHECK(length(trim(content))>=1 AND length(content)<=1000000),CHECK(row_version>=1),
      CHECK((deleted_at IS NULL)=(deleted_by_command_id IS NULL)),
      FOREIGN KEY(created_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(updated_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(deleted_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE submissions (
      id CHAR(36) PRIMARY KEY NOT NULL,paper_id CHAR(36) NOT NULL,
      venue VARCHAR(500) NOT NULL,status VARCHAR(64) NOT NULL,submitted_at TEXT,
      deadline_at TEXT,active_version_id CHAR(36),created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,deleted_at TEXT,row_version INTEGER NOT NULL,
      created_by_command_id CHAR(36) NOT NULL,updated_by_command_id CHAR(36) NOT NULL,
      deleted_by_command_id CHAR(36),CHECK(length(trim(venue)) BETWEEN 1 AND 500),
      CHECK(row_version>=1),CHECK((deleted_at IS NULL)=(deleted_by_command_id IS NULL)),
      FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE RESTRICT,
      FOREIGN KEY(active_version_id) REFERENCES paper_versions(id) ON DELETE RESTRICT,
      FOREIGN KEY(created_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(updated_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(deleted_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE notes (
      id CHAR(36) PRIMARY KEY NOT NULL,title VARCHAR(500) NOT NULL,content TEXT NOT NULL,
      source_document_id CHAR(36),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
      deleted_at TEXT,CHECK(length(trim(title)) BETWEEN 1 AND 500),CHECK(length(content)>0),
      FOREIGN KEY(source_document_id) REFERENCES source_documents(id) ON DELETE RESTRICT)""",
    """CREATE TABLE entity_relations (
      id CHAR(36) PRIMARY KEY NOT NULL,source_type VARCHAR(64) NOT NULL,
      source_id CHAR(36) NOT NULL,relation_type VARCHAR(64) NOT NULL,
      target_type VARCHAR(64) NOT NULL,target_id CHAR(36) NOT NULL,
      confidence NUMERIC(6,5),confirmation_state VARCHAR(64) NOT NULL,
      lifecycle_state VARCHAR(64) NOT NULL DEFAULT 'active',superseded_by_relation_id CHAR(36),
      created_by_actor_type VARCHAR(64) NOT NULL,created_by_actor_id VARCHAR(255),
      created_by_command_id CHAR(36),row_version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,updated_at TEXT NOT NULL,retracted_at TEXT,
      retracted_by_command_id CHAR(36),CHECK(row_version>=1),
      CHECK(lifecycle_state IN ('active','retracted','superseded')),
      CHECK((lifecycle_state='superseded')=(superseded_by_relation_id IS NOT NULL)),
      CHECK(relation_type IN ('belongs_to','derived_from','version_of','used_in','deleted_from','supports','contradicts','extends','related_to','presented_at','submitted_as','reviewed_by','suggested_for','split_from','merged_from','version_successor_of')),
      FOREIGN KEY(superseded_by_relation_id) REFERENCES entity_relations(id) ON DELETE RESTRICT,
      FOREIGN KEY(created_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT,
      FOREIGN KEY(retracted_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    "CREATE UNIQUE INDEX ux_entity_relations_active_endpoints ON entity_relations(relation_type,source_type,source_id,target_type,target_id) WHERE lifecycle_state='active'",
    """CREATE TABLE relation_observations (
      id CHAR(36) PRIMARY KEY NOT NULL,relation_id CHAR(36) NOT NULL,
      observed_by_actor_type VARCHAR(64) NOT NULL,observed_by_actor_id VARCHAR(255),
      provenance_type VARCHAR(64) NOT NULL,confidence NUMERIC(6,5),
      origin_task_id CHAR(36),origin_operation_id CHAR(36),evidence_ref_id CHAR(36),
      provider_id VARCHAR(255),model_id VARCHAR(255),observed_at TEXT NOT NULL,
      observation_key VARCHAR(255) NOT NULL UNIQUE,
      CHECK(origin_task_id IS NULL OR origin_operation_id IS NULL),
      FOREIGN KEY(relation_id) REFERENCES entity_relations(id) ON DELETE RESTRICT,
      FOREIGN KEY(origin_task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
      FOREIGN KEY(origin_operation_id) REFERENCES background_operations(id) ON DELETE RESTRICT,
      FOREIGN KEY(evidence_ref_id) REFERENCES evidence_refs(id) ON DELETE RESTRICT)""",
    """CREATE TABLE legacy_relation_observations_v01 (
      id CHAR(36) PRIMARY KEY NOT NULL,relation_id CHAR(36) NOT NULL,
      observed_by_actor_type VARCHAR(64) NOT NULL,observed_by_actor_id VARCHAR(255),
      provenance_type VARCHAR(64) NOT NULL,confidence NUMERIC(6,5),
      origin_task_id CHAR(36),evidence_ref_id CHAR(36),provider_id VARCHAR(255),
      model_id VARCHAR(255),observed_at TEXT NOT NULL,observation_key VARCHAR(255) NOT NULL,
      reason_code VARCHAR(128) NOT NULL,migration_batch_id CHAR(36) NOT NULL,
      source_schema_revision VARCHAR(128) NOT NULL,preserved_at TEXT NOT NULL,
      FOREIGN KEY(migration_batch_id) REFERENCES migration_batches(id) ON DELETE RESTRICT)""",
    "CREATE INDEX ix_legacy_relation_observations_key ON legacy_relation_observations_v01(observation_key)",
    """CREATE TABLE paper_version_candidates (
      id CHAR(36) PRIMARY KEY NOT NULL,earlier_snapshot_id CHAR(36) NOT NULL,
      later_snapshot_id CHAR(36) NOT NULL,detector_id VARCHAR(255) NOT NULL,
      detector_version VARCHAR(128) NOT NULL,rule_id VARCHAR(32) NOT NULL,
      rule_config_fingerprint CHAR(64) NOT NULL,direction_rationale_json TEXT NOT NULL,
      signals_json TEXT NOT NULL,input_observation_ids_json TEXT NOT NULL,
      status VARCHAR(64) NOT NULL,superseded_by_candidate_id CHAR(36),row_version INTEGER NOT NULL,
      created_at TEXT NOT NULL,decided_at TEXT,decided_by_command_id CHAR(36),
      UNIQUE(earlier_snapshot_id,later_snapshot_id,detector_id,detector_version,rule_config_fingerprint),
      FOREIGN KEY(earlier_snapshot_id) REFERENCES source_snapshots(id) ON DELETE RESTRICT,
      FOREIGN KEY(later_snapshot_id) REFERENCES source_snapshots(id) ON DELETE RESTRICT,
      FOREIGN KEY(superseded_by_candidate_id) REFERENCES paper_version_candidates(id) ON DELETE RESTRICT,
      FOREIGN KEY(decided_by_command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
    """CREATE TABLE domain_events (
      id CHAR(36) PRIMARY KEY NOT NULL,schema_version VARCHAR(16) NOT NULL,
      event_type VARCHAR(128) NOT NULL,workspace_id CHAR(36),command_id CHAR(36),
      operation_id CHAR(36),aggregate_type VARCHAR(128) NOT NULL,
      aggregate_id CHAR(36) NOT NULL,aggregate_version INTEGER,actor_type VARCHAR(64),
      payload_json TEXT NOT NULL,deduplication_key VARCHAR(255) NOT NULL UNIQUE,
      causation_id CHAR(36),correlation_id CHAR(36),created_at TEXT NOT NULL,
      occurred_at TEXT,processed_at TEXT,
      FOREIGN KEY(command_id) REFERENCES application_commands(id) ON DELETE RESTRICT)""",
)

_LEGACY_EVIDENCE_DDL = """CREATE TABLE legacy_evidence_refs_v01 (
 id CHAR(36) PRIMARY KEY NOT NULL,entity_type VARCHAR(64) NOT NULL,entity_id CHAR(36) NOT NULL,
 document_id CHAR(36) NOT NULL,version_id CHAR(36),section VARCHAR(1000),page INTEGER,
 slide INTEGER,paragraph_id CHAR(64),char_start INTEGER,char_end INTEGER,locator_json TEXT NOT NULL,
 quote_hash CHAR(64) NOT NULL,created_at TEXT NOT NULL,migration_batch_id CHAR(36) NOT NULL,
 source_schema_revision VARCHAR(128) NOT NULL,migration_reason VARCHAR(128) NOT NULL,
 preserved_at TEXT NOT NULL)"""

_LEGACY_OBSERVATION_INSERT = """INSERT INTO legacy_relation_observations_v01
 (id,relation_id,observed_by_actor_type,observed_by_actor_id,provenance_type,confidence,
  origin_task_id,evidence_ref_id,provider_id,model_id,observed_at,observation_key,
  reason_code,migration_batch_id,source_schema_revision,preserved_at)
 VALUES (:id,:relation_id,:observed_by_actor_type,:observed_by_actor_id,:provenance_type,
  :confidence,:origin_task_id,:evidence_ref_id,:provider_id,:model_id,:observed_at,
  :observation_key,:reason,:batch,:revision,:now)"""
