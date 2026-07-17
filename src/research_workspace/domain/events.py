"""Immutable DomainEvent 2.0 boundary for new Gate 1 writes."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from research_workspace.domain.operations import freeze_json


_ENTITY_MUTATION_EVENTS = frozenset(
    {
        "paper.created", "paper.updated", "paper.deleted", "paper.restored",
        "idea.created", "idea.updated", "idea.deleted", "idea.restored",
        "submission.created", "submission.updated", "submission.deleted",
        "submission.restored",
    }
)

_SUBMISSION_STATUS_EVENT = "submission.status_changed"


def validate_user_event_payload(event_type: str, payload: object) -> None:
    """Fail closed for the Task 5 user-event subset; later tasks extend by contract."""
    if not isinstance(payload, Mapping):
        raise ValueError("COMMAND_VALIDATION_FAILED")
    if event_type == _SUBMISSION_STATUS_EVENT:
        if set(payload) != {
            "submission_id", "old_status", "new_status", "row_version"
        }:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if (
            not isinstance(payload["submission_id"], str)
            or not isinstance(payload["old_status"], str)
            or not isinstance(payload["new_status"], str)
            or not isinstance(payload["row_version"], int)
            or payload["row_version"] < 1
        ):
            raise ValueError("COMMAND_VALIDATION_FAILED")
        return
    if event_type not in _ENTITY_MUTATION_EVENTS:
        raise ValueError("COMMAND_VALIDATION_FAILED")
    if set(payload) != {"entity_id", "row_version", "changed_fields"}:
        raise ValueError("COMMAND_VALIDATION_FAILED")
    if not isinstance(payload["entity_id"], str):
        raise ValueError("COMMAND_VALIDATION_FAILED")
    if not isinstance(payload["row_version"], int) or payload["row_version"] < 1:
        raise ValueError("COMMAND_VALIDATION_FAILED")
    fields = payload["changed_fields"]
    if not isinstance(fields, (list, tuple)) or len(set(fields)) != len(fields):
        raise ValueError("COMMAND_VALIDATION_FAILED")


# v0.1 read compatibility. New writes use DomainEventV2 exclusively.
DomainEvent = Mapping[str, object]


@dataclass(frozen=True)
class DomainEventV2:
    event_id: UUID
    event_type: str
    occurred_at: datetime
    workspace_id: UUID
    command_id: UUID | None
    operation_id: UUID | None
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int | None
    actor_type: str
    correlation_id: UUID
    causation_id: UUID | None
    payload: Mapping[str, object]
    deduplication_key: str

    def __post_init__(self) -> None:
        if self.actor_type not in {"user", "system"}:
            raise ValueError("actor_type must be user or system")
        if self.actor_type == "user" and self.command_id is None:
            raise ValueError("user events require command_id")
        if self.actor_type == "system" and self.operation_id is None:
            raise ValueError("system events require operation_id")
        frozen = freeze_json(self.payload)
        if not isinstance(frozen, Mapping):
            raise TypeError("event payload must be an object")
        object.__setattr__(self, "payload", frozen)
