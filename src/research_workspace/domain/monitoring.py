"""Closed Gate 2 monitoring vocabulary."""

from enum import StrEnum


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
