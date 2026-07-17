"""Pure protected-write plans for Idea."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import rfc8785

from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.domain.entities import Idea
from research_workspace.domain.enums import IdeaStatus


class IdeaCommandError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class IdeaDependencies:
    active_relations: int = 0
    active_evidence_refs: int = 0

    @property
    def any(self) -> bool:
        return bool(self.active_relations or self.active_evidence_refs)


def _title(value: str) -> str:
    result = value.strip()
    if not 1 <= len(result) <= 500:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    return result


def _content(value: str) -> str:
    result = value.replace("\r\n", "\n").replace("\r", "\n")
    if not result.strip() or len(result) > 1_000_000:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    return result


def _status(value: str) -> str:
    try:
        return IdeaStatus(value).value
    except ValueError as exc:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED") from exc


def _snapshot(
    idea_id: UUID, row_version: int, *, title: str, content: str,
    status: str, deleted_at: datetime | None,
) -> bytes:
    return rfc8785.dumps(
        {
            "schema_version": "1.0",
            "entity_type": "Idea",
            "entity_id": str(idea_id),
            "row_version": row_version,
            "fields": {
                "title": title,
                "content": content,
                "status": status,
                "origin_type": "manual",
                "deleted_at": deleted_at.isoformat().replace("+00:00", "Z")
                if deleted_at else None,
            },
        }
    )


def _event(idea_id: UUID, version: int, changed: tuple[str, ...]) -> bytes:
    return rfc8785.dumps(
        {
            "entity_id": str(idea_id),
            "row_version": version,
            "changed_fields": list(changed),
        }
    )


def create_idea(
    command_id: UUID, idea_id: UUID, title: str, content: str, status: str,
    now: datetime, *, origin_type: str = "manual",
) -> DomainMutation:
    del command_id, now
    if origin_type != "manual":
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    clean_title, clean_content, clean_status = _title(title), _content(content), _status(status)
    changed = ("content", "deleted_at", "origin_type", "status", "title")
    after = _snapshot(
        idea_id, 1, title=clean_title, content=clean_content,
        status=clean_status, deleted_at=None,
    )
    return DomainMutation(
        "Idea", idea_id, "create", None, None, after, changed,
        "idea.created", _event(idea_id, 1, changed),
    )


def update_idea(
    idea: Idea, command_id: UUID, *, title: str, content: str,
    status: str, now: datetime,
) -> DomainMutation:
    del command_id, now
    if idea.deleted_at is not None or idea.origin_type.value != "manual":
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    clean_title, clean_content, clean_status = _title(title), _content(content), _status(status)
    changed = tuple(
        name for name, before, after in (
            ("content", idea.content, clean_content),
            ("status", idea.status.value, clean_status),
            ("title", idea.title, clean_title),
        ) if before != after
    )
    if not changed:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    return _change(idea, "update", clean_title, clean_content, clean_status, None, changed, "idea.updated")


def soft_delete_idea(
    idea: Idea, command_id: UUID, now: datetime, dependencies: IdeaDependencies,
) -> DomainMutation:
    del command_id
    if dependencies.any:
        raise IdeaCommandError("DELETE_DEPENDENCY_CONFLICT")
    if idea.deleted_at is not None:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    return _change(
        idea, "soft_delete", idea.title, idea.content, idea.status.value,
        now, ("deleted_at",), "idea.deleted",
    )


def restore_idea(idea: Idea, command_id: UUID, now: datetime) -> DomainMutation:
    del command_id, now
    if idea.deleted_at is None:
        raise IdeaCommandError("COMMAND_VALIDATION_FAILED")
    return _change(
        idea, "restore", idea.title, idea.content, idea.status.value,
        None, ("deleted_at",), "idea.restored",
    )


def _change(
    idea: Idea, operation: str, title: str, content: str, status: str,
    deleted_at: datetime | None, changed: tuple[str, ...], event_type: str,
) -> DomainMutation:
    before = _snapshot(
        idea.id, idea.row_version, title=idea.title, content=idea.content,
        status=idea.status.value, deleted_at=idea.deleted_at,
    )
    version = idea.row_version + 1
    after = _snapshot(
        idea.id, version, title=title, content=content, status=status,
        deleted_at=deleted_at,
    )
    ordered = tuple(sorted(changed))
    return DomainMutation(
        "Idea", idea.id, operation, idea.row_version, before, after, ordered,
        event_type, _event(idea.id, version, ordered),
    )
