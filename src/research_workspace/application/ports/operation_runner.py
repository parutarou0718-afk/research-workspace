"""Closed deterministic feature-runner protocol; no general Task surface."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, TypeAlias
from uuid import UUID

from research_workspace.application.dto.parsing_dto import ParseRequest
from research_workspace.application.dto.monitoring_dto import (
    ReconciliationObservation,
    ReconciliationPlan,
)
from research_workspace.application.services.candidate_detection import (
    CandidateInput,
    PaperMembership,
)
from research_workspace.domain.operations import OperationOutcome, OperationWorkPlan


class CancellationToken(Protocol):
    @property
    def cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class SnapshotImportWorkPlan:
    operation_id: UUID
    import_item_id: UUID
    source_path: Path


@dataclass(frozen=True, slots=True)
class DocumentParseWorkPlan:
    operation_id: UUID
    parser_id: str
    request: ParseRequest


@dataclass(frozen=True, slots=True)
class ReconciliationWorkPlan:
    operation_id: UUID
    plan: ReconciliationPlan
    known: tuple[ReconciliationObservation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "known", tuple(self.known))
        if self.operation_id != self.plan.operation_id:
            raise ValueError("COMMAND_VALIDATION_FAILED")


@dataclass(frozen=True, slots=True)
class CandidateDetectionJob:
    candidate_id: UUID
    value: CandidateInput
    memberships: tuple[PaperMembership, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "memberships", tuple(self.memberships))


@dataclass(frozen=True, slots=True)
class CandidateDetectionWorkPlan:
    operation_id: UUID
    jobs: tuple[CandidateDetectionJob, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "jobs", tuple(self.jobs))
        if len(self.jobs) > 12:
            raise ValueError("CANDIDATE_COMPARISON_LIMIT_EXCEEDED")
        if len({job.candidate_id for job in self.jobs}) != len(self.jobs):
            raise ValueError("COMMAND_VALIDATION_FAILED")


FeatureWorkPlan: TypeAlias = (
    SnapshotImportWorkPlan
    | DocumentParseWorkPlan
    | ReconciliationWorkPlan
    | CandidateDetectionWorkPlan
)


class OperationHandle(Protocol):
    def on_progress(self, callback: Callable[[object], None]) -> None: ...
    def on_completed(self, callback: Callable[[object], None]) -> None: ...
    def on_failed(self, callback: Callable[[object], None]) -> None: ...
    def on_cancelled(self, callback: Callable[[object], None]) -> None: ...
    def cancel(self) -> None: ...
    def join(self, timeout: float | None = None) -> bool: ...
    def shutdown(self, timeout: float | None = None) -> bool: ...


class OperationRunner(Protocol):
    def run(self, plan: OperationWorkPlan, cancellation: CancellationToken) -> OperationOutcome: ...

    def start(self, plan: FeatureWorkPlan) -> OperationHandle: ...
