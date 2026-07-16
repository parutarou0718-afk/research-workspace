"""Outer actor validation and creation of non-reusable permission snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from research_workspace.domain.capabilities import (
    CAPABILITY_REGISTRY,
    PathScope,
    PermissionContext,
)


@dataclass(frozen=True)
class RawActorEnvelope:
    actor_type: str
    actor_id: str | None


@dataclass(frozen=True)
class AuthorizationRequest:
    actor: RawActorEnvelope
    workspace_id: UUID
    requested_capability: str
    scope_refs: tuple[str, ...]
    path_scopes: tuple[PathScope, ...]
    granted_at: datetime
    policy_version: str
    authorization_decision_id: UUID


class AuthorizationFailure(ValueError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def authorize_request(request: AuthorizationRequest) -> PermissionContext:
    if request.actor.actor_type in {"agent", "task_executor"}:
        raise AuthorizationFailure("ACTOR_NOT_ENABLED")
    if request.actor.actor_type not in {"user", "system"}:
        raise AuthorizationFailure("COMMAND_PERMISSION_DENIED")
    try:
        capability = CAPABILITY_REGISTRY.require(request.requested_capability)
    except ValueError as exc:
        raise AuthorizationFailure("COMMAND_PERMISSION_DENIED") from exc
    return PermissionContext(
        schema_version="1.0",
        actor_type=request.actor.actor_type,
        actor_id=request.actor.actor_id,
        workspace_id=request.workspace_id,
        capabilities=(capability,),
        scope_refs=tuple(request.scope_refs),
        path_scopes=tuple(request.path_scopes),
        network_allowed=False,
        granted_at=request.granted_at,
        policy_version=request.policy_version,
        authorization_decision_id=request.authorization_decision_id,
    )
