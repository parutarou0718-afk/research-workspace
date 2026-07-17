from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from research_workspace.application.services.authorization import (
    AuthorizationFailure,
    AuthorizationRequest,
    RawActorEnvelope,
    authorize_request,
)
from research_workspace.application.services.retry_policy import (
    RETRY_POLICY_REGISTRY,
    UnknownErrorCode,
    retry_decision,
)
from research_workspace.domain.capabilities import (
    CAPABILITY_REGISTRY,
    PermissionContext,
)


def _request(actor_type: str, capability: str) -> AuthorizationRequest:
    return AuthorizationRequest(
        RawActorEnvelope(actor_type, "local-user"),
        UUID("43000000-0000-0000-0000-000000000001"),
        capability,
        ("Paper:43000000-0000-0000-0000-000000000002",),
        (),
        datetime(2026, 7, 17, tzinfo=timezone.utc),
        "1.0",
        UUID("43000000-0000-0000-0000-000000000003"),
    )


def test_gate3_request_capabilities_are_closed_and_offline() -> None:
    approved = {
        "paper.write",
        "idea.write",
        "submission.write",
        "relation.review",
        "undo.execute",
    }
    assert approved <= CAPABILITY_REGISTRY.capabilities
    for capability in approved:
        context = authorize_request(_request("user", capability))
        assert context.capabilities == (capability,)
        assert context.network_allowed is False
    with pytest.raises(AuthorizationFailure, match="COMMAND_PERMISSION_DENIED"):
        authorize_request(_request("user", "paper.admin"))


@pytest.mark.parametrize("actor_type", ["agent", "task_executor"])
def test_disabled_actor_is_rejected_before_permission_context(
    actor_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    def forbidden_init(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("PermissionContext must not be constructed")

    monkeypatch.setattr(PermissionContext, "__init__", forbidden_init)
    with pytest.raises(AuthorizationFailure, match="ACTOR_NOT_ENABLED"):
        authorize_request(_request(actor_type, "paper.write"))
    assert constructed is False


def test_historical_permission_context_is_not_an_authorization_request() -> None:
    context = authorize_request(_request("user", "paper.write"))
    with pytest.raises((AttributeError, TypeError)):
        authorize_request(context)  # type: ignore[arg-type]


def test_gate3_retry_registry_is_explicit_and_fail_closed() -> None:
    nonretryable = {
        "COMMAND_IDEMPOTENCY_CONFLICT",
        "COMMAND_VALIDATION_FAILED",
        "CONCURRENT_MODIFICATION",
        "RECOVERY_POINT_FAILED",
        "UNDO_NOT_AVAILABLE",
        "UNDO_ALREADY_APPLIED",
        "UNDO_CONFLICT",
        "UNDO_DEPENDENCY_CONFLICT",
        "UNDO_CONSTRAINT_VIOLATION",
        "DELETE_DEPENDENCY_CONFLICT",
        "INVALID_WORKFLOW_TRANSITION",
        "INVALID_VERSION_ASSIGNMENT",
        "VERSION_RETRACTION_DEPENDENCY_CONFLICT",
        "RELATION_DUPLICATE",
        "RELATION_CYCLE",
        "RELATION_ENDPOINT_INVALID",
        "CANDIDATE_STATE_CHANGED",
    }
    assert nonretryable <= RETRY_POLICY_REGISTRY.policies.keys()
    assert all(
        retry_decision(code, attempt=1).retryable is False
        for code in nonretryable
    )
    assert retry_decision("SQLITE_BUSY", attempt=1).retryable is True
    with pytest.raises(UnknownErrorCode):
        retry_decision("RELATION_LIBRARY_ERROR", attempt=1)

