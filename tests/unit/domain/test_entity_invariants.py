from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from research_workspace.domain.entities import (
    DomainEvent,
    PaperVersion,
    Submission,
    Task,
    TaskAttempt,
    TaskEffect,
)
from research_workspace.domain.enums import (
    EventType,
    PaperStatus,
    SubmissionStatus,
    TaskEffectStatus,
    TaskType,
)
from research_workspace.domain.relations import (
    cached_relation_confidence,
    validate_current_version_ownership,
    validate_grant_source_url,
    validate_observation_key,
    validate_parent_version_ownership,
    validate_submission_timing,
    validate_submission_version_ownership,
)


NOW = datetime(2026, 7, 16, tzinfo=UTC)


def test_closed_status_enums_match_the_approved_values():
    assert {item.value for item in PaperStatus} == {
        "active", "paused", "revision", "submitted", "completed", "archived"
    }
    assert {item.value for item in SubmissionStatus} == {
        "preparing", "ready", "submitted", "editorial_review", "external_review",
        "revision", "accepted", "rejected", "withdrawn", "no_response",
    }


def test_foundation_entities_are_frozen_values():
    version = PaperVersion("v1", "paper-a", "doc-a", "first", None, True, NOW)
    with pytest.raises(FrozenInstanceError):
        version.version_label = "changed"


def test_operational_records_are_dormant_frozen_entity_snapshots():
    for entity_type in (Task, TaskAttempt, TaskEffect, DomainEvent):
        assert entity_type.__dataclass_params__.frozen is True
    assert {item.value for item in TaskEffectStatus} == {
        "prepared", "committed", "manual_reconciliation"
    }
    assert len(TaskType) == 7
    assert len(EventType) == 12


@pytest.mark.parametrize(
    ("status", "requires_timestamp"),
    [(status, status in {"submitted", "editorial_review", "external_review", "revision",
                         "accepted", "rejected", "no_response"})
     for status in SubmissionStatus._value2member_map_],
)
def test_submission_timestamp_requirement_matches_each_state(status, requires_timestamp):
    expected = (f"submitted_at is required for {status}",) if requires_timestamp else ()
    assert validate_submission_timing(status, None) == expected
    assert validate_submission_timing(status, NOW) == ()


def test_submission_requires_timestamp_for_review_state():
    assert validate_submission_timing("external_review", None) == (
        "submitted_at is required for external_review",
    )


def test_current_version_must_belong_to_paper_and_be_current():
    assert validate_current_version_ownership("paper-a", "paper-a", True) == ()
    assert validate_current_version_ownership("paper-a", "paper-b", True) == (
        "current version must belong to the paper",
    )
    assert validate_current_version_ownership("paper-a", "paper-a", False) == (
        "current version must have is_current=true",
    )


def test_parent_and_submission_versions_must_belong_to_their_paper():
    assert validate_parent_version_ownership("paper-a", "paper-a") == ()
    assert validate_parent_version_ownership("paper-a", "paper-b") == (
        "parent version must belong to the same paper",
    )
    assert validate_submission_version_ownership("paper-a", "paper-a") == ()
    assert validate_submission_version_ownership("paper-a", "paper-b") == (
        "active submission version must belong to the submission paper",
    )


def test_observation_keys_are_append_only_idempotency_keys():
    assert validate_observation_key("observation-2", {"observation-1"}) == ()
    assert validate_observation_key("observation-1", {"observation-1"}) == (
        "observation_key must be unique",
    )


def test_relation_confidence_is_cached_maximum_without_losing_existing_value():
    assert cached_relation_confidence(None, None) is None
    assert cached_relation_confidence(None, 0.4) == 0.4
    assert cached_relation_confidence(0.8, None) == 0.8
    assert cached_relation_confidence(0.8, 0.4) == 0.8
    assert cached_relation_confidence(0.4, 0.8) == 0.8


def test_submission_entity_uses_closed_enum_values():
    submission = Submission(
        "submission-a", "paper-a", "Venue", SubmissionStatus.READY,
        None, None, None, NOW, NOW, None,
    )
    assert submission.status is SubmissionStatus.READY


@pytest.mark.parametrize("url", [None, "https://example.org/grant", "http://example.org/grant"])
def test_grant_source_url_accepts_only_optional_absolute_http_urls(url):
    assert validate_grant_source_url(url) == ()


@pytest.mark.parametrize("url", ["/grant", "example.org/grant", "ftp://example.org/grant"])
def test_grant_source_url_rejects_non_http_or_relative_urls(url):
    assert validate_grant_source_url(url) == (
        "source_url must be an absolute http or https URL",
    )
