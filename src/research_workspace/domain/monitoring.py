"""Closed Gate 2 monitoring vocabulary and semantic configuration."""

from dataclasses import dataclass
from enum import StrEnum
import hashlib

import rfc8785


class MonitoringRootStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    OVERFLOW_RECONCILING = "overflow_reconciling"
    ERROR = "error"


class PendingPathState(StrEnum):
    DETECTED = "detected"
    DEBOUNCING = "debouncing"
    WAITING_FOR_STABILITY = "waiting_for_stability"
    IMPORTING = "importing"
    IMPORTED = "imported"
    DUPLICATE_CONTENT = "duplicate_content"
    SAFE_FAILURE = "safe_failure"
    UNSTABLE_SOURCE = "unstable_source"


class RawFileEventType(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    MOVED = "moved"
    DELETED = "deleted"
    OVERFLOW = "overflow"
    ROOT_STATE = "root_state"


class ReconciliationReason(StrEnum):
    BASELINE = "baseline"
    DISCONNECT = "disconnect"
    OVERFLOW = "overflow"
    UNCLEAN_SHUTDOWN = "unclean_shutdown"
    USER_VERIFY = "user_verify"


class ReconciliationStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MonitoringConfiguration:
    quiet_window_seconds: int = 2
    stable_observations: int = 2
    max_stability_attempts: int = 5
    backoff_seconds: tuple[int, ...] = (2, 5, 15, 30, 60)
    allowed_extensions: tuple[str, ...] = (".docx", ".pdf", ".pptx")
    excluded_names: tuple[str, ...] = ()
    candidate_window: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_extensions",
            tuple(sorted({extension.casefold() for extension in self.allowed_extensions})),
        )
        object.__setattr__(
            self,
            "excluded_names",
            tuple(sorted({name.casefold() for name in self.excluded_names})),
        )
        object.__setattr__(self, "backoff_seconds", tuple(self.backoff_seconds))
        if (
            self.quiet_window_seconds < 0
            or self.stable_observations < 2
            or self.max_stability_attempts < 1
            or len(self.backoff_seconds) != self.max_stability_attempts
            or any(delay < 0 for delay in self.backoff_seconds)
            or self.candidate_window < 1
        ):
            raise ValueError("invalid semantic monitoring configuration")
        if any(not extension.startswith(".") for extension in self.allowed_extensions):
            raise ValueError("allowed extensions must include a leading dot")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "quiet_window_seconds": self.quiet_window_seconds,
            "stable_observations": self.stable_observations,
            "max_stability_attempts": self.max_stability_attempts,
            "backoff_seconds": list(self.backoff_seconds),
            "allowed_extensions": list(self.allowed_extensions),
            "excluded_names": list(self.excluded_names),
            "candidate_window": self.candidate_window,
        }

    def canonical_json(self) -> bytes:
        return rfc8785.dumps(self.semantic_payload())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json()).hexdigest()


DEFAULT_MONITORING_CONFIG = MonitoringConfiguration()
