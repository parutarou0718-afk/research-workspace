"""Pure retry and lease state-transition tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from research_workspace.domain.tasks import (
    AttemptStatus,
    TaskStatus,
    decide_attempt_outcome,
    eligible_for_lease,
    expired_lease_decision,
)


NOW = datetime(2026, 7, 16, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "next_attempt_at", "attempt_count", "max_attempts", "expected"),
    [
        (TaskStatus.PENDING, None, 0, 3, True),
        (TaskStatus.PENDING, NOW, 1, 3, True),
        (TaskStatus.PENDING, NOW + timedelta(seconds=1), 1, 3, False),
        (TaskStatus.RUNNING, NOW - timedelta(seconds=1), 1, 3, False),
        (TaskStatus.PENDING, None, 3, 3, False),
        (TaskStatus.SUCCEEDED, None, 0, 3, False),
    ],
)
def test_only_due_pending_tasks_with_attempts_remaining_are_lease_eligible(
    status, next_attempt_at, attempt_count, max_attempts, expected
):
    assert eligible_for_lease(
        status=status,
        next_attempt_at=next_attempt_at,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        now=NOW,
    ) is expected


def test_expired_lease_with_attempts_remaining_is_due_for_retry():
    decision = expired_lease_decision(attempt_count=2, max_attempts=3, now=NOW)

    assert decision.task_status is TaskStatus.PENDING
    assert decision.attempt_status is AttemptStatus.RETRY_SCHEDULED
    assert decision.error_code == "EXECUTOR_LEASE_EXPIRED"
    assert decision.retryable is True
    assert decision.retry_at == NOW


def test_expired_retrying_lease_requires_the_due_time():
    with pytest.raises(ValueError, match="now"):
        expired_lease_decision(attempt_count=2, max_attempts=3)


def test_expired_final_lease_is_terminalized():
    decision = expired_lease_decision(attempt_count=3, max_attempts=3, now=NOW)

    assert decision.task_status is TaskStatus.FAILED
    assert decision.attempt_status is AttemptStatus.FAILED
    assert decision.error_code == "TASK_LEASE_EXHAUSTED"
    assert decision.retryable is False
    assert decision.retry_at is None


def test_retryable_error_schedules_first_retry_with_base_delay():
    decision = decide_attempt_outcome(
        attempt=1, max_attempts=3, retryable=True, now=NOW, jitter_fraction=0.0
    )

    assert decision.task_status is TaskStatus.PENDING
    assert decision.attempt_status is AttemptStatus.RETRY_SCHEDULED
    assert decision.retry_at == NOW + timedelta(seconds=5)


def test_second_and_higher_retry_delays_follow_approved_schedule():
    second = decide_attempt_outcome(
        attempt=2, max_attempts=4, retryable=True, now=NOW, jitter_fraction=0.0
    )
    third = decide_attempt_outcome(
        attempt=3, max_attempts=4, retryable=True, now=NOW, jitter_fraction=0.0
    )

    assert second.retry_at == NOW + timedelta(seconds=30)
    assert third.retry_at == NOW + timedelta(minutes=5)


def test_retry_delay_includes_supplied_bounded_jitter():
    decision = decide_attempt_outcome(
        attempt=1, max_attempts=3, retryable=True, now=NOW, jitter_fraction=0.2
    )

    assert decision.retry_at == NOW + timedelta(seconds=6)


def test_final_retryable_attempt_becomes_terminal_failure():
    decision = decide_attempt_outcome(
        attempt=3,
        max_attempts=3,
        retryable=True,
        error_code="CONNECTOR_TIMEOUT",
        error_details={"provider": "example"},
    )

    assert decision.task_status is TaskStatus.FAILED
    assert decision.attempt_status is AttemptStatus.FAILED
    assert decision.retry_at is None
    assert decision.retries_exhausted is True
    assert decision.error_code == "CONNECTOR_TIMEOUT"
    assert decision.error_details == {
        "provider": "example",
        "retries_exhausted": True,
    }


def test_error_details_on_a_decision_are_immutable():
    supplied = {"nested": {"items": ["original"]}}
    decision = decide_attempt_outcome(
        attempt=3,
        max_attempts=3,
        retryable=True,
        error_details=supplied,
    )

    supplied["nested"]["items"].append("caller mutation")
    assert decision.error_details["nested"]["items"] == ("original",)
    with pytest.raises(TypeError):
        decision.error_details["nested"]["changed"] = True
    with pytest.raises(AttributeError):
        decision.error_details["nested"]["items"].append("changed")


def test_non_retryable_error_is_terminal_immediately():
    decision = decide_attempt_outcome(
        attempt=1,
        max_attempts=3,
        retryable=False,
        now=NOW,
        error_code="TASK_PERMISSION_DENIED",
        error_details={"action": "relation.confirm"},
    )

    assert decision.task_status is TaskStatus.FAILED
    assert decision.retry_at is None
    assert decision.retries_exhausted is False
    assert decision.error_code == "TASK_PERMISSION_DENIED"
    assert decision.error_details == {"action": "relation.confirm"}


def test_retry_decisions_are_immutable():
    decision = expired_lease_decision(attempt_count=3, max_attempts=3)

    with pytest.raises(FrozenInstanceError):
        decision.error_code = "changed"


@pytest.mark.parametrize("jitter", [-0.01, 0.21])
def test_jitter_outside_approved_zero_to_twenty_percent_is_rejected(jitter):
    with pytest.raises(ValueError, match="jitter_fraction"):
        decide_attempt_outcome(
            attempt=1,
            max_attempts=3,
            retryable=True,
            now=NOW,
            jitter_fraction=jitter,
        )
