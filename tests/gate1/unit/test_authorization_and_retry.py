from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from research_workspace.application.services.authorization import (
    AuthorizationRequest,
    RawActorEnvelope,
)
from research_workspace.application.services.operation_dispatcher import OperationDispatcher
from research_workspace.application.services.retry_policy import (
    RETRY_POLICY_REGISTRY,
    UnknownErrorCode,
    retry_decision,
)
from research_workspace.domain.capabilities import (
    CAPABILITY_REGISTRY,
    UnknownCapability,
)


def request(actor_type: str = "user", capability: str = "document.parse.request") -> AuthorizationRequest:
    return AuthorizationRequest(
        actor=RawActorEnvelope(actor_type, "actor-1"),
        workspace_id=UUID("30000000-0000-0000-0000-000000000001"),
        requested_capability=capability,
        scope_refs=(),
        path_scopes=(),
        granted_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        policy_version="1.0",
        authorization_decision_id=UUID("30000000-0000-0000-0000-000000000002"),
    )


@pytest.mark.parametrize("actor", ["agent", "task_executor"])
def test_disabled_actor_fails_before_permission_context_or_handler(actor: str) -> None:
    calls = []
    result = OperationDispatcher().dispatch(request(actor), lambda context: calls.append(context))
    assert result.error_code == "ACTOR_NOT_ENABLED"
    assert result.permission_context is None
    assert calls == []


def test_capability_registry_is_closed_through_gate2() -> None:
    assert CAPABILITY_REGISTRY.schema_version == "1.0"
    assert frozenset(
        {
            "source.observe.request",
            "source.snapshot_import.request",
            "document.parse.request",
            "version_candidate.detect.request",
            "maintenance.verify.request",
        }
    ) <= CAPABILITY_REGISTRY.capabilities
    with pytest.raises(UnknownCapability):
        CAPABILITY_REGISTRY.require("paper.admin")


def test_unknown_capability_fails_before_handler() -> None:
    calls = []
    result = OperationDispatcher().dispatch(request(capability="plugin.anything"), lambda _: calls.append(True))
    assert result.error_code == "COMMAND_PERMISSION_DENIED"
    assert calls == []


def test_authorized_request_builds_non_reusable_permission_snapshot() -> None:
    result = OperationDispatcher().dispatch(request(), lambda context: context.authorization_decision_id)
    assert result.error_code is None
    assert result.permission_context.actor_type == "user"
    assert result.permission_context.network_allowed is False
    with pytest.raises(ValueError, match="not a reusable credential"):
        OperationDispatcher().dispatch_context(result.permission_context, lambda _: None)


def test_retry_policy_is_closed_and_attempt_bounded() -> None:
    assert RETRY_POLICY_REGISTRY.schema_version == "1.0"
    with pytest.raises(TypeError):
        RETRY_POLICY_REGISTRY.policies["library.Exception"] = object()
    assert retry_decision("SOURCE_BUSY", attempt=1).retryable is True
    assert retry_decision("SOURCE_UNSTABLE", attempt=5).retryable is False
    assert retry_decision("PDF_PASSWORD_REQUIRED", attempt=1).retryable is False
    assert retry_decision("COMMAND_PERMISSION_DENIED", attempt=1).retryable is False
    with pytest.raises(UnknownErrorCode):
        retry_decision("library.Exception", attempt=1)
