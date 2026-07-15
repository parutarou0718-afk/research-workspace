"""Pure capability, consent, and dormant-port contract tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import get_type_hints

import pytest

from research_workspace.application.ports.event_bus import EventBus
from research_workspace.application.ports.task_executor import TaskExecutor
from research_workspace.domain.tasks import Capability, permission_for


@pytest.mark.parametrize(
    ("capability", "action", "scope"),
    [
        (Capability.DOCUMENT_PARSER, "source.read_declared", {"source_declared": True}),
        (
            Capability.DOCUMENT_PARSER,
            "derived.write_selected_data_directory",
            {"selected_data_directory": True},
        ),
        (Capability.KNOWLEDGE, "idea_candidate.create", {}),
        (Capability.KNOWLEDGE, "relation_candidate.create", {}),
        (
            Capability.CONTEXT_RECOVERY,
            "aggregate.read_approved",
            {"aggregate_approved": True},
        ),
        (Capability.CONTEXT_RECOVERY, "candidate_snapshot.write", {}),
        (Capability.CONTEXT_RECOVERY, "evidence.write", {}),
        (Capability.EXPORT, "entities.read_selected", {"entities_selected": True}),
        (
            Capability.EXPORT,
            "export.write_user_approved_target",
            {"export_target_approved": True},
        ),
        (Capability.GRANT, "recommendation.create", {}),
    ],
)
def test_capability_matrix_allows_only_approved_scoped_actions(capability, action, scope):
    assert permission_for(capability, action, **scope).allowed is True


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        (Capability.DOCUMENT_PARSER, "source.read_declared"),
        (Capability.DOCUMENT_PARSER, "derived.write_selected_data_directory"),
        (Capability.CONTEXT_RECOVERY, "aggregate.read_approved"),
        (Capability.EXPORT, "entities.read_selected"),
        (Capability.EXPORT, "export.write_user_approved_target"),
    ],
)
def test_resource_scoped_actions_are_denied_without_matching_scope(capability, action):
    assert permission_for(capability, action).allowed is False


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        (Capability.KNOWLEDGE, "relation.confirm"),
        (Capability.KNOWLEDGE, "relation.reject"),
        (Capability.KNOWLEDGE, "confirmed_data.overwrite"),
        (Capability.KNOWLEDGE, "confirmed_data.delete"),
        (Capability.CONTEXT_RECOVERY, "source_entity.modify"),
        (Capability.GRANT, "external_submission.create"),
        (Capability.GRANT, "state.modify"),
        (Capability.DOCUMENT_PARSER, "source.write"),
        (Capability.EXPORT, "filesystem.write_arbitrary"),
    ],
)
def test_capability_matrix_denies_unapproved_or_source_mutating_actions(
    capability, action
):
    assert permission_for(capability, action).allowed is False


def test_knowledge_capability_cannot_confirm_relation():
    assert permission_for(Capability.KNOWLEDGE, "relation.confirm").allowed is False


@pytest.mark.parametrize("action", ["status_transition.propose", "status_transition.apply"])
def test_submission_transition_requires_user_request_and_audit(action):
    assert permission_for(Capability.SUBMISSION, action).allowed is False
    assert permission_for(
        Capability.SUBMISSION, action, user_requested=True, audited=False
    ).allowed is False
    assert permission_for(
        Capability.SUBMISSION, action, user_requested=True, audited=True
    ).allowed is True


@pytest.mark.parametrize(
    ("local_only", "provider_selected", "user_consented", "data_range_disclosed"),
    [
        (True, True, True, True),
        (False, False, True, True),
        (False, True, False, True),
        (False, True, True, False),
    ],
)
def test_network_access_is_denied_when_any_consent_gate_is_missing(
    local_only, provider_selected, user_consented, data_range_disclosed
):
    assert permission_for(
        Capability.CONTEXT_RECOVERY,
        "network.access",
        local_only=local_only,
        provider_selected=provider_selected,
        user_consented=user_consented,
        data_range_disclosed=data_range_disclosed,
    ).allowed is False


def test_network_access_requires_all_consent_gates():
    assert permission_for(
        Capability.CONTEXT_RECOVERY,
        "network.access",
        local_only=False,
        provider_selected=True,
        user_consented=True,
        data_range_disclosed=True,
    ).allowed is True


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        (Capability.DOCUMENT_PARSER, "derived.write_selected_data_directory"),
        (Capability.KNOWLEDGE, "idea_candidate.create"),
        (Capability.CONTEXT_RECOVERY, "candidate_snapshot.write"),
        (Capability.SUBMISSION, "status_transition.apply"),
        (Capability.EXPORT, "export.write_user_approved_target"),
    ],
)
def test_dry_run_denies_persistent_domain_and_external_writes(capability, action):
    assert permission_for(
        capability,
        action,
        dry_run=True,
        user_requested=True,
        audited=True,
    ).allowed is False


def test_dry_run_still_allows_scoped_reads():
    assert permission_for(
        Capability.EXPORT,
        "entities.read_selected",
        dry_run=True,
        entities_selected=True,
    ).allowed is True


def test_permission_decisions_are_immutable():
    decision = permission_for(Capability.KNOWLEDGE, "relation.confirm")

    with pytest.raises(FrozenInstanceError):
        decision.allowed = True


def test_dormant_ports_expose_the_approved_contract_methods():
    assert callable(TaskExecutor.execute)
    assert callable(EventBus.publish)
    assert callable(EventBus.subscribe)
    assert get_type_hints(TaskExecutor.execute)["return"] != type(None)
    assert get_type_hints(EventBus.publish)["return"] is type(None)
