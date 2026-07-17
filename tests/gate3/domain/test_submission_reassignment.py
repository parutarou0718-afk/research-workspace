from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from research_workspace.application.commands.manage_submission import (
    SubmissionCommandError,
    SubmissionDependencies,
    reassign_submission_paper,
    restore_submission,
    soft_delete_submission,
    update_submission,
)
from research_workspace.domain.entities import Submission
from research_workspace.domain.enums import SubmissionStatus


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _submission(status=SubmissionStatus.PREPARING, active_version_id=None) -> Submission:
    return Submission(
        uuid4(), uuid4(), "Venue", status,
        None if status in {SubmissionStatus.PREPARING, SubmissionStatus.READY} else NOW,
        None, active_version_id, NOW, NOW, None, 1, uuid4(), uuid4(), None,
    )


def test_ordinary_edit_has_no_paper_reassignment_surface() -> None:
    submission = _submission()
    mutation = update_submission(
        submission, uuid4(), venue="New Venue", deadline_at=None,
        active_version=None, now=NOW,
    )
    assert str(submission.paper_id).encode() in mutation.after_snapshot
    with pytest.raises(TypeError):
        update_submission(
            submission, uuid4(), venue="Venue", deadline_at=None,
            active_version=None, now=NOW, paper_id=uuid4(),
        )


@pytest.mark.parametrize(
    "dependencies",
    [
        SubmissionDependencies(active_version=True),
        SubmissionDependencies(active_evidence_refs=1),
        SubmissionDependencies(active_relations=1),
    ],
)
def test_reassignment_rejects_incompatible_dependencies(dependencies) -> None:
    with pytest.raises(SubmissionCommandError, match="SUBMISSION_REASSIGNMENT_CONFLICT"):
        reassign_submission_paper(_submission(), uuid4(), uuid4(), NOW, dependencies)


def test_reassignment_is_pre_submission_only() -> None:
    for status in SubmissionStatus:
        submission = _submission(status)
        if status in {SubmissionStatus.PREPARING, SubmissionStatus.READY}:
            mutation = reassign_submission_paper(
                submission, uuid4(), uuid4(), NOW, SubmissionDependencies()
            )
            assert mutation.operation == "reassign_paper"
        else:
            with pytest.raises(
                SubmissionCommandError, match="SUBMISSION_REASSIGNMENT_CONFLICT"
            ):
                reassign_submission_paper(
                    submission, uuid4(), uuid4(), NOW, SubmissionDependencies()
                )


def test_soft_delete_and_restore_are_row_versioned_mutations() -> None:
    submission = _submission()
    deleted = soft_delete_submission(submission, uuid4(), NOW)
    assert deleted.operation == "soft_delete"
    deleted_record = Submission(
        submission.id, submission.paper_id, submission.venue, submission.status,
        submission.submitted_at, submission.deadline_at,
        submission.active_version_id, submission.created_at, NOW, NOW, 2,
        submission.created_by_command_id, uuid4(), uuid4(),
    )
    restored = restore_submission(deleted_record, uuid4(), NOW)
    assert restored.operation == "restore"
    assert b'"deleted_at":null' in restored.after_snapshot
