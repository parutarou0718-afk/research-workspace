"""Pure protected-write plans for Submission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import rfc8785

from research_workspace.application.services.command_dispatcher import DomainMutation
from research_workspace.domain.entities import Submission
from research_workspace.domain.enums import SubmissionStatus


class SubmissionCommandError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class SubmissionVersionRef:
    id: UUID
    paper_id: UUID
    lifecycle_state: str


@dataclass(frozen=True, slots=True)
class SubmissionDependencies:
    active_version: bool = False
    active_evidence_refs: int = 0
    active_relations: int = 0

    @property
    def any(self) -> bool:
        return self.active_version or bool(
            self.active_evidence_refs or self.active_relations
        )


_S = SubmissionStatus
_PRE = frozenset({_S.PREPARING, _S.READY})
_TRANSITION_VALUES = {
    _S.PREPARING: "ready",
    _S.READY: "preparing submitted",
    _S.SUBMITTED: "editorial_review external_review revision accepted rejected withdrawn no_response",
    _S.EDITORIAL_REVIEW: "external_review revision accepted rejected withdrawn no_response",
    _S.EXTERNAL_REVIEW: "revision accepted rejected withdrawn no_response",
    _S.REVISION: "submitted editorial_review external_review accepted rejected withdrawn no_response",
    _S.NO_RESPONSE: "editorial_review external_review revision accepted rejected withdrawn",
    _S.REJECTED: "revision",
    _S.ACCEPTED: "withdrawn",
    _S.WITHDRAWN: "",
}
_TRANSITIONS = {
    old: frozenset(_S(value) for value in values.split())
    for old, values in _TRANSITION_VALUES.items()
}


def is_submission_transition_allowed(old: _S, new: _S) -> bool:
    return new in _TRANSITIONS[old]


def _error(code: str = "COMMAND_VALIDATION_FAILED") -> None:
    raise SubmissionCommandError(code)


def _venue(value: str) -> str:
    result = value.strip()
    if not 1 <= len(result) <= 500:
        _error()
    return result


def _status(value: str) -> _S:
    try:
        return _S(value)
    except ValueError:
        _error()


def _version_id(
    paper_id: UUID, status: _S, version: SubmissionVersionRef | None
) -> UUID | None:
    invalid = version is not None and (
        version.paper_id != paper_id or version.lifecycle_state != "active"
    )
    if invalid or (status not in _PRE and version is None):
        _error("INVALID_VERSION_ASSIGNMENT")
    return version.id if version else None


def _validate(
    paper_id: UUID, status: _S, submitted_at: datetime | None,
    version: SubmissionVersionRef | None, now: datetime,
) -> UUID | None:
    if (status in _PRE) != (submitted_at is None):
        _error()
    if submitted_at is not None and submitted_at > now + timedelta(minutes=5):
        _error()
    return _version_id(paper_id, status, version)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _snapshot(
    submission_id: UUID, row_version: int, paper_id: UUID, venue: str,
    status: _S, submitted_at: datetime | None, deadline_at: datetime | None,
    active_version_id: UUID | None, deleted_at: datetime | None,
) -> bytes:
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Submission",
        "entity_id": str(submission_id), "row_version": row_version,
        "fields": {
            "paper_id": str(paper_id), "venue": venue, "status": status.value,
            "submitted_at": _iso(submitted_at), "deadline_at": _iso(deadline_at),
            "active_version_id": str(active_version_id) if active_version_id else None,
            "deleted_at": _iso(deleted_at),
        },
    })


def _entity_event(
    submission_id: UUID, row_version: int, changed: tuple[str, ...]
) -> bytes:
    return rfc8785.dumps({
        "entity_id": str(submission_id), "row_version": row_version,
        "changed_fields": list(changed),
    })


def create_submission(
    command_id: UUID, submission_id: UUID, paper_id: UUID, venue: str,
    status: str, submitted_at: datetime | None, deadline_at: datetime | None,
    active_version: SubmissionVersionRef | None, now: datetime,
) -> DomainMutation:
    del command_id
    state = _status(status)
    version_id = _validate(paper_id, state, submitted_at, active_version, now)
    fields = (
        "active_version_id", "deadline_at", "deleted_at", "paper_id",
        "status", "submitted_at", "venue",
    )
    after = _snapshot(
        submission_id, 1, paper_id, _venue(venue), state, submitted_at,
        deadline_at, version_id, None,
    )
    return DomainMutation(
        "Submission", submission_id, "create", None, None, after, fields,
        "submission.created", _entity_event(submission_id, 1, fields),
    )


def update_submission(
    submission: Submission, command_id: UUID, *, venue: str,
    deadline_at: datetime | None, active_version: SubmissionVersionRef | None,
    now: datetime,
) -> DomainMutation:
    del command_id
    if submission.deleted_at is not None:
        _error()
    version_id = _validate(
        submission.paper_id, submission.status, submission.submitted_at,
        active_version, now,
    )
    clean_venue = _venue(venue)
    values = (
        ("active_version_id", submission.active_version_id, version_id),
        ("deadline_at", submission.deadline_at, deadline_at),
        ("venue", submission.venue, clean_venue),
    )
    changed = tuple(name for name, before, after in values if before != after)
    if not changed:
        _error()
    return _change(
        submission, "update", submission.paper_id, clean_venue,
        submission.status, submission.submitted_at, deadline_at, version_id,
        None, changed, "submission.updated",
    )


def transition_submission(
    submission: Submission, command_id: UUID, new_status: str, *,
    submitted_at: datetime | None, active_version: SubmissionVersionRef | None,
    now: datetime, confirm_accepted_withdrawal: bool = False,
) -> DomainMutation:
    del command_id
    target = _status(new_status)
    if not is_submission_transition_allowed(submission.status, target):
        _error("INVALID_SUBMISSION_TRANSITION")
    if (
        submission.status is _S.ACCEPTED and target is _S.WITHDRAWN
        and not confirm_accepted_withdrawal
    ):
        _error("COMMAND_CONFIRMATION_REQUIRED")
    first_time = submission.submitted_at
    if target not in _PRE and first_time is None:
        first_time = submitted_at
    version_id = _validate(
        submission.paper_id, target, first_time, active_version, now
    )
    changed = ("status",)
    if version_id != submission.active_version_id:
        changed = ("active_version_id", "status")
    return _change(
        submission, "transition", submission.paper_id, submission.venue, target,
        first_time, submission.deadline_at, version_id, submission.deleted_at,
        changed, "submission.status_changed",
    )


def reassign_submission_paper(
    submission: Submission, command_id: UUID, paper_id: UUID, now: datetime,
    dependencies: SubmissionDependencies,
) -> DomainMutation:
    del command_id, now
    if (
        submission.status not in _PRE or submission.active_version_id is not None
        or dependencies.any or paper_id == submission.paper_id
    ):
        _error("SUBMISSION_REASSIGNMENT_CONFLICT")
    return _change(
        submission, "reassign_paper", paper_id, submission.venue,
        submission.status, None, submission.deadline_at, None,
        submission.deleted_at, ("paper_id",), "submission.updated",
    )


def soft_delete_submission(
    submission: Submission, command_id: UUID, now: datetime
) -> DomainMutation:
    del command_id
    if submission.deleted_at is not None:
        _error()
    return _change(
        submission, "soft_delete", submission.paper_id, submission.venue,
        submission.status, submission.submitted_at, submission.deadline_at,
        submission.active_version_id, now, ("deleted_at",), "submission.deleted",
    )


def restore_submission(
    submission: Submission, command_id: UUID, now: datetime
) -> DomainMutation:
    del command_id, now
    if submission.deleted_at is None:
        _error()
    return _change(
        submission, "restore", submission.paper_id, submission.venue,
        submission.status, submission.submitted_at, submission.deadline_at,
        submission.active_version_id, None, ("deleted_at",), "submission.restored",
    )


def _change(
    item: Submission, operation: str, paper_id: UUID, venue: str, status: _S,
    submitted_at: datetime | None, deadline_at: datetime | None,
    active_version_id: UUID | None, deleted_at: datetime | None,
    changed: tuple[str, ...], event_type: str,
) -> DomainMutation:
    before = _snapshot(
        item.id, item.row_version, item.paper_id, item.venue, item.status,
        item.submitted_at, item.deadline_at, item.active_version_id, item.deleted_at,
    )
    version = item.row_version + 1
    after = _snapshot(
        item.id, version, paper_id, venue, status, submitted_at, deadline_at,
        active_version_id, deleted_at,
    )
    ordered = tuple(sorted(changed))
    payload = (
        rfc8785.dumps({
            "submission_id": str(item.id), "old_status": item.status.value,
            "new_status": status.value, "row_version": version,
        })
        if event_type == "submission.status_changed"
        else _entity_event(item.id, version, ordered)
    )
    return DomainMutation(
        "Submission", item.id, operation, item.row_version, before, after,
        ordered, event_type, payload,
    )
