"""Pure future-compatible task, retry, effect, and permission policies."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import TypeAlias

import rfc8785


TaskContract: TypeAlias = Mapping[str, object]
TaskResult: TypeAlias = Mapping[str, object]


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_CONFIRMATION = "needs_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptStatus(str, Enum):
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_CONFIRMATION = "needs_confirmation"


class FileEffectRecoveryAction(str, Enum):
    RETURN_COMMITTED = "RETURN_COMMITTED"
    COMMIT_FINAL = "COMMIT_FINAL"
    PROMOTE_STAGING = "PROMOTE_STAGING"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"


class Capability(str, Enum):
    DOCUMENT_PARSER = "document_parser"
    KNOWLEDGE = "knowledge"
    CONTEXT_RECOVERY = "context_recovery"
    SUBMISSION = "submission"
    EXPORT = "export"
    GRANT = "grant"


@dataclass(frozen=True)
class AttemptDecision:
    task_status: TaskStatus
    attempt_status: AttemptStatus
    retry_at: datetime | None
    error_code: str | None = None
    error_details: Mapping[str, object] | None = None
    retryable: bool = False
    retries_exhausted: bool = False


@dataclass(frozen=True)
class FileEffectRecoveryDecision:
    action: FileEffectRecoveryAction
    retryable: bool


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str


_TRANSPORT_FIELDS = frozenset(
    {"task_id", "created_at", "correlation_id", "idempotency_key"}
)


def task_request_fingerprint(task: TaskContract) -> str:
    """Hash the semantic task request using RFC 8785 canonical bytes."""

    semantic = {key: value for key, value in task.items() if key not in _TRANSPORT_FIELDS}
    input_refs = semantic.get("input_refs")
    if isinstance(input_refs, list):
        semantic["input_refs"] = sorted(
            input_refs,
            key=lambda ref: (ref["ref_type"], ref["ref_id"]),
        )
    return hashlib.sha256(rfc8785.dumps(semantic)).hexdigest()


def task_effect_operation_key(
    *,
    task_id: str,
    executor_id: str,
    effect_type: str,
    output_type: str,
    output_identity: str,
) -> str:
    """Return the stable identity of one future side-effect operation."""

    identity = {
        "task_id": task_id,
        "executor_id": executor_id,
        "effect_type": effect_type,
        "output_type": output_type,
        "output_identity": output_identity,
    }
    return hashlib.sha256(rfc8785.dumps(identity)).hexdigest()


def eligible_for_lease(
    *,
    status: TaskStatus,
    next_attempt_at: datetime | None,
    attempt_count: int,
    max_attempts: int,
    now: datetime,
) -> bool:
    """Evaluate the acquisition predicate without acquiring a lease."""

    if not _attempt_counts_valid(attempt_count, max_attempts, allow_zero=True):
        return False
    return (
        status is TaskStatus.PENDING
        and (next_attempt_at is None or next_attempt_at <= now)
        and attempt_count < max_attempts
    )


def expired_lease_decision(
    *, attempt_count: int, max_attempts: int, now: datetime | None = None
) -> AttemptDecision:
    """Decide the separate expired-running cleanup transition."""

    _validate_attempts(attempt_count, max_attempts, allow_zero=False)
    if attempt_count < max_attempts:
        if now is None:
            raise ValueError("now is required when scheduling an expired lease retry")
        return AttemptDecision(
            task_status=TaskStatus.PENDING,
            attempt_status=AttemptStatus.RETRY_SCHEDULED,
            retry_at=now,
            error_code="EXECUTOR_LEASE_EXPIRED",
            error_details=MappingProxyType({}),
            retryable=True,
        )
    return AttemptDecision(
        task_status=TaskStatus.FAILED,
        attempt_status=AttemptStatus.FAILED,
        retry_at=None,
        error_code="TASK_LEASE_EXHAUSTED",
        error_details=MappingProxyType({}),
        retryable=False,
        retries_exhausted=True,
    )


def decide_attempt_outcome(
    *,
    attempt: int,
    max_attempts: int,
    retryable: bool,
    now: datetime | None = None,
    jitter_fraction: float = 0.0,
    error_code: str | None = None,
    error_details: Mapping[str, object] | None = None,
) -> AttemptDecision:
    """Decide whether an execution error is retried or terminalized."""

    _validate_attempts(attempt, max_attempts, allow_zero=False)
    if not 0.0 <= jitter_fraction <= 0.2:
        raise ValueError("jitter_fraction must be between 0.0 and 0.2")

    if retryable and attempt < max_attempts:
        if now is None:
            raise ValueError("now is required when scheduling a retry")
        base_seconds = 5 if attempt == 1 else 30 if attempt == 2 else 300
        retry_at = now + timedelta(seconds=base_seconds * (1 + jitter_fraction))
        return AttemptDecision(
            task_status=TaskStatus.PENDING,
            attempt_status=AttemptStatus.RETRY_SCHEDULED,
            retry_at=retry_at,
            error_code=error_code,
            error_details=_immutable_error_details(error_details),
            retryable=True,
        )

    return AttemptDecision(
        task_status=TaskStatus.FAILED,
        attempt_status=AttemptStatus.FAILED,
        retry_at=None,
        error_code=error_code,
        error_details=_immutable_error_details(
            error_details, retries_exhausted=retryable and attempt >= max_attempts
        ),
        retryable=False,
        retries_exhausted=retryable and attempt >= max_attempts,
    )


def decide_file_effect_recovery(
    *,
    committed: bool,
    staging_exists: bool,
    staging_sha256: str | None,
    final_exists: bool,
    final_sha256: str | None,
    expected_sha256: str,
) -> FileEffectRecoveryDecision:
    """Select a recovery action from already-observed file state."""

    if committed:
        return FileEffectRecoveryDecision(
            FileEffectRecoveryAction.RETURN_COMMITTED, retryable=False
        )
    if final_exists and final_sha256 == expected_sha256:
        return FileEffectRecoveryDecision(
            FileEffectRecoveryAction.COMMIT_FINAL, retryable=False
        )
    if staging_exists and staging_sha256 == expected_sha256:
        return FileEffectRecoveryDecision(
            FileEffectRecoveryAction.PROMOTE_STAGING, retryable=False
        )
    return FileEffectRecoveryDecision(
        FileEffectRecoveryAction.RETRYABLE_ERROR, retryable=True
    )


_ALLOWED_ACTIONS: Mapping[Capability, frozenset[str]] = {
    Capability.DOCUMENT_PARSER: frozenset(
        {"source.read_declared", "derived.write_selected_data_directory"}
    ),
    Capability.KNOWLEDGE: frozenset(
        {"idea_candidate.create", "relation_candidate.create"}
    ),
    Capability.CONTEXT_RECOVERY: frozenset(
        {
            "aggregate.read_approved",
            "candidate_snapshot.write",
            "evidence.write",
        }
    ),
    Capability.SUBMISSION: frozenset(
        {"status_transition.propose", "status_transition.apply"}
    ),
    Capability.EXPORT: frozenset(
        {"entities.read_selected", "export.write_user_approved_target"}
    ),
    Capability.GRANT: frozenset({"recommendation.create"}),
}

_PERSISTENT_OR_EXTERNAL_WRITE_ACTIONS = frozenset(
    {
        "derived.write_selected_data_directory",
        "idea_candidate.create",
        "relation_candidate.create",
        "candidate_snapshot.write",
        "evidence.write",
        "status_transition.apply",
        "export.write_user_approved_target",
    }
)


def permission_for(
    capability: Capability,
    action: str,
    *,
    dry_run: bool = False,
    source_declared: bool = False,
    selected_data_directory: bool = False,
    aggregate_approved: bool = False,
    entities_selected: bool = False,
    export_target_approved: bool = False,
    user_requested: bool = False,
    audited: bool = False,
    local_only: bool = True,
    provider_selected: bool = False,
    user_consented: bool = False,
    data_range_disclosed: bool = False,
) -> PermissionDecision:
    """Evaluate the closed capability matrix and explicit consent gates."""

    if action == "network.access":
        allowed = (
            not local_only
            and provider_selected
            and user_consented
            and data_range_disclosed
        )
        return PermissionDecision(
            allowed,
            "network consent gates satisfied" if allowed else "network access denied",
        )

    if dry_run and action in _PERSISTENT_OR_EXTERNAL_WRITE_ACTIONS:
        return PermissionDecision(False, "dry run forbids persistent or external writes")

    if action not in _ALLOWED_ACTIONS.get(capability, frozenset()):
        return PermissionDecision(False, "action is outside the capability")

    scope_satisfied = {
        "source.read_declared": source_declared,
        "derived.write_selected_data_directory": selected_data_directory,
        "aggregate.read_approved": aggregate_approved,
        "candidate_snapshot.write": aggregate_approved,
        "evidence.write": aggregate_approved,
        "entities.read_selected": entities_selected,
        "export.write_user_approved_target": export_target_approved,
    }.get(action, True)
    if not scope_satisfied:
        return PermissionDecision(False, "resource is outside the approved scope")

    if capability is Capability.SUBMISSION and not (user_requested and audited):
        return PermissionDecision(
            False, "submission transitions require a user request and audit"
        )

    if not local_only and not (
        provider_selected and user_consented and data_range_disclosed
    ):
        return PermissionDecision(False, "network access denied")

    return PermissionDecision(True, "allowed by scoped capability")


def _validate_attempts(attempt: int, max_attempts: int, *, allow_zero: bool) -> None:
    if not _attempt_counts_valid(attempt, max_attempts, allow_zero=allow_zero):
        raise ValueError("attempt counts are outside the approved range")


def _attempt_counts_valid(attempt: int, max_attempts: int, *, allow_zero: bool) -> bool:
    if type(attempt) is not int or type(max_attempts) is not int:
        return False
    minimum = 0 if allow_zero else 1
    return 1 <= max_attempts <= 10 and minimum <= attempt <= max_attempts


def _immutable_error_details(
    details: Mapping[str, object] | None, *, retries_exhausted: bool = False
) -> Mapping[str, object]:
    copied = dict(details or {})
    if retries_exhausted:
        copied["retries_exhausted"] = True
    frozen = _freeze_json(copied)
    assert isinstance(frozen, Mapping)
    return frozen


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value
