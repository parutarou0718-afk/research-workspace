from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest

from research_workspace.domain.entities import (
    DomainEvent,
    EvidenceRef,
    PaperVersion,
    Submission,
    Task,
    TaskAttempt,
    TaskEffect,
)
from research_workspace.domain.enums import (
    EvidenceTargetType,
    EventType,
    PaperStatus,
    SubmissionStatus,
    TaskEffectStatus,
    TaskType,
)
from research_workspace.domain.tasks import TaskStatus
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


def test_domain_model_entity_fields_match_every_frozen_dataclass_exactly():
    contract_path = Path(__file__).parents[3] / "contracts" / "domain_model.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    from research_workspace.domain import entities

    approved_names = {
        "Paper",
        "PaperVersion",
        "Idea",
        "Note",
        "SourceDocument",
        "Submission",
        "Conference",
        "Grant",
        "EvidenceRef",
        "EntityRelation",
        "RelationObservation",
        "Task",
        "TaskAttempt",
        "TaskEffect",
        "AuditLog",
        "DomainEvent",
    }
    gate1_names = set(contract["gate1_entities"]) - {"SourceDocument", "DomainEvent"}
    implementation_types = {
        name: value
        for name, value in inspect.getmembers(entities, inspect.isclass)
        if value.__module__ == entities.__name__ and is_dataclass(value)
    }

    assert set(contract["entities"]) == approved_names
    assert set(implementation_types) == approved_names | gate1_names
    for entity_type in implementation_types.values():
        assert is_dataclass(entity_type)
        assert entity_type.__dataclass_params__.frozen is True
    assert {
        name: [field.name for field in fields(implementation_types[name])]
        for name in approved_names | gate1_names
    } == {
        **{
            name: contract["gate3_entities"].get(name, fields)
            if name in {"Paper", "Idea", "Submission"}
            else fields
            for name, fields in contract["entities"].items()
        },
        **{name: contract["gate1_entities"][name] for name in gate1_names},
    }


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
    assert {item.value for item in EventType} == {
        "document.imported", "paper.created", "paper.version_added",
        "paper.version_relation_corrected", "idea.created", "idea.candidate_extracted",
        "idea.linked", "submission.created", "submission.status_changed",
        "context.recovered", "task.failed", "audit.undo_applied",
        "source.snapshot_imported", "source.snapshot_reused",
        "document.parse_succeeded", "document.parse_failed",
    }


def test_mapping_fields_are_detached_and_recursively_immutable():
    locator = {"heading_path": ["Intro"], "metadata": {"rank": 1}}
    evidence = EvidenceRef(
        "evidence", EvidenceTargetType.PAPER, "paper", "document", None,
        None, None, None, None, None, None, locator, "hash", NOW,
    )
    locator["heading_path"].append("Mutated")
    locator["metadata"]["rank"] = 2
    assert evidence.locator_json == {
        "heading_path": ("Intro",), "metadata": {"rank": 1}
    }
    with pytest.raises(TypeError):
        evidence.locator_json["new"] = "value"
    with pytest.raises(TypeError):
        evidence.locator_json["metadata"]["rank"] = 3


def test_all_json_snapshot_fields_detach_nested_caller_values():
    payload = {"nested": [{"value": 1}]}
    task = Task(
        "task", TaskType.IMPORT_DOCUMENT, TaskStatus.PENDING, "key", "f" * 64,
        payload, payload, 0, 3, None, None, None, 0, NOW, None, None,
    )
    payload["nested"][0]["value"] = 9
    assert task.payload_json["nested"][0]["value"] == 1
    assert task.result_json["nested"][0]["value"] == 1
    with pytest.raises(TypeError):
        task.payload_json["nested"][0]["value"] = 2


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


def test_unknown_submission_status_fails_closed():
    assert validate_submission_timing("invented", None) == (
        "unknown submission status: invented",
    )


def test_submission_requires_timestamp_for_review_state():
    assert validate_submission_timing("external_review", None) == (
        "submitted_at is required for external_review",
    )


def test_current_version_must_belong_to_paper_and_be_current():
    assert validate_current_version_ownership("paper-a", None) == ()
    assert validate_current_version_ownership(
        "paper-a", "version-a", version_resolved=False
    ) == ("current version could not be resolved",)
    assert validate_current_version_ownership(
        "paper-a", "version-a", version_resolved=True, version_id="version-b",
        version_paper_id="paper-a", version_is_current=True,
    ) == ("resolved current version does not match current_version_id",)
    assert validate_current_version_ownership(
        "paper-a", "version-a", version_resolved=True, version_id="version-a",
        version_paper_id="paper-b", version_is_current=True,
    ) == (
        "current version must belong to the paper",
    )
    assert validate_current_version_ownership(
        "paper-a", "version-a", version_resolved=True, version_id="version-a",
        version_paper_id="paper-a", version_is_current=False,
    ) == (
        "current version must have is_current=true",
    )
    assert validate_current_version_ownership(
        "paper-a", "version-a", version_resolved=True, version_id="version-a",
        version_paper_id="paper-a", version_is_current=True,
    ) == ()


def test_parent_and_submission_versions_must_belong_to_their_paper():
    assert validate_parent_version_ownership("paper-a", None) == ()
    assert validate_parent_version_ownership(
        "paper-a", "parent-a", parent_resolved=False
    ) == ("parent version could not be resolved",)
    assert validate_parent_version_ownership(
        "paper-a", "parent-a", parent_resolved=True,
        parent_id="parent-b", parent_paper_id="paper-a",
    ) == ("resolved parent version does not match parent_version_id",)
    assert validate_parent_version_ownership(
        "paper-a", "parent-a", parent_resolved=True,
        parent_id="parent-a", parent_paper_id="paper-b",
    ) == (
        "parent version must belong to the same paper",
    )
    assert validate_parent_version_ownership(
        "paper-a", "parent-a", parent_resolved=True,
        parent_id="parent-a", parent_paper_id="paper-a",
    ) == ()
    assert validate_submission_version_ownership("paper-a", None) == ()
    assert validate_submission_version_ownership(
        "paper-a", "version-a", version_resolved=False
    ) == ("active submission version could not be resolved",)
    assert validate_submission_version_ownership(
        "paper-a", "version-a", version_resolved=True,
        version_id="version-b", version_paper_id="paper-a",
    ) == ("resolved active version does not match active_version_id",)
    assert validate_submission_version_ownership(
        "paper-a", "version-a", version_resolved=True,
        version_id="version-a", version_paper_id="paper-b",
    ) == (
        "active submission version must belong to the submission paper",
    )
    assert validate_submission_version_ownership(
        "paper-a", "version-a", version_resolved=True,
        version_id="version-a", version_paper_id="paper-a",
    ) == ()


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
        uuid4(), uuid4(), "Venue", SubmissionStatus.READY,
        None, None, None, NOW, NOW, None, 1, uuid4(), uuid4(), None,
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
