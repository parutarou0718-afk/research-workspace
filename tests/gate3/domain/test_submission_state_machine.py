from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from research_workspace.application.commands.manage_submission import (
    SubmissionCommandError,
    SubmissionVersionRef,
    create_submission,
    transition_submission,
)
from research_workspace.domain.entities import Submission
from research_workspace.domain.enums import SubmissionStatus


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)
ALL = tuple(SubmissionStatus)
ALLOWED = {
    SubmissionStatus.PREPARING: {SubmissionStatus.READY},
    SubmissionStatus.READY: {SubmissionStatus.PREPARING, SubmissionStatus.SUBMITTED},
    SubmissionStatus.SUBMITTED: {
        SubmissionStatus.EDITORIAL_REVIEW, SubmissionStatus.EXTERNAL_REVIEW,
        SubmissionStatus.REVISION, SubmissionStatus.ACCEPTED, SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN, SubmissionStatus.NO_RESPONSE,
    },
    SubmissionStatus.EDITORIAL_REVIEW: {
        SubmissionStatus.EXTERNAL_REVIEW, SubmissionStatus.REVISION,
        SubmissionStatus.ACCEPTED, SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN, SubmissionStatus.NO_RESPONSE,
    },
    SubmissionStatus.EXTERNAL_REVIEW: {
        SubmissionStatus.REVISION, SubmissionStatus.ACCEPTED,
        SubmissionStatus.REJECTED, SubmissionStatus.WITHDRAWN,
        SubmissionStatus.NO_RESPONSE,
    },
    SubmissionStatus.REVISION: {
        SubmissionStatus.SUBMITTED, SubmissionStatus.EDITORIAL_REVIEW,
        SubmissionStatus.EXTERNAL_REVIEW, SubmissionStatus.ACCEPTED,
        SubmissionStatus.REJECTED, SubmissionStatus.WITHDRAWN,
        SubmissionStatus.NO_RESPONSE,
    },
    SubmissionStatus.NO_RESPONSE: {
        SubmissionStatus.EDITORIAL_REVIEW, SubmissionStatus.EXTERNAL_REVIEW,
        SubmissionStatus.REVISION, SubmissionStatus.ACCEPTED,
        SubmissionStatus.REJECTED, SubmissionStatus.WITHDRAWN,
    },
    SubmissionStatus.REJECTED: {SubmissionStatus.REVISION},
    SubmissionStatus.ACCEPTED: {SubmissionStatus.WITHDRAWN},
    SubmissionStatus.WITHDRAWN: set(),
}


def _submission(status: SubmissionStatus) -> Submission:
    paper_id = uuid4()
    submitted_at = None if status in {SubmissionStatus.PREPARING, SubmissionStatus.READY} else NOW
    active_version_id = None if submitted_at is None else uuid4()
    return Submission(
        uuid4(), paper_id, "Venue", status, submitted_at, None, active_version_id,
        NOW, NOW, None, 1, uuid4(), uuid4(), None,
    )


def _version(submission: Submission) -> SubmissionVersionRef:
    return SubmissionVersionRef(
        submission.active_version_id or uuid4(), submission.paper_id, "active"
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [(old, new) for old in ALL for new in ALL if old != new],
    ids=lambda value: value.value,
)
def test_exact_transition_table(old: SubmissionStatus, new: SubmissionStatus) -> None:
    submission = _submission(old)
    accepted = new in ALLOWED[old]
    kwargs = {
        "submitted_at": submission.submitted_at or NOW,
        "active_version": _version(submission),
        "now": NOW,
        "confirm_accepted_withdrawal": old is SubmissionStatus.ACCEPTED,
    }
    if accepted:
        mutation = transition_submission(submission, uuid4(), new.value, **kwargs)
        assert mutation.event_type == "submission.status_changed"
    else:
        with pytest.raises(SubmissionCommandError, match="INVALID_SUBMISSION_TRANSITION"):
            transition_submission(submission, uuid4(), new.value, **kwargs)


def test_accepted_withdrawal_requires_explicit_confirmation() -> None:
    submission = _submission(SubmissionStatus.ACCEPTED)
    with pytest.raises(SubmissionCommandError, match="COMMAND_CONFIRMATION_REQUIRED"):
        transition_submission(
            submission, uuid4(), "withdrawn", submitted_at=NOW,
            active_version=_version(submission), now=NOW,
        )


def test_first_submission_time_is_preserved_on_revision_resubmission() -> None:
    first = NOW - timedelta(days=30)
    submission = _submission(SubmissionStatus.REVISION)
    submission = Submission(
        submission.id, submission.paper_id, submission.venue, submission.status,
        first, submission.deadline_at, submission.active_version_id,
        submission.created_at, submission.updated_at, submission.deleted_at,
        submission.row_version, submission.created_by_command_id,
        submission.updated_by_command_id, submission.deleted_by_command_id,
    )
    mutation = transition_submission(
        submission, uuid4(), "submitted", submitted_at=NOW,
        active_version=_version(submission), now=NOW,
    )
    assert first.isoformat().replace("+00:00", "Z").encode() in mutation.after_snapshot
    assert NOW.isoformat().replace("+00:00", "Z").encode() not in mutation.after_snapshot


def test_submitted_states_require_owned_active_version_and_nonfuture_time() -> None:
    paper_id = uuid4()
    with pytest.raises(SubmissionCommandError, match="INVALID_VERSION_ASSIGNMENT"):
        create_submission(
            uuid4(), uuid4(), paper_id, "Venue", "submitted", NOW, None, None, NOW
        )
    wrong = SubmissionVersionRef(uuid4(), uuid4(), "active")
    with pytest.raises(SubmissionCommandError, match="INVALID_VERSION_ASSIGNMENT"):
        create_submission(
            uuid4(), uuid4(), paper_id, "Venue", "submitted", NOW, None, wrong, NOW
        )
    owned = SubmissionVersionRef(uuid4(), paper_id, "active")
    with pytest.raises(SubmissionCommandError, match="COMMAND_VALIDATION_FAILED"):
        create_submission(
            uuid4(), uuid4(), paper_id, "Venue", "submitted",
            NOW + timedelta(minutes=5, seconds=1), None, owned, NOW,
        )
    assert create_submission(
        uuid4(), uuid4(), paper_id, "Venue", "submitted",
        NOW - timedelta(days=365), None, owned, NOW,
    ).event_type == "submission.created"


def test_preparing_and_ready_forbid_submitted_at() -> None:
    for status in ("preparing", "ready"):
        with pytest.raises(SubmissionCommandError, match="COMMAND_VALIDATION_FAILED"):
            create_submission(
                uuid4(), uuid4(), uuid4(), "Venue", status, NOW, None, None, NOW
            )


def test_future_deadline_is_allowed() -> None:
    assert create_submission(
        uuid4(), uuid4(), uuid4(), "Venue", "preparing", None,
        NOW + timedelta(days=365), None, NOW,
    ).event_type == "submission.created"
