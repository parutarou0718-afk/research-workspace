"""Field-aware preflight for one protected compensating undo command."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from uuid import UUID

import rfc8785

from research_workspace.application.services.command_dispatcher import DomainMutation


class UndoError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UndoChange:
    entity_type: str
    entity_id: UUID
    operation: str
    before_snapshot: bytes | None
    after_snapshot: bytes | None
    changed_fields: tuple[str, ...]
    current_snapshot: bytes
    dependency_count: int = 0


@dataclass(frozen=True, slots=True)
class UndoPreflight:
    original_status: str
    already_undone: bool
    original_is_undo: bool
    changes: tuple[UndoChange, ...]


_ENTITY_EVENTS = {
    "Paper": ("paper.updated", "paper.deleted", "paper.restored"),
    "Idea": ("idea.updated", "idea.deleted", "idea.restored"),
    "Submission": (
        "submission.updated", "submission.deleted", "submission.restored"
    ),
}


def plan_compensating_undo(
    original_command_id: UUID,
    undo_command_id: UUID,
    now: datetime,
    preflight: UndoPreflight,
) -> tuple[DomainMutation, ...]:
    del original_command_id, undo_command_id
    if preflight.original_status != "committed" or preflight.original_is_undo:
        raise UndoError("UNDO_NOT_AVAILABLE")
    if preflight.already_undone:
        raise UndoError("UNDO_ALREADY_APPLIED")
    if not preflight.changes:
        raise UndoError("UNDO_NOT_AVAILABLE")
    return tuple(_compensate(change, now) for change in preflight.changes)


def _compensate(change: UndoChange, now: datetime) -> DomainMutation:
    if change.operation == "create" and change.dependency_count:
        raise UndoError("UNDO_DEPENDENCY_CONFLICT")
    current = _object(change.current_snapshot)
    before = _object(change.before_snapshot) if change.before_snapshot else None
    after = _object(change.after_snapshot) if change.after_snapshot else None
    if after is None:
        raise UndoError("UNDO_NOT_AVAILABLE")
    current_fields = current["fields"]
    after_fields = after["fields"]
    for field in change.changed_fields:
        if current_fields.get(field) != after_fields.get(field):
            raise UndoError("UNDO_CONFLICT")
    result_fields = dict(current_fields)
    event_index = 0
    compensation_fields = tuple(change.changed_fields)
    if change.operation == "create":
        if "deleted_at" in result_fields:
            result_fields["deleted_at"] = now.isoformat().replace("+00:00", "Z")
            event_index = 1
            compensation_fields = ("deleted_at",)
        elif "lifecycle_state" in result_fields:
            result_fields["lifecycle_state"] = "retracted"
            result_fields["retracted_at"] = now.isoformat().replace(
                "+00:00", "Z"
            )
            compensation_fields = ("lifecycle_state", "retracted_at")
        else:
            raise UndoError("UNDO_NOT_AVAILABLE")
    else:
        if before is None:
            raise UndoError("UNDO_NOT_AVAILABLE")
        for field in change.changed_fields:
            result_fields[field] = before["fields"].get(field)
        if change.operation == "soft_delete":
            event_index = 2
    row_version = current["row_version"] + 1
    result = {
        **current,
        "row_version": row_version,
        "fields": result_fields,
    }
    event_type = _event_type(change.entity_type, event_index)
    payload = rfc8785.dumps({
        "entity_id": str(change.entity_id), "row_version": row_version,
        "changed_fields": list(tuple(sorted(compensation_fields))),
    })
    return DomainMutation(
        change.entity_type, change.entity_id, "undo", current["row_version"],
        change.current_snapshot, rfc8785.dumps(result),
        tuple(sorted(compensation_fields)), event_type, payload,
    )


def _event_type(entity_type: str, index: int) -> str:
    try:
        return _ENTITY_EVENTS[entity_type][index]
    except KeyError as exc:
        raise UndoError("UNDO_NOT_AVAILABLE") from exc


def _object(value: bytes | None) -> dict[str, object]:
    if value is None:
        raise UndoError("UNDO_NOT_AVAILABLE")
    try:
        result = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UndoError("UNDO_NOT_AVAILABLE") from exc
    if not isinstance(result, dict) or not isinstance(result.get("fields"), dict):
        raise UndoError("UNDO_NOT_AVAILABLE")
    return result
