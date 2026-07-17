"""Read projection for Submission commands and pages."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Submission
from research_workspace.domain.enums import SubmissionStatus
from research_workspace.application.commands.manage_submission import (
    is_submission_transition_allowed,
)


class SubmissionReadRepository(Protocol):
    def get_submission(self, submission_id: UUID) -> Submission | None: ...
    def list_submissions(
        self, *, include_deleted: bool = False
    ) -> tuple[Submission, ...]: ...


@dataclass(frozen=True, slots=True)
class SubmissionReadModel:
    id: UUID
    paper_id: UUID
    venue: str
    status: str
    submitted_at: datetime | None
    deadline_at: datetime | None
    active_version_id: UUID | None
    deleted_at: datetime | None
    row_version: int
    allowed_transitions: tuple[str, ...]
    actions: tuple[str, ...]


def project_submission(submission: Submission) -> SubmissionReadModel:
    transitions = tuple(
        status.value
        for status in SubmissionStatus
        if is_submission_transition_allowed(submission.status, status)
    )
    actions = (
        ("restore",)
        if submission.deleted_at is not None
        else ("edit", "soft_delete", "transition")
    )
    return SubmissionReadModel(
        submission.id, submission.paper_id, submission.venue,
        submission.status.value, submission.submitted_at,
        submission.deadline_at, submission.active_version_id,
        submission.deleted_at, submission.row_version, transitions, actions,
    )


class GetSubmissionsQuery:
    def __init__(self, repository: SubmissionReadRepository) -> None:
        self._repository = repository

    def get(self, submission_id: UUID) -> Submission:
        submission = self._repository.get_submission(submission_id)
        if submission is None:
            raise LookupError("SUBMISSION_NOT_FOUND")
        return submission

    def list(self, *, include_deleted: bool = False) -> tuple[Submission, ...]:
        return self._repository.list_submissions(include_deleted=include_deleted)

    def project(
        self, *, include_deleted: bool = False
    ) -> tuple[SubmissionReadModel, ...]:
        return tuple(
            project_submission(submission)
            for submission in self._repository.list_submissions(
                include_deleted=include_deleted
            )
        )
