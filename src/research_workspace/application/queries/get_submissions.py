"""Read projection for Submission commands and pages."""

from typing import Protocol
from uuid import UUID

from research_workspace.domain.entities import Submission


class SubmissionReadRepository(Protocol):
    def get_submission(self, submission_id: UUID) -> Submission | None: ...
    def list_submissions(
        self, *, include_deleted: bool = False
    ) -> tuple[Submission, ...]: ...


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
