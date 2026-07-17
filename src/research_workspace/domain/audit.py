"""Closed immutable audit vocabulary for protected Gate 3 writes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import rfc8785
from uuid import UUID


APPROVED_ENTITY_TYPES = frozenset(
    {"Paper", "Idea", "Submission", "PaperVersion", "PaperVersionCandidate", "EntityRelation"}
)
APPROVED_OPERATIONS = frozenset(
    {"create", "update", "soft_delete", "restore", "confirm", "reject", "reconsider", "retract", "undo"}
)


@dataclass(frozen=True, slots=True)
class DomainSnapshot:
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_bytes, bytes):
            raise TypeError("domain snapshots must be immutable bytes")
        value = json.loads(self.canonical_bytes)
        if rfc8785.dumps(value) != self.canonical_bytes:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "1.0"
            or value.get("entity_type") not in APPROVED_ENTITY_TYPES
            or not isinstance(value.get("fields"), dict)
            or not isinstance(value.get("row_version"), int)
            or value["row_version"] < 1
        ):
            raise ValueError("COMMAND_VALIDATION_FAILED")


@dataclass(frozen=True, slots=True)
class AuditChange:
    entity_type: str
    entity_id: UUID
    operation: str
    before: DomainSnapshot | None
    after: DomainSnapshot | None
    changed_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.entity_type not in APPROVED_ENTITY_TYPES or self.operation not in APPROVED_OPERATIONS:
            raise ValueError("COMMAND_VALIDATION_FAILED")
        if not self.changed_fields or tuple(sorted(set(self.changed_fields))) != self.changed_fields:
            raise ValueError("changed_fields must be unique and sorted")
