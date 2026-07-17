"""Immutable values crossing Gate 2 monitoring ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from research_workspace.domain.monitoring import (
    MonitoringRootStatus,
    PendingPathState,
    RawFileEventType,
    ReconciliationReason,
)
from research_workspace.domain.versioning import VersionRuleId


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class MonitoringRootPlan:
    monitoring_root_id: UUID
    root_path: Path
    recursive: bool
    watcher_generation: int
    config_fingerprint: str
    semantic_config_json: bytes

    def __post_init__(self) -> None:
        if self.recursive is not True:
            raise ValueError("v0.2 monitoring roots are recursive")
        if self.watcher_generation < 0:
            raise ValueError("watcher_generation must be nonnegative")
        _require_sha256(self.config_fingerprint, "config_fingerprint")
        if not isinstance(self.semantic_config_json, bytes):
            raise TypeError("semantic_config_json must be immutable bytes")


@dataclass(frozen=True, slots=True)
class RawFileEventDTO:
    event_id: UUID
    monitoring_root_id: UUID
    provider: str
    event_type: RawFileEventType
    source_path: Path | None
    destination_path: Path | None
    observed_at: datetime
    ingested_at: datetime
    raw_sequence_json: bytes | None
    correlation_hint: str | None
    deduplication_key: str

    def __post_init__(self) -> None:
        _require_sha256(self.deduplication_key, "deduplication_key")
        if self.raw_sequence_json is not None and not isinstance(self.raw_sequence_json, bytes):
            raise TypeError("raw_sequence_json must be immutable bytes")


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    operation_id: UUID
    reconciliation_run_id: UUID
    monitoring_root_id: UUID
    reason: ReconciliationReason
    root_path: Path
    checkpoint: bytes | None
    page_size: int

    def __post_init__(self) -> None:
        if self.page_size < 1 or self.page_size > 10_000:
            raise ValueError("page_size must be in the bounded range 1..10000")
        if self.checkpoint is not None and not isinstance(self.checkpoint, bytes):
            raise TypeError("checkpoint must be immutable bytes")


@dataclass(frozen=True, slots=True)
class ReconciliationObservation:
    normalized_path: str
    size_bytes: int | None
    modified_at: datetime | None
    file_id_hint: str | None
    volume_serial_hint: str | None

@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    source_path: Path
    normalized_path: str
    normalized_path_hash: str
    size_bytes: int
    modified_at: datetime
    file_id_hint: str | None
    volume_serial_hint: str | None

@dataclass(frozen=True, slots=True)
class ReconciliationPage:
    checkpoint: bytes | None
    items_seen: int
    suspected: tuple[ReconciliationFinding, ...]
    completed: bool
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.items_seen < 0 or self.items_seen > 10_000:
            raise ValueError("items_seen outside bounded page")
        if self.checkpoint is not None and not isinstance(self.checkpoint, bytes):
            raise TypeError("checkpoint must be immutable bytes")
        object.__setattr__(self, "suspected", tuple(self.suspected))


@dataclass(frozen=True, slots=True)
class CandidateDetectionResult:
    earlier_snapshot_id: UUID
    later_snapshot_id: UUID
    detector_id: str
    detector_version: str
    rule_id: VersionRuleId
    rule_config_fingerprint: str
    direction_rationale: bytes
    signals: bytes
    input_observation_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if self.earlier_snapshot_id == self.later_snapshot_id:
            raise ValueError("candidate snapshots must be distinct")
        if not self.detector_id.strip() or not self.detector_version.strip():
            raise ValueError("detector identity must be nonblank")
        _require_sha256(self.rule_config_fingerprint, "rule_config_fingerprint")
        if not isinstance(self.direction_rationale, bytes) or not isinstance(self.signals, bytes):
            raise TypeError("candidate evidence must be immutable bytes")
        observation_ids = tuple(self.input_observation_ids)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("input_observation_ids must be unique")
        object.__setattr__(self, "input_observation_ids", observation_ids)


@dataclass(frozen=True, slots=True)
class MonitoringRootRecord:
    monitoring_root_id: UUID
    original_path: Path
    normalized_path: str
    normalized_path_hash: str
    status: MonitoringRootStatus
    config_fingerprint: str
    watcher_generation: int
    created_at: datetime
    updated_at: datetime
    removed_at: datetime | None


@dataclass(frozen=True, slots=True)
class MonitoringRootSeed:
    monitoring_root_id: UUID
    original_path: Path
    normalized_path: str
    normalized_path_hash: str
    semantic_config_json: bytes
    config_fingerprint: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BaselineObservationDTO:
    observation_id: UUID
    original_path: Path
    normalized_path: str
    normalized_path_hash: str
    original_filename: str
    entry_type: str
    size_bytes: int | None
    modified_at: datetime | None
    file_id_hint: str | None
    volume_serial_hint: str | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class PendingPathCheckDTO:
    pending_path_check_id: UUID
    monitoring_root_id: UUID
    source_path: Path
    state: PendingPathState
    stability_attempt_count: int
    next_check_at: datetime | None
    last_failure_code: str | None
    source_observation_id: UUID | None
    row_version: int
