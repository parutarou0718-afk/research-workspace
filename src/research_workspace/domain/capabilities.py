"""Closed Gate 1 capability and permission-snapshot vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


class UnknownCapability(ValueError):
    pass


class UnknownExecutionRole(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityRegistry:
    schema_version: Literal["1.0"]
    capabilities: frozenset[str]

    def require(self, capability: str) -> str:
        if capability not in self.capabilities:
            raise UnknownCapability(capability)
        return capability


CAPABILITY_REGISTRY = CapabilityRegistry(
    "1.0",
    frozenset(
        {
            "source.observe.request",
            "source.snapshot_import.request",
            "document.parse.request",
            "version_candidate.detect.request",
            "maintenance.verify.request",
        }
    ),
)


@dataclass(frozen=True)
class ExecutionRoleRegistry:
    schema_version: Literal["1.0"]
    roles: frozenset[str]

    def require(self, role: str) -> str:
        if role not in self.roles:
            raise UnknownExecutionRole(role)
        return role


EXECUTION_ROLE_REGISTRY = ExecutionRoleRegistry(
    "1.0",
    frozenset(
        {
            "source_observer",
            "snapshot_importer",
            "document_parser",
            "candidate_detector",
            "reconciler",
            "verifier",
        }
    ),
)


@dataclass(frozen=True)
class PathScope:
    scope_type: Literal[
        "import_source", "snapshot_read", "workspace_staging", "monitoring_root"
    ]
    normalized_path_hash: str
    root_id: UUID
    access_mode: Literal["read", "list", "copy", "create_only"]
    recursive: bool

    def __post_init__(self) -> None:
        if self.scope_type not in {
            "import_source", "snapshot_read", "workspace_staging", "monitoring_root"
        }:
            raise ValueError("scope_type is not registered")
        if self.access_mode not in {"read", "list", "copy", "create_only"}:
            raise ValueError("access_mode is not registered")
        if len(self.normalized_path_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.normalized_path_hash
        ):
            raise ValueError("normalized_path_hash must be lowercase SHA-256")


@dataclass(frozen=True)
class PermissionContext:
    """Audit snapshot of a decision; never a reusable authorization token."""

    schema_version: Literal["1.0"]
    actor_type: Literal["user", "system"]
    actor_id: str | None
    workspace_id: UUID
    capabilities: tuple[str, ...]
    scope_refs: tuple[str, ...]
    path_scopes: tuple[PathScope, ...]
    network_allowed: Literal[False]
    granted_at: datetime
    policy_version: str
    authorization_decision_id: UUID

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("schema_version must be 1.0")
        if self.actor_type not in {"user", "system"}:
            raise ValueError("actor_type must be user or system")
        if self.network_allowed is not False:
            raise ValueError("network_allowed must be false")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "scope_refs", tuple(self.scope_refs))
        object.__setattr__(self, "path_scopes", tuple(self.path_scopes))
