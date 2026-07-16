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
    "SOURCE_UNSTABLE": RetryPolicy(True, 3, (1.0, 5.0), True, "waiting_for_stability", "unstable_source"),
    "SQLITE_BUSY": RetryPolicy(True, 3, (0.05, 0.2), False, "waiting", "failed"),
    "PDF_PASSWORD_REQUIRED": RetryPolicy(False, 1, (), False, "needs_password", "failed"),
    "COMMAND_PERMISSION_DENIED": RetryPolicy(False, 1, (), False, "permission_denied", "failed"),
    "UNSUPPORTED_CONFIGURATION": RetryPolicy(False, 1, (), False, "unsupported", "failed"),
    "SOURCE_PATH_UNSAFE": RetryPolicy(False, 1, (), False, "unsafe_path", "failed"),
    "SOURCE_HASH_MISMATCH": RetryPolicy(False, 1, (), False, "integrity_error", "failed"),
    "PDF_CORRUPT": RetryPolicy(False, 1, (), False, "parse_failed", "failed"),
    "PDF_TRUNCATED": RetryPolicy(False, 1, (), False, "parse_failed", "failed"),
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
