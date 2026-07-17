from datetime import datetime, timezone
from uuid import UUID

import pytest

from research_workspace.application.services.authorization import (
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
    EXECUTION_ROLE_REGISTRY,
    PathScope,
    UnknownCapability,
    UnknownExecutionRole,
)


def _request(actor_type: str, capability: str) -> AuthorizationRequest:
    return AuthorizationRequest(
        RawActorEnvelope(actor_type, "local-user"),
        UUID("41000000-0000-0000-0000-000000000001"),
        capability,
        (),
        (
            PathScope(
                "monitoring_root",
                "a" * 64,
                UUID("41000000-0000-0000-0000-000000000002"),
                "list",
                True,
            ),
        ),
        datetime(2026, 7, 17, tzinfo=timezone.utc),
        "1.0",
        UUID("41000000-0000-0000-0000-000000000003"),
    )


def test_gate2_capabilities_and_execution_roles_are_closed() -> None:
    assert CAPABILITY_REGISTRY.require("source.observe.request") == "source.observe.request"
    assert (
        CAPABILITY_REGISTRY.require("version_candidate.detect.request")
        == "version_candidate.detect.request"
    )
    assert EXECUTION_ROLE_REGISTRY.require("source_observer") == "source_observer"
    assert EXECUTION_ROLE_REGISTRY.require("candidate_detector") == "candidate_detector"
    with pytest.raises(UnknownCapability):
        CAPABILITY_REGISTRY.require("monitor.anything")
    with pytest.raises(UnknownExecutionRole):
        EXECUTION_ROLE_REGISTRY.require("agent")


def test_gate2_permission_snapshot_has_no_network_or_reusable_authority() -> None:
    context = authorize_request(_request("user", "source.observe.request"))
    assert context.network_allowed is False
    assert context.capabilities == ("source.observe.request",)
    assert context.path_scopes[0].scope_type == "monitoring_root"


@pytest.mark.parametrize("actor_type", ["agent", "task_executor"])
def test_disabled_actor_is_rejected_before_permission_context(actor_type: str) -> None:
    with pytest.raises(ValueError, match="ACTOR_NOT_ENABLED"):
        authorize_request(_request(actor_type, "source.observe.request"))


def test_gate2_retry_registry_retries_only_named_temporary_failures() -> None:
    disconnected = retry_decision("MONITOR_ROOT_DISCONNECTED", attempt=1)
    assert disconnected.retryable is True
    assert disconnected.requires_revalidation is True
    assert retry_decision("SOURCE_BUSY", attempt=1).retryable is True
    for code in (
        "COMMAND_PERMISSION_DENIED",
        "SOURCE_PATH_UNSAFE",
        "SOURCE_HASH_MISMATCH",
        "PDF_CORRUPT",
    ):
        assert retry_decision(code, attempt=1).retryable is False
    with pytest.raises(UnknownErrorCode):
        retry_decision("watchdog.LibraryException", attempt=1)
    with pytest.raises(TypeError):
        RETRY_POLICY_REGISTRY.policies["MONITOR_ANYTHING"] = object()
