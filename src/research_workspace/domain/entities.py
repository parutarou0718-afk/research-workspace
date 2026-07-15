"""Immutable foundation domain records, independent of persistence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

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
    id: str
    title: str
    status: PaperStatus
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


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
    id: str
    title: str
    content: str
    status: IdeaStatus
    origin_type: IdeaOriginType
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


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
    id: str
    paper_id: str
    venue: str
    status: SubmissionStatus
    submitted_at: datetime | None
    deadline_at: datetime | None
    active_version_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


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
