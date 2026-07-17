"""Immutable worker messages and QtCore-only delivery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeAlias
from uuid import UUID

from PySide6.QtCore import QObject, Signal, Slot

from research_workspace.application.dto.parsing_dto import ParseResult
from research_workspace.application.dto.monitoring_dto import (
    CandidateDetectionResult,
    ReconciliationPage,
)
from research_workspace.infrastructure.filesystem.snapshots import MaterializedSnapshot
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint


@dataclass(frozen=True, slots=True)
class WorkerProgress:
    operation_id: UUID
    phase: str
    completed: int
    total: int


@dataclass(frozen=True, slots=True)
class SnapshotWorkerResult:
    operation_id: UUID
    import_item_id: UUID
    materialized: MaterializedSnapshot


@dataclass(frozen=True, slots=True)
class ParseWorkerResult:
    operation_id: UUID
    parse_result: ParseResult


@dataclass(frozen=True, slots=True)
class ReconciliationWorkerResult:
    operation_id: UUID
    reconciliation_run_id: UUID
    page: ReconciliationPage


@dataclass(frozen=True, slots=True)
class DetectedCandidate:
    candidate_id: UUID
    result: CandidateDetectionResult


@dataclass(frozen=True, slots=True)
class CandidateWorkerResult:
    operation_id: UUID
    candidates: tuple[DetectedCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))


@dataclass(frozen=True, slots=True)
class RecoveryWorkerResult:
    operation_id: UUID
    recovery_point: VerifiedRecoveryPoint


WorkerResult: TypeAlias = (
    SnapshotWorkerResult
    | ParseWorkerResult
    | ReconciliationWorkerResult
    | CandidateWorkerResult
    | RecoveryWorkerResult
)


@dataclass(frozen=True, slots=True)
class WorkerCompleted:
    operation_id: UUID
    result: WorkerResult


@dataclass(frozen=True, slots=True)
class WorkerFailed:
    operation_id: UUID
    error_code: str


@dataclass(frozen=True, slots=True)
class WorkerCancelled:
    operation_id: UUID


WorkerTerminal: TypeAlias = WorkerCompleted | WorkerFailed | WorkerCancelled


class WorkerSignals(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)
    cancelled = Signal(object)
    finished = Signal(object)


class CallbackRelay(QObject):
    def __init__(self, callback: Callable[[object], None]) -> None:
        super().__init__()
        self._callback = callback

    @Slot(object)
    def deliver(self, payload: object) -> None:
        self._callback(payload)
