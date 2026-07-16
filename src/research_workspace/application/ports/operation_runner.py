"""Closed deterministic feature-runner protocol; no general Task surface."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, TypeAlias
from uuid import UUID

from research_workspace.application.dto.parsing_dto import ParseRequest
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


FeatureWorkPlan: TypeAlias = SnapshotImportWorkPlan | DocumentParseWorkPlan


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
