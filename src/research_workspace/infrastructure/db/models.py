"""Typed SQLAlchemy mappings for the locked foundation schema."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean, CHAR, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from research_workspace.infrastructure.db.base import Base, UTCDateTime, UUIDText


def _uuid(primary_key: bool = False, nullable: bool = False):
    return mapped_column(UUIDText(), primary_key=primary_key, nullable=nullable)


class LegacySourceDocumentV01Model(Base):
    __tablename__ = "legacy_source_documents_v01"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="sha256_lower_hex"),
        CheckConstraint("read_only = 1", name="original_read_only"),
        Index("ux_source_documents_path_nocase", "path", unique=True, sqlite_where=None),
        Index("ix_source_documents_sha256", "sha256"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    path: Mapped[str] = mapped_column(Text(collation="NOCASE"), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
    missing_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    migration_batch_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    source_schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    preserved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkspaceMetadataModel(Base):
    __tablename__ = "workspace_metadata"
    __table_args__ = (CheckConstraint("watcher_generation >= 0", name="watcher_generation_nonnegative"),)
    workspace_id: Mapped[UUID] = _uuid(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    clean_shutdown: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
    watcher_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MigrationBatchModel(Base):
    __tablename__ = "migration_batches"
    id: Mapped[UUID] = _uuid(primary_key=True)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    target_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    pre_migration_backup_path_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    counts_json: Mapped[str] = mapped_column(Text, nullable=False)
    exceptions_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class BackgroundOperationModel(Base):
    __tablename__ = "background_operations"
    id: Mapped[UUID] = _uuid(primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    work_plan_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    permission_context_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class SourceSnapshotModel(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_source_snapshots_sha256"),
        UniqueConstraint("storage_relative_path", name="uq_source_snapshots_storage_path"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_by_operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False)


class SourceObservationModel(Base):
    __tablename__ = "source_observations"
    __table_args__ = (
        UniqueConstraint("normalized_path", name="uq_source_observations_normalized_path"),
        Index("ix_source_observations_normalized_path_hash", "normalized_path_hash"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_path: Mapped[str] = mapped_column(Text(collation="NOCASE"), nullable=False)
    normalized_path_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    monitoring_root_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("monitoring_roots.id", ondelete="RESTRICT"), nullable=True)
    current_snapshot_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=True)
    availability_status: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    file_id_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume_serial_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    missing_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class SourceObservationEventModel(Base):
    __tablename__ = "source_observation_events"
    id: Mapped[UUID] = _uuid(primary_key=True)
    source_observation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_observations.id", ondelete="RESTRICT"), nullable=False)
    raw_file_event_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("raw_file_events.id", ondelete="RESTRICT"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=True)
    path_before_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    path_after_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MonitoringRootModel(Base):
    __tablename__ = "monitoring_roots"
    __table_args__ = (
        UniqueConstraint("normalized_path", name="uq_monitoring_roots_normalized_path"),
        CheckConstraint(
            "status IN ('active','paused','disconnected','degraded','overflow_reconciling','error')",
            name="status_enum",
        ),
        CheckConstraint("recursive = 1", name="recursive_true"),
        CheckConstraint("watcher_generation >= 0", name="watcher_generation_nonnegative"),
        CheckConstraint(
            "length(normalized_path_hash)=64 "
            "AND normalized_path_hash NOT GLOB '*[^0-9a-f]*'",
            name="normalized_path_hash_lower_hex",
        ),
        CheckConstraint(
            "length(config_fingerprint)=64 "
            "AND config_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="config_fingerprint_lower_hex",
        ),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_path: Mapped[str] = mapped_column(Text(collation="NOCASE"), nullable=False)
    normalized_path_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    recursive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    watcher_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RawFileEventModel(Base):
    __tablename__ = "raw_file_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_raw_file_events_deduplication"),
        CheckConstraint(
            "event_type IN ('created','modified','moved','deleted','overflow','root_state')",
            name="event_type_enum",
        ),
        CheckConstraint(
            "source_path_hash IS NULL OR "
            "(length(source_path_hash)=64 AND source_path_hash NOT GLOB '*[^0-9a-f]*')",
            name="source_path_hash_lower_hex",
        ),
        CheckConstraint(
            "destination_path_hash IS NULL OR "
            "(length(destination_path_hash)=64 "
            "AND destination_path_hash NOT GLOB '*[^0-9a-f]*')",
            name="destination_path_hash_lower_hex",
        ),
        CheckConstraint(
            "length(deduplication_key)=64 "
            "AND deduplication_key NOT GLOB '*[^0-9a-f]*'",
            name="deduplication_key_lower_hex",
        ),
        CheckConstraint(
            "event_type <> 'moved' OR destination_path IS NOT NULL",
            name="move_has_destination",
        ),
        Index("ix_raw_file_events_root_observed", "monitoring_root_id", "observed_at"),
        Index("ix_raw_file_events_source_hash_observed", "source_path_hash", "observed_at"),
        Index("ix_raw_file_events_correlation_hint", "correlation_hint"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    monitoring_root_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("monitoring_roots.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    destination_path_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    raw_sequence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deduplication_key: Mapped[str] = mapped_column(CHAR(64), nullable=False)


class PendingPathCheckModel(Base):
    __tablename__ = "pending_path_checks"
    __table_args__ = (
        UniqueConstraint(
            "monitoring_root_id", "normalized_path", name="uq_pending_path_checks_root_path"
        ),
        CheckConstraint("stability_attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        CheckConstraint(
            "length(normalized_path_hash)=64 "
            "AND normalized_path_hash NOT GLOB '*[^0-9a-f]*'",
            name="normalized_path_hash_lower_hex",
        ),
        CheckConstraint(
            "state IN ('detected','debouncing','waiting_for_stability','importing',"
            "'imported','duplicate_content','safe_failure','unstable_source')",
            name="state_enum",
        ),
        CheckConstraint("last_event_at >= first_event_at", name="event_time_order"),
        Index("ix_pending_path_checks_path_hash", "normalized_path_hash"),
        Index("ix_pending_path_checks_state_due", "state", "next_check_at"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    monitoring_root_id: Mapped[UUID] = mapped_column(
        UUIDText(), ForeignKey("monitoring_roots.id", ondelete="RESTRICT"), nullable=False
    )
    normalized_path: Mapped[str] = mapped_column(Text(collation="NOCASE"), nullable=False)
    normalized_path_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    first_event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    merged_event_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    stability_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_observation_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("source_observations.id", ondelete="RESTRICT"), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class RawEventPendingLinkModel(Base):
    __tablename__ = "raw_event_pending_links"
    raw_file_event_id: Mapped[UUID] = mapped_column(
        UUIDText(),
        ForeignKey("raw_file_events.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pending_path_check_id: Mapped[UUID] = mapped_column(
        UUIDText(),
        ForeignKey("pending_path_checks.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ReconciliationRunModel(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_reconciliation_runs_operation"),
        CheckConstraint("items_seen >= 0", name="items_seen_nonnegative"),
        CheckConstraint("items_suspected_changed >= 0", name="items_changed_nonnegative"),
        CheckConstraint(
            "items_estimated IS NULL OR items_estimated >= items_seen",
            name="estimate_covers_seen",
        ),
        CheckConstraint(
            "reason IN ('baseline','disconnect','overflow','unclean_shutdown','user_verify')",
            name="reason_enum",
        ),
        CheckConstraint(
            "status IN ('planned','running','paused','completed','failed','cancelled')",
            name="status_enum",
        ),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    monitoring_root_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("monitoring_roots.id", ondelete="RESTRICT"), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_suspected_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PaperVersionCandidateModel(Base):
    __tablename__ = "paper_version_candidates"
    __table_args__ = (
        UniqueConstraint(
            "earlier_snapshot_id",
            "later_snapshot_id",
            "detector_id",
            "detector_version",
            "rule_config_fingerprint",
            name="uq_paper_version_candidates_identity",
        ),
        CheckConstraint("earlier_snapshot_id <> later_snapshot_id", name="snapshots_distinct"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        CheckConstraint(
            "length(trim(detector_id)) > 0 AND length(trim(detector_version)) > 0",
            name="detector_nonblank",
        ),
        CheckConstraint(
            "rule_id IN ('R1_SOURCE_CONTINUITY','R2_REPLACE_CONTINUITY',"
            "'R3_PAPER_TITLE_TIME','R4_NAME_TITLE_TEXT','R5_ZERO_TEXT_LINEAGE')",
            name="rule_id_enum",
        ),
        CheckConstraint(
            "length(rule_config_fingerprint)=64 "
            "AND rule_config_fingerprint NOT GLOB '*[^0-9a-f]*'",
            name="rule_config_fingerprint_lower_hex",
        ),
        CheckConstraint(
            "status IN ('pending','confirmed','rejected','superseded')",
            name="status_enum",
        ),
        CheckConstraint(
            "(status='superseded' AND superseded_by_candidate_id IS NOT NULL) OR "
            "(status<>'superseded' AND superseded_by_candidate_id IS NULL)",
            name="supersession_consistent",
        ),
        CheckConstraint(
            "(status IN ('confirmed','rejected') AND decided_at IS NOT NULL) OR "
            "(status NOT IN ('confirmed','rejected') AND decided_at IS NULL)",
            name="decision_time_consistent",
        ),
        Index("ix_paper_version_candidates_earlier", "earlier_snapshot_id"),
        Index("ix_paper_version_candidates_later", "later_snapshot_id"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    earlier_snapshot_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=False)
    later_snapshot_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=False)
    detector_id: Mapped[str] = mapped_column(String(255), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_config_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    direction_rationale_json: Mapped[str] = mapped_column(Text, nullable=False)
    signals_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_observation_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'pending'"))
    superseded_by_candidate_id: Mapped[UUID | None] = mapped_column(
        UUIDText(),
        ForeignKey("paper_version_candidates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decided_by_command_id: Mapped[UUID | None] = mapped_column(
        UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True
    )


class OperationAttemptModel(Base):
    __tablename__ = "operation_attempts"
    __table_args__ = (UniqueConstraint("operation_id", "attempt_number", name="uq_operation_attempts"),)
    id: Mapped[UUID] = _uuid(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    diagnostic_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ImportBatchModel(Base):
    __tablename__ = "import_batches"
    id: Mapped[UUID] = _uuid(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_added_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_is_exact: Mapped[bool] = mapped_column(Boolean, nullable=False)
    disclosure_accepted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ParseArtifactModel(Base):
    __tablename__ = "parse_artifacts"
    __table_args__ = (UniqueConstraint("source_snapshot_id", "parser_id", "parser_version", "config_fingerprint", "contract_version", name="uq_parse_artifacts_revision"),)
    id: Mapped[UUID] = _uuid(primary_key=True)
    source_snapshot_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=False)
    parser_id: Mapped[str] = mapped_column(String(255), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    successful_attempt_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("parse_attempts.id", ondelete="RESTRICT"), nullable=True, unique=True)
    output_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    derived_file_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    derived_relative_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ParseAttemptModel(Base):
    __tablename__ = "parse_attempts"
    __table_args__ = (
        UniqueConstraint("parse_artifact_id", "attempt_number", name="uq_parse_attempts_number"),
        Index("ux_parse_attempts_one_succeeded", "parse_artifact_id", unique=True, sqlite_where=text("status='succeeded'")),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    parse_artifact_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    executor_version: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    derived_file_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    diagnostic_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SnapshotParsePreferenceModel(Base):
    __tablename__ = "snapshot_parse_preferences"
    source_snapshot_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), primary_key=True)
    parse_artifact_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_by_operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False)


class SourceDocumentModel(Base):
    __tablename__ = "source_documents"
    id: Mapped[UUID] = _uuid(primary_key=True)
    parse_artifact_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ParsedBlockModel(Base):
    __tablename__ = "parsed_blocks"
    __table_args__ = (UniqueConstraint("parse_artifact_id", "block_index", name="uq_parsed_blocks_index"),)
    id: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    parse_artifact_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)


class EvidenceRefModel(Base):
    __tablename__ = "evidence_refs"
    id: Mapped[UUID] = _uuid(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    parse_artifact_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=False)
    parsed_block_id: Mapped[str] = mapped_column(CHAR(64), ForeignKey("parsed_blocks.id", ondelete="RESTRICT"), nullable=False)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    saved_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_by_operation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=False)


class ImportItemModel(Base):
    __tablename__ = "import_items"
    id: Mapped[UUID] = _uuid(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    source_observation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_observations.id", ondelete="RESTRICT"), nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=True)
    parse_artifact_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ApplicationCommandModel(Base):
    __tablename__ = "application_commands"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_application_commands_idempotency_key"),
        UniqueConstraint("undo_of_command_id", name="uq_application_commands_undo_of"),
        CheckConstraint("contract_version = '1.0'", name="contract_version"),
        CheckConstraint("actor_type IN ('user','system')", name="actor_type"),
        CheckConstraint("status IN ('pending','running','committed','failed','cancelled')", name="status"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    command_type: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission_context_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recovery_point_id: Mapped[UUID | None] = mapped_column(
        UUIDText(), ForeignKey("recovery_points.id", ondelete="RESTRICT"), nullable=True
    )
    undo_of_command_id: Mapped[UUID | None] = mapped_column(
        UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True
    )
    result_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    migration_batch_id: Mapped[UUID | None] = mapped_column(
        UUIDText(), ForeignKey("migration_batches.id", ondelete="RESTRICT"), nullable=True
    )


class AuditChangeModel(Base):
    __tablename__ = "audit_changes"
    __table_args__ = (
        UniqueConstraint("command_id", "change_index", name="uq_audit_changes_command_index"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False
    )
    change_index: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    before_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    before_row_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_row_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RecoveryPointModel(Base):
    __tablename__ = "recovery_points"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_recovery_points_command"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    command_id: Mapped[UUID] = mapped_column(
        UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    physical_state: Mapped[str] = mapped_column(String(64), nullable=False)
    database_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_manifest_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RecoverySlotModel(Base):
    __tablename__ = "recovery_slots"
    __table_args__ = (
        UniqueConstraint("recovery_point_id", name="uq_recovery_slots_point"),
    )
    workspace_id: Mapped[UUID] = mapped_column(
        UUIDText(), ForeignKey("workspace_metadata.workspace_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    slot_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    recovery_point_id: Mapped[UUID] = mapped_column(
        UUIDText(), ForeignKey("recovery_points.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class PaperModel(Base):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("status IN ('active','paused','revision','submitted','completed','archived')", name="status_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
        CheckConstraint("deleted_at IS NULL OR deleted_at >= created_at", name="deleted_after_created"),
        CheckConstraint("(deleted_at IS NULL) = (deleted_by_command_id IS NULL)", name="delete_pair"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'active'"))
    current_version_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("paper_versions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    updated_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    deleted_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)


class PaperVersionModel(Base):
    __tablename__ = "paper_versions"
    __table_args__ = (
        UniqueConstraint("paper_id", "source_snapshot_id", name="uq_paper_versions_snapshot"),
        UniqueConstraint("paper_id", "normalized_version_label", name="uq_paper_versions_label"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    paper_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), nullable=False)
    context_parse_artifact_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("parse_artifacts.id", ondelete="RESTRICT"), nullable=True)
    version_label: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_version_label: Mapped[str] = mapped_column(String(200), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'active'")
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    confirmed_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    retracted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    retracted_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)


class IdeaModel(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("length(content) > 0", name="content_nonempty"),
        CheckConstraint("status IN ('unused','used','parked','archived')", name="status_enum"),
        CheckConstraint("origin_type IN ('manual','document','note','meeting','chat','book','paper','ai_candidate')", name="origin_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
        CheckConstraint("(deleted_at IS NULL) = (deleted_by_command_id IS NULL)", name="delete_pair"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'unused'"))
    origin_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'manual'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    updated_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    deleted_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)


class NoteModel(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("length(content) > 0", name="content_nonempty"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class SubmissionModel(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint("length(trim(venue)) > 0", name="venue_nonempty"),
        CheckConstraint("status IN ('preparing','ready','submitted','editorial_review','external_review','revision','accepted','rejected','withdrawn','no_response')", name="status_enum"),
        CheckConstraint("(deleted_at IS NULL) = (deleted_by_command_id IS NULL)", name="delete_pair"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    paper_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False)
    venue: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'preparing'"))
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    active_version_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("paper_versions.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    updated_by_command_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=False)
    deleted_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)


class ConferenceModel(Base):
    __tablename__ = "conferences"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("status IN ('planned','registered','attending','completed','cancelled')", name="status_enum"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at", name="ends_after_starts"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'planned'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class GrantModel(Base):
    __tablename__ = "grants"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("status IN ('watching','preparing','submitted','awarded','rejected','archived')", name="status_enum"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'watching'"))
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LegacyEvidenceRefV01Model(Base):
    __tablename__ = "legacy_evidence_refs_v01"
    __table_args__ = (
        CheckConstraint("entity_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EntityRelation')", name="entity_type_enum"),
        CheckConstraint("page IS NULL OR page >= 1", name="page_positive"),
        CheckConstraint("slide IS NULL OR slide >= 1", name="slide_positive"),
        CheckConstraint("char_start IS NULL OR char_start >= 0", name="char_start_nonnegative"),
        CheckConstraint("char_end IS NULL OR (char_start IS NOT NULL AND char_end >= char_start)", name="char_range"),
        CheckConstraint("paragraph_id IS NULL OR (length(paragraph_id) = 64 AND paragraph_id NOT GLOB '*[^0-9a-f]*')", name="paragraph_id_lower_hex"),
        CheckConstraint("length(quote_hash) = 64 AND quote_hash NOT GLOB '*[^0-9a-f]*'", name="quote_hash_lower_hex"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    document_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    version_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    section: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_id: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    migration_batch_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    source_schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    preserved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LegacyPaperVersionV01Model(Base):
    __tablename__ = "legacy_paper_versions_v01"
    __table_args__ = (
        UniqueConstraint("migration_batch_id", "legacy_row_id", name="uq_legacy_paper_versions_row"),
        Index("ix_legacy_paper_versions_linkage", "paper_id", "source_document_id", "parent_version_id"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    legacy_row_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    original_table: Mapped[str] = mapped_column(String(128), nullable=False)
    original_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    paper_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_batch_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("migration_batches.id", ondelete="RESTRICT"), nullable=False)
    source_schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    migrated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LegacyDependentRecordV01Model(Base):
    __tablename__ = "legacy_dependent_records_v01"
    __table_args__ = (
        UniqueConstraint(
            "original_table", "legacy_row_id", "migration_batch_id",
            name="uq_legacy_dependent_record",
        ),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    original_table: Mapped[str] = mapped_column(String(128), nullable=False)
    legacy_row_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    original_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_batch_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("migration_batches.id", ondelete="RESTRICT"), nullable=False)
    source_schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    migrated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LegacyRelationObservationV01Model(Base):
    __tablename__ = "legacy_relation_observations_v01"
    __table_args__ = (Index("ix_legacy_relation_observations_key", "observation_key"),)
    id: Mapped[UUID] = _uuid(primary_key=True)
    relation_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    observed_by_actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provenance_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    origin_task_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    evidence_ref_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_batch_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("migration_batches.id", ondelete="RESTRICT"), nullable=False)
    source_schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    preserved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class EntityRelationModel(Base):
    __tablename__ = "entity_relations"
    __table_args__ = (
        CheckConstraint("relation_type IN ('belongs_to','derived_from','version_of','used_in','deleted_from','supports','contradicts','extends','related_to','presented_at','submitted_as','reviewed_by','suggested_for','split_from','merged_from','version_successor_of')", name="relation_type_enum"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        CheckConstraint("confirmation_state IN ('candidate','confirmed','rejected')", name="confirmation_state_enum"),
        CheckConstraint("lifecycle_state IN ('active','retracted','superseded')", name="lifecycle_state_enum"),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        Index(
            "ux_entity_relations_active_endpoints",
            "relation_type", "source_type", "source_id", "target_type", "target_id",
            unique=True, sqlite_where=text("lifecycle_state='active'"),
        ),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    confirmation_state: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'candidate'"))
    lifecycle_state: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'active'")
    )
    superseded_by_relation_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("entity_relations.id", ondelete="RESTRICT"), nullable=True)
    created_by_actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)
    row_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    retracted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    retracted_by_command_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True)


class RelationObservationModel(Base):
    __tablename__ = "relation_observations"
    __table_args__ = (
        UniqueConstraint("observation_key", name="uq_relation_observations_observation_key"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        CheckConstraint("origin_task_id IS NULL OR origin_operation_id IS NULL", name="origin_exclusive"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    relation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("entity_relations.id", ondelete="RESTRICT"), nullable=False)
    observed_by_actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provenance_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    origin_task_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True)
    origin_operation_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("background_operations.id", ondelete="RESTRICT"), nullable=True)
    evidence_ref_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("evidence_refs.id", ondelete="RESTRICT"), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observation_key: Mapped[str] = mapped_column(String(255), nullable=False)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        UniqueConstraint("undo_token", name="uq_audit_logs_undo_token"),
        UniqueConstraint("undo_of_audit_id", name="uq_audit_logs_undo_of_audit_id"),
        CheckConstraint("actor_type IN ('user','system','task_executor','agent')", name="actor_type_enum"),
        CheckConstraint("target_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef','EntityRelation','RelationObservation','Task')", name="target_type_enum"),
        CheckConstraint("before_json IS NOT NULL OR after_json IS NOT NULL", name="before_or_after"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    undo_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    undo_of_audit_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("audit_logs.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tasks_idempotency_key"),
        CheckConstraint("task_type IN ('import_document','compare_versions','extract_idea_candidates','recover_paper_context','refresh_submission_overview','scheduled_incremental_organize','export_data')", name="task_type_enum"),
        CheckConstraint("status IN ('pending','running','needs_confirmation','succeeded','failed','cancelled')", name="status_enum"),
        CheckConstraint("length(request_fingerprint) = 64 AND request_fingerprint NOT GLOB '*[^0-9a-f]*'", name="request_fingerprint_lower_hex"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="max_attempts_range"),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint("lease_owner IS NULL OR lease_expires_at IS NOT NULL", name="lease_expiry_with_owner"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'pending'"))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class TaskAttemptModel(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="uq_task_attempts_task_attempt"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint("status IN ('running','retry_scheduled','succeeded','failed','cancelled','needs_confirmation')", name="status_enum"),
        CheckConstraint("(status = 'running' AND finished_at IS NULL AND result_json IS NULL) OR (status <> 'running' AND finished_at IS NOT NULL AND result_json IS NOT NULL)", name="closed_attempt_result"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'running'"))
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class TaskEffectModel(Base):
    __tablename__ = "task_effects"
    __table_args__ = (
        UniqueConstraint("operation_key", name="uq_task_effects_operation_key"),
        CheckConstraint("length(operation_key) = 64 AND operation_key NOT GLOB '*[^0-9a-f]*'", name="operation_key_lower_hex"),
        CheckConstraint("status IN ('prepared','committed','manual_reconciliation')", name="status_enum"),
        CheckConstraint("status <> 'committed' OR committed_at IS NOT NULL", name="committed_timestamp"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    operation_key: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    task_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("task_attempts.id", ondelete="RESTRICT"), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(255), nullable=False)
    output_type: Mapped[str] = mapped_column(String(255), nullable=False)
    output_identity: Mapped[str] = mapped_column(String(1000), nullable=False)
    output_ref_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    recovery_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class DomainEventModel(Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_domain_events_deduplication_key"),
        CheckConstraint("schema_version IN ('1.0','2.0')", name="schema_version_enum"),
        CheckConstraint("actor_type IS NULL OR actor_type IN ('user','system')", name="actor_type_enum"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    command_id: Mapped[UUID | None] = mapped_column(
        UUIDText(), ForeignKey("application_commands.id", ondelete="RESTRICT"), nullable=True
    )
    operation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    aggregate_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    causation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
