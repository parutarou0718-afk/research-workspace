"""Immutable foundation domain records, independent of persistence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from research_workspace.domain.enums import (
    ActorType,
    AuditTargetType,
    ConferenceStatus,
    ConfirmationState,
    EvidenceTargetType,
    EventAggregateType,
    EventType,
    GrantStatus,
    IdeaOriginType,
    IdeaStatus,
    PaperStatus,
    ProvenanceType,
    RelationEntityType,
    RelationType,
    SubmissionStatus,
    TaskEffectStatus,
    TaskType,
)
from research_workspace.domain.tasks import AttemptStatus, TaskStatus


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    sha256: str
    size_bytes: int
    mime_type: str
    storage_relative_path: str
    original_filename: str
    created_at: datetime
    preferred_parse_artifact_id: str | None


@dataclass(frozen=True)
class SourceObservation:
    id: str
    normalized_path_hash: str
    original_filename: str
    current_snapshot_id: str | None
    availability_status: str
    baseline_only: bool
    size_bytes: int | None
    modified_at: datetime | None
    file_id_hint: str | None
    volume_serial_hint: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    missing_at: datetime | None
    row_version: int


@dataclass(frozen=True)
class SourceObservationEvent:
    id: str
    source_observation_id: str
    event_type: str
    snapshot_id: str | None
    path_before_hash: str | None
    path_after_hash: str | None
    facts_json: Mapping[str, object]
    raw_file_event_id: str | None
    observed_at: datetime

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "facts_json")


@dataclass(frozen=True)
class BackgroundOperation:
    id: str
    operation_type: str
    status: str
    correlation_command_id: str | None
    work_plan_fingerprint: str
    permission_context_json: Mapping[str, object]
    result_summary_json: Mapping[str, object] | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "permission_context_json", "result_summary_json")


@dataclass(frozen=True)
class OperationAttempt:
    id: str
    operation_id: str
    attempt_number: int
    status: str
    error_code: str | None
    diagnostic_summary_json: Mapping[str, object] | None
    started_at: datetime
    finished_at: datetime | None
    next_attempt_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "diagnostic_summary_json")


@dataclass(frozen=True)
class ImportBatch:
    id: str
    operation_id: str
    status: str
    selected_count: int
    estimated_total_bytes: int
    estimated_added_bytes: int | None
    estimate_is_exact: bool
    disclosure_accepted_at: datetime
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class ImportItem:
    id: str
    batch_id: str
    source_observation_id: str
    snapshot_id: str | None
    state: str
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class ParseArtifact:
    id: str
    source_snapshot_id: str
    parser_id: str
    parser_version: str
    config_fingerprint: str
    contract_version: str
    created_at: datetime


@dataclass(frozen=True)
class ParseAttempt:
    id: str
    parse_artifact_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    warnings_json: tuple[str, ...]
    executor_version: str
    output_sha256: str | None
    derived_file_sha256: str | None
    derived_relative_path: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings_json", tuple(self.warnings_json))


@dataclass(frozen=True)
class ParsedBlock:
    id: str
    source_document_id: str
    parse_artifact_id: str
    block_index: int
    kind: str
    text: str
    locator_json: Mapping[str, object]
    metadata_json: Mapping[str, object]
    block_hash: str

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "locator_json", "metadata_json")


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _freeze_mapping_fields(instance: object, *field_names: str) -> None:
    for field_name in field_names:
        value = getattr(instance, field_name)
        if value is not None:
            object.__setattr__(instance, field_name, _freeze_json(value))


@dataclass(frozen=True)
class Paper:
    id: UUID
    title: str
    status: PaperStatus
    current_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    created_by_command_id: UUID
    updated_by_command_id: UUID
    deleted_by_command_id: UUID | None


@dataclass(frozen=True)
class PaperVersion:
    id: str
    paper_id: str
    source_document_id: str
    version_label: str
    parent_version_id: str | None
    is_current: bool
    created_at: datetime


@dataclass(frozen=True)
class Idea:
    id: UUID
    title: str
    content: str
    status: IdeaStatus
    origin_type: IdeaOriginType
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    created_by_command_id: UUID
    updated_by_command_id: UUID
    deleted_by_command_id: UUID | None


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    content: str
    source_document_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class SourceDocument:
    id: str
    path: str
    sha256: str
    mime_type: str
    size_bytes: int
    modified_at: datetime
    imported_at: datetime
    read_only: bool
    missing_at: datetime | None


@dataclass(frozen=True)
class Submission:
    id: UUID
    paper_id: UUID
    venue: str
    status: SubmissionStatus
    submitted_at: datetime | None
    deadline_at: datetime | None
    active_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    created_by_command_id: UUID
    updated_by_command_id: UUID
    deleted_by_command_id: UUID | None


@dataclass(frozen=True)
class Conference:
    id: str
    name: str
    starts_at: datetime | None
    ends_at: datetime | None
    location: str | None
    status: ConferenceStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class Grant:
    id: str
    name: str
    status: GrantStatus
    deadline_at: datetime | None
    source_url: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class EvidenceRef:
    id: str
    entity_type: EvidenceTargetType
    entity_id: str
    document_id: str
    version_id: str | None
    section: str | None
    page: int | None
    slide: int | None
    paragraph_id: str | None
    char_start: int | None
    char_end: int | None
    locator_json: Mapping[str, object]
    quote_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "locator_json")


@dataclass(frozen=True)
class EntityRelation:
    id: str
    source_type: RelationEntityType
    source_id: str
    relation_type: RelationType
    target_type: RelationEntityType
    target_id: str
    confidence: Decimal | None
    confirmation_state: ConfirmationState
    created_by_actor_type: ActorType
    created_by_actor_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RelationObservation:
    id: str
    relation_id: str
    observed_by_actor_type: ActorType
    observed_by_actor_id: str | None
    provenance_type: ProvenanceType
    confidence: Decimal | None
    origin_task_id: str | None
    evidence_ref_id: str | None
    provider_id: str | None
    model_id: str | None
    observed_at: datetime
    observation_key: str


@dataclass(frozen=True)
class AuditLog:
    id: str
    actor_type: ActorType
    actor_id: str | None
    action: str
    target_type: AuditTargetType
    target_id: str
    before_json: Mapping[str, object] | None
    after_json: Mapping[str, object] | None
    task_id: str | None
    correlation_id: str | None
    undo_token: str | None
    undo_of_audit_id: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "before_json", "after_json")


@dataclass(frozen=True)
class Task:
    id: str
    task_type: TaskType
    status: TaskStatus
    idempotency_key: str
    request_fingerprint: str
    payload_json: Mapping[str, object]
    result_json: Mapping[str, object] | None
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    lease_generation: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "payload_json", "result_json")


@dataclass(frozen=True)
class TaskAttempt:
    id: str
    task_id: str
    attempt_number: int
    lease_generation: int
    lease_owner: str
    status: AttemptStatus
    result_json: Mapping[str, object] | None
    started_at: datetime
    finished_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "result_json")


@dataclass(frozen=True)
class TaskEffect:
    id: str
    operation_key: str
    task_id: str
    attempt_id: str
    effect_type: str
    output_type: str
    output_identity: str
    output_ref_json: Mapping[str, object]
    status: TaskEffectStatus
    recovery_json: Mapping[str, object] | None
    created_at: datetime
    committed_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "output_ref_json", "recovery_json")


@dataclass(frozen=True)
class DomainEvent:
    id: str
    event_type: EventType
    aggregate_type: EventAggregateType
    aggregate_id: str
    payload_json: Mapping[str, object]
    deduplication_key: str
    causation_id: str | None
    correlation_id: str | None
    created_at: datetime
    processed_at: datetime | None

    def __post_init__(self) -> None:
        _freeze_mapping_fields(self, "payload_json")
