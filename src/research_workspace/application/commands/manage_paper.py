"""Pure protected-write plans for Paper."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import rfc8785

from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.domain.entities import Paper
from research_workspace.domain.enums import PaperStatus


class PaperCommandError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class PaperDependencies:
    active_submissions: int = 0
    active_relations: int = 0
    active_versions: int = 0
    active_evidence_refs: int = 0

    @property
    def any(self) -> bool:
        return any(
            (
                self.active_submissions,
                self.active_relations,
                self.active_versions,
                self.active_evidence_refs,
            )
        )


@dataclass(frozen=True, slots=True)
class PaperVersionRef:
    id: UUID
    paper_id: UUID
    lifecycle_state: str


def _title(value: str) -> str:
    normalized = value.strip()
    if not 1 <= len(normalized) <= 500:
        raise PaperCommandError("COMMAND_VALIDATION_FAILED")
    return normalized


def _status(value: str) -> str:
    try:
        return PaperStatus(value).value
    except ValueError as exc:
        raise PaperCommandError("COMMAND_VALIDATION_FAILED") from exc


def _snapshot(
    paper_id: UUID,
    row_version: int,
    *,
    title: str,
    status: str,
    current_version_id: UUID | None,
    deleted_at: datetime | None,
) -> bytes:
    return rfc8785.dumps(
        {
            "schema_version": "1.0",
            "entity_type": "Paper",
            "entity_id": str(paper_id),
            "row_version": row_version,
            "fields": {
                "title": title,
                "status": status,
                "current_version_id": (
                    str(current_version_id) if current_version_id else None
                ),
                "deleted_at": (
                    deleted_at.isoformat().replace("+00:00", "Z")
                    if deleted_at
                    else None
                ),
            },
        }
    )


def _event(paper_id: UUID, row_version: int, fields: tuple[str, ...]) -> bytes:
    return rfc8785.dumps(
        {
            "entity_id": str(paper_id),
            "row_version": row_version,
            "changed_fields": list(fields),
        }
    )


def create_paper(
    command_id: UUID,
    paper_id: UUID,
    title: str,
    status: str,
    now: datetime,
) -> DomainMutation:
    del command_id, now
    clean_title, clean_status = _title(title), _status(status)
    fields = ("current_version_id", "deleted_at", "status", "title")
    after = _snapshot(
        paper_id,
        1,
        title=clean_title,
        status=clean_status,
        current_version_id=None,
        deleted_at=None,
    )
    return DomainMutation(
        "Paper", paper_id, "create", None, None, after, fields,
        "paper.created", _event(paper_id, 1, fields),
    )


def update_paper(
    paper: Paper,
    command_id: UUID,
    *,
    title: str,
    status: str,
    now: datetime,
) -> DomainMutation:
    del command_id, now
    if paper.deleted_at is not None:
        raise PaperCommandError("COMMAND_VALIDATION_FAILED")
    clean_title, clean_status = _title(title), _status(status)
    changed = tuple(
        name
        for name, before, after in (
            ("status", paper.status.value, clean_status),
            ("title", paper.title, clean_title),
        )
        if before != after
    )
    if not changed:
        raise PaperCommandError("COMMAND_VALIDATION_FAILED")
    return _change(
        paper, "update", clean_title, clean_status, paper.current_version_id,
        None, changed, "paper.updated",
    )


def soft_delete_paper(
    paper: Paper,
    command_id: UUID,
    now: datetime,
    dependencies: PaperDependencies,
) -> DomainMutation:
    del command_id
    if paper.deleted_at is not None or dependencies.any:
        code = "DELETE_DEPENDENCY_CONFLICT" if dependencies.any else "COMMAND_VALIDATION_FAILED"
        raise PaperCommandError(code)
    return _change(
        paper, "soft_delete", paper.title, paper.status.value,
        paper.current_version_id, now, ("deleted_at",), "paper.deleted",
    )


def restore_paper(paper: Paper, command_id: UUID, now: datetime) -> DomainMutation:
    del command_id, now
    if paper.deleted_at is None:
        raise PaperCommandError("COMMAND_VALIDATION_FAILED")
    return _change(
        paper, "restore", paper.title, paper.status.value,
        paper.current_version_id, None, ("deleted_at",), "paper.restored",
    )


def set_current_version(
    paper: Paper,
    command_id: UUID,
    version: PaperVersionRef | None,
    now: datetime,
) -> DomainMutation:
    del command_id, now
    if version is not None and (
        version.paper_id != paper.id or version.lifecycle_state != "active"
    ):
        raise PaperCommandError("INVALID_VERSION_ASSIGNMENT")
    identity = version.id if version else None
    return _change(
        paper, "update", paper.title, paper.status.value, identity,
        paper.deleted_at, ("current_version_id",), "paper.updated",
    )


def _change(
    paper: Paper,
    operation: str,
    title: str,
    status: str,
    current_version_id: UUID | None,
    deleted_at: datetime | None,
    changed: tuple[str, ...],
    event_type: str,
) -> DomainMutation:
    before = _snapshot(
        paper.id, paper.row_version, title=paper.title, status=paper.status.value,
        current_version_id=paper.current_version_id, deleted_at=paper.deleted_at,
    )
    after_version = paper.row_version + 1
    after = _snapshot(
        paper.id, after_version, title=title, status=status,
        current_version_id=current_version_id, deleted_at=deleted_at,
    )
    return DomainMutation(
        "Paper", paper.id, operation, paper.row_version, before, after,
        tuple(sorted(changed)), event_type, _event(paper.id, after_version, tuple(sorted(changed))),
    )
