"""Framework-free dispatcher for protected, idempotent application commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID, uuid4

import rfc8785

from research_workspace.application.dto.recovery_dto import RecoveryPlan
from research_workspace.application.ports.operation_runner import CancellationToken
from research_workspace.application.services.authorization import (
    AuthorizationRequest,
    RawActorEnvelope,
    authorize_request,
)


class CommandDispatchError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class RawCommandEnvelope:
    command_id: UUID
    command_type: str
    contract_version: Literal["1.0"]
    idempotency_key: str
    actor_type: str
    actor_id: str | None
    workspace_id: UUID
    requested_at: datetime
    request_payload: bytes

    def validate_outer_actor(self) -> None:
        if self.actor_type in {"agent", "task_executor"}:
            raise CommandDispatchError("ACTOR_NOT_ENABLED")
        if self.actor_type not in {"user", "system"}:
            raise CommandDispatchError("COMMAND_PERMISSION_DENIED")


@dataclass(frozen=True, slots=True)
class CommandPlan:
    command_id: UUID
    command_type: str
    idempotency_key: str
    request_fingerprint: str
    permission_context: bytes
    entity_scopes: tuple[tuple[str, UUID], ...]
    expected_versions: tuple[tuple[str, UUID, int], ...]
    canonical_request: bytes
    protected: bool


@dataclass(frozen=True, slots=True)
class DomainMutation:
    entity_type: str
    entity_id: UUID
    operation: str
    expected_row_version: int | None
    before_snapshot: bytes | None
    after_snapshot: bytes | None
    changed_fields: tuple[str, ...]
    event_type: str
    event_payload: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_fields", tuple(self.changed_fields))
        for value in (self.before_snapshot, self.after_snapshot, self.event_payload):
            if value is not None and not isinstance(value, bytes):
                raise TypeError("mutation JSON must be immutable bytes")


@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: UUID
    affected_entity_ids: tuple[UUID, ...]
    affected_count: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class ExistingCommand:
    command_id: UUID
    request_fingerprint: str
    status: str
    result: CommandResult | None


class ProtectedWriteCoordinator(Protocol):
    def find_command_by_idempotency(self, key: str) -> ExistingCommand | None: ...
    def persist_command_envelope(self, plan: CommandPlan) -> None: ...
    def persist_verified_recovery(self, plan: CommandPlan, recovery) -> None: ...
    def commit_mutations(
        self, plan: CommandPlan, mutations: tuple[DomainMutation, ...]
    ) -> CommandResult: ...
    def mark_command_failed(self, command_id: UUID, error_code: str) -> None: ...


def canonical_request_fingerprint(payload: bytes) -> str:
    try:
        value = json.loads(payload)
        canonical = rfc8785.dumps(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CommandDispatchError("COMMAND_VALIDATION_FAILED") from exc
    return hashlib.sha256(canonical).hexdigest()


def check_idempotency(existing: ExistingCommand, fingerprint: str) -> Literal["replay"]:
    if existing.request_fingerprint != fingerprint:
        raise CommandDispatchError("COMMAND_IDEMPOTENCY_CONFLICT")
    return "replay"


class CommandDispatcher:
    """Coordinates phases but owns no database, file, UI, or network handle."""

    def __init__(
        self,
        coordinator: ProtectedWriteCoordinator,
        recovery_service,
        *,
        database_path: Path,
        recovery_root: Path,
    ) -> None:
        self._coordinator = coordinator
        self._recovery_service = recovery_service
        self._database_path = database_path
        self._recovery_root = recovery_root

    def dispatch(
        self,
        envelope: RawCommandEnvelope,
        *,
        capability: str,
        entity_scopes: tuple[tuple[str, UUID], ...],
        expected_versions: tuple[tuple[str, UUID, int], ...],
        build_mutations: Callable[[CommandPlan], tuple[DomainMutation, ...]],
        cancellation: CancellationToken,
    ) -> CommandResult:
        envelope.validate_outer_actor()
        fingerprint = canonical_request_fingerprint(envelope.request_payload)
        existing = self._coordinator.find_command_by_idempotency(envelope.idempotency_key)
        if existing is not None:
            check_idempotency(existing, fingerprint)
            if existing.status == "committed" and existing.result is not None:
                return CommandResult(
                    existing.result.command_id,
                    existing.result.affected_entity_ids,
                    existing.result.affected_count,
                    True,
                )
            raise CommandDispatchError("COMMAND_VALIDATION_FAILED")
        try:
            context = authorize_request(
                AuthorizationRequest(
                    RawActorEnvelope(envelope.actor_type, envelope.actor_id),
                    envelope.workspace_id,
                    capability,
                    tuple(f"{kind}:{identity}" for kind, identity in entity_scopes),
                    (),
                    envelope.requested_at,
                    "1.0",
                    uuid4(),
                )
            )
            context_json = _permission_json(context)
            canonical_request = rfc8785.dumps(json.loads(envelope.request_payload))
            plan = CommandPlan(
                envelope.command_id,
                envelope.command_type,
                envelope.idempotency_key,
                fingerprint,
                context_json,
                tuple(entity_scopes),
                tuple(expected_versions),
                canonical_request,
                True,
            )
            self._coordinator.persist_command_envelope(plan)
            recovery = self._recovery_service.create(
                RecoveryPlan(
                    uuid4(),
                    plan.command_id,
                    plan.command_type,
                    plan.request_fingerprint,
                    envelope.workspace_id,
                    self._database_path,
                    self._recovery_root,
                    "0004_gate3_protected_crud",
                ),
                cancellation=cancellation,
            )
            return self._coordinator.commit_mutations(plan, build_mutations(plan))
        except Exception as exc:
            error_code = getattr(exc, "error_code", "COMMAND_VALIDATION_FAILED")
            persisted = self._coordinator.find_command_by_idempotency(
                envelope.idempotency_key
            )
            if (
                persisted is not None
                and persisted.request_fingerprint == fingerprint
                and persisted.status == "committed"
                and persisted.result is not None
            ):
                return persisted.result
            try:
                self._coordinator.mark_command_failed(envelope.command_id, error_code)
            except Exception:
                pass
            if isinstance(exc, CommandDispatchError):
                raise
            raise CommandDispatchError(error_code) from exc


def _permission_json(context) -> bytes:
    value = asdict(context)
    value["workspace_id"] = str(value["workspace_id"])
    value["authorization_decision_id"] = str(value["authorization_decision_id"])
    value["granted_at"] = value["granted_at"].isoformat().replace("+00:00", "Z")
    for scope in value["path_scopes"]:
        scope["root_id"] = str(scope["root_id"])
    return rfc8785.dumps(value)
