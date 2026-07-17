"""Fail-closed Gate 1 retry policy registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


class UnknownErrorCode(ValueError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    retryable: bool
    maximum_attempts: int
    backoff_seconds: tuple[float, ...]
    requires_revalidation: bool
    user_visible_state: str
    terminal_state: str


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    next_delay_seconds: float | None
    requires_revalidation: bool
    user_visible_state: str
    terminal_state: str


@dataclass(frozen=True)
class RetryPolicyRegistry:
    schema_version: str
    policies: Mapping[str, RetryPolicy]


RETRY_POLICY_REGISTRY = RetryPolicyRegistry("1.0", MappingProxyType({
    "SOURCE_BUSY": RetryPolicy(True, 3, (0.25, 1.0), True, "waiting", "failed"),
    "SOURCE_UNSTABLE": RetryPolicy(True, 5, (2.0, 5.0, 15.0, 30.0), True, "waiting_for_stability", "unstable_source"),
    "MONITOR_ROOT_DISCONNECTED": RetryPolicy(
        True, 5, (2.0, 5.0, 15.0, 30.0), True, "disconnected", "failed"
    ),
    "SQLITE_BUSY": RetryPolicy(True, 3, (0.05, 0.2), False, "waiting", "failed"),
    "PDF_PASSWORD_REQUIRED": RetryPolicy(False, 1, (), False, "needs_password", "failed"),
    "COMMAND_PERMISSION_DENIED": RetryPolicy(False, 1, (), False, "permission_denied", "failed"),
    "UNSUPPORTED_CONFIGURATION": RetryPolicy(False, 1, (), False, "unsupported", "failed"),
    "SOURCE_PATH_UNSAFE": RetryPolicy(False, 1, (), False, "unsafe_path", "failed"),
    "SOURCE_HASH_MISMATCH": RetryPolicy(False, 1, (), False, "integrity_error", "failed"),
    "PDF_CORRUPT": RetryPolicy(False, 1, (), False, "parse_failed", "failed"),
    "PDF_TRUNCATED": RetryPolicy(False, 1, (), False, "parse_failed", "failed"),
    "COMMAND_IDEMPOTENCY_CONFLICT": RetryPolicy(False, 1, (), False, "command_conflict", "failed"),
    "COMMAND_VALIDATION_FAILED": RetryPolicy(False, 1, (), False, "validation_failed", "failed"),
    "CONCURRENT_MODIFICATION": RetryPolicy(False, 1, (), True, "concurrent_modification", "failed"),
    "RECOVERY_POINT_FAILED": RetryPolicy(False, 1, (), True, "recovery_failed", "failed"),
    "UNDO_NOT_AVAILABLE": RetryPolicy(False, 1, (), True, "undo_unavailable", "failed"),
    "UNDO_ALREADY_APPLIED": RetryPolicy(False, 1, (), True, "undo_unavailable", "failed"),
    "UNDO_CONFLICT": RetryPolicy(False, 1, (), True, "undo_conflict", "failed"),
    "UNDO_DEPENDENCY_CONFLICT": RetryPolicy(False, 1, (), True, "undo_conflict", "failed"),
    "UNDO_CONSTRAINT_VIOLATION": RetryPolicy(False, 1, (), True, "undo_conflict", "failed"),
    "DELETE_DEPENDENCY_CONFLICT": RetryPolicy(False, 1, (), True, "dependency_conflict", "failed"),
    "INVALID_WORKFLOW_TRANSITION": RetryPolicy(False, 1, (), True, "validation_failed", "failed"),
    "INVALID_VERSION_ASSIGNMENT": RetryPolicy(False, 1, (), True, "validation_failed", "failed"),
    "VERSION_RETRACTION_DEPENDENCY_CONFLICT": RetryPolicy(False, 1, (), True, "dependency_conflict", "failed"),
    "RELATION_DUPLICATE": RetryPolicy(False, 1, (), True, "relation_conflict", "failed"),
    "RELATION_CYCLE": RetryPolicy(False, 1, (), True, "relation_conflict", "failed"),
    "RELATION_ENDPOINT_INVALID": RetryPolicy(False, 1, (), True, "validation_failed", "failed"),
    "CANDIDATE_STATE_CHANGED": RetryPolicy(False, 1, (), True, "concurrent_modification", "failed"),
}))


def retry_decision(error_code: str, *, attempt: int) -> RetryDecision:
    try:
        policy = RETRY_POLICY_REGISTRY.policies[error_code]
    except KeyError as exc:
        raise UnknownErrorCode(error_code) from exc
    if attempt < 1:
        raise ValueError("attempt must be positive")
    retryable = policy.retryable and attempt < policy.maximum_attempts
    delay = policy.backoff_seconds[min(attempt - 1, len(policy.backoff_seconds) - 1)] if retryable else None
    return RetryDecision(
        retryable,
        delay,
        policy.requires_revalidation,
        policy.user_visible_state,
        policy.terminal_state,
    )
