"""Immutable DomainEvent 2.0 boundary for new Gate 1 writes."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from research_workspace.domain.operations import freeze_json


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
