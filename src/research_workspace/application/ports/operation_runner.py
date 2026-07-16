"""Closed deterministic operation-runner protocol; no Task execution surface."""

from typing import Protocol

from research_workspace.domain.operations import OperationOutcome, OperationWorkPlan


class CancellationToken(Protocol):
    @property
    def cancelled(self) -> bool: ...


class OperationRunner(Protocol):
    def run(self, plan: OperationWorkPlan, cancellation: CancellationToken) -> OperationOutcome: ...
