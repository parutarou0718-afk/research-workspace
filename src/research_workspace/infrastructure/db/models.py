"""Typed SQLAlchemy mappings for the locked foundation schema."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean, CHAR, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from research_workspace.infrastructure.db.base import Base, UTCDateTime, UUIDText


def _uuid(primary_key: bool = False, nullable: bool = False):
    return mapped_column(UUIDText(), primary_key=primary_key, nullable=nullable)


class SourceDocumentModel(Base):
    __tablename__ = "source_documents"
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


class PaperModel(Base):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("status IN ('active','paused','revision','submitted','completed','archived')", name="status_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
        CheckConstraint("deleted_at IS NULL OR deleted_at >= created_at", name="deleted_after_created"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'active'"))
    current_version_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("paper_versions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PaperVersionModel(Base):
    __tablename__ = "paper_versions"
    __table_args__ = (
        UniqueConstraint("paper_id", "version_label", name="uq_paper_versions_paper_label"),
        CheckConstraint("parent_version_id IS NULL OR parent_version_id <> id", name="parent_not_self"),
        Index("ux_paper_versions_one_current", "paper_id", unique=True, sqlite_where=text("is_current = 1")),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    paper_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("paper_versions.id", ondelete="RESTRICT"), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class IdeaModel(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("length(content) > 0", name="content_nonempty"),
        CheckConstraint("status IN ('unused','used','parked','archived')", name="status_enum"),
        CheckConstraint("origin_type IN ('manual','document','note','meeting','chat','book','paper','ai_candidate')", name="origin_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'unused'"))
    origin_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'manual'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


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
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
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


class ConferenceModel(Base):
    __tablename__ = "conferences"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("status IN ('planned','registered','attending','completed','cancelled')", name="status_enum"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at", name="ends_after_starts"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
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
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'watching'"))
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EvidenceRefModel(Base):
    __tablename__ = "evidence_refs"
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
    document_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("source_documents.id", ondelete="RESTRICT"), nullable=False)
    version_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("paper_versions.id", ondelete="RESTRICT"), nullable=True)
    section: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_id: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class EntityRelationModel(Base):
    __tablename__ = "entity_relations"
    __table_args__ = (
        UniqueConstraint("relation_type", "source_type", "source_id", "target_type", "target_id", name="uq_entity_relations_assertion"),
        CheckConstraint("source_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')", name="source_type_enum"),
        CheckConstraint("target_type IN ('Paper','PaperVersion','Idea','Note','SourceDocument','Submission','Conference','Grant','EvidenceRef')", name="target_type_enum"),
        CheckConstraint("relation_type IN ('belongs_to','derived_from','version_of','used_in','deleted_from','supports','contradicts','extends','related_to','presented_at','submitted_as','reviewed_by','suggested_for','split_from','merged_from')", name="relation_type_enum"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        CheckConstraint("confirmation_state IN ('candidate','confirmed','rejected')", name="confirmation_state_enum"),
        CheckConstraint("created_by_actor_type IN ('user','system','task_executor','agent')", name="actor_type_enum"),
        CheckConstraint("updated_at >= created_at", name="updated_after_created"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    confirmation_state: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'candidate'"))
    created_by_actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RelationObservationModel(Base):
    __tablename__ = "relation_observations"
    __table_args__ = (
        UniqueConstraint("observation_key", name="uq_relation_observations_observation_key"),
        CheckConstraint("observed_by_actor_type IN ('user','system','task_executor','agent')", name="actor_type_enum"),
        CheckConstraint("provenance_type IN ('manual','rule','import','ai')", name="provenance_type_enum"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        CheckConstraint("provenance_type NOT IN ('import','ai') OR confidence IS NOT NULL", name="confidence_provenance"),
        CheckConstraint("observed_by_actor_type NOT IN ('task_executor','agent') OR origin_task_id IS NOT NULL", name="task_actor_origin"),
        CheckConstraint("provenance_type NOT IN ('import','ai') OR evidence_ref_id IS NOT NULL", name="evidence_provenance"),
        CheckConstraint("provenance_type <> 'ai' OR (provider_id IS NOT NULL AND model_id IS NOT NULL)", name="ai_provider_model"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    relation_id: Mapped[UUID] = mapped_column(UUIDText(), ForeignKey("entity_relations.id", ondelete="RESTRICT"), nullable=False)
    observed_by_actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provenance_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    origin_task_id: Mapped[UUID | None] = mapped_column(UUIDText(), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True)
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
        CheckConstraint("event_type IN ('document.imported','paper.created','paper.version_added','paper.version_relation_corrected','idea.created','idea.candidate_extracted','idea.linked','submission.created','submission.status_changed','context.recovered','task.failed','audit.undo_applied')", name="event_type_enum"),
        CheckConstraint("aggregate_type IN ('Paper','PaperVersion','Idea','SourceDocument','Submission','Conference','Grant','Task','AuditLog')", name="aggregate_type_enum"),
    )
    id: Mapped[UUID] = _uuid(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(UUIDText(), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    causation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(UUIDText(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
