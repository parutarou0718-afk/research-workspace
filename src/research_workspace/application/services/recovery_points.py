"""Application orchestration for pre-command recovery protection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from research_workspace.application.dto.recovery_dto import (
    RecoveryPlan,
    VerifiedRecoveryPoint,
)
from research_workspace.application.ports.sqlite_backup import SQLiteBackupPort
from research_workspace.application.ports.operation_runner import CancellationToken


class RecoveryCoordinator(Protocol):
    def next_recovery_generation(self) -> int: ...

    def activate_recovery_point(self, point: VerifiedRecoveryPoint) -> None: ...

    def reset_recovery_after_restore(self, workspace_id: UUID) -> None: ...


class RecoveryPointError(RuntimeError):
    def __init__(self, error_code: str = "RECOVERY_POINT_FAILED") -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class RestoreResetPlan:
    workspace_id: UUID
    physical_state: Literal["historical_unavailable_after_restore"]
    clear_slots: Literal[True]

    @classmethod
    def for_workspace(cls, workspace_id: UUID) -> "RestoreResetPlan":
        return cls(workspace_id, "historical_unavailable_after_restore", True)


class RecoveryPointService:
    def __init__(self, backup: SQLiteBackupPort, coordinator: RecoveryCoordinator) -> None:
        self._backup = backup
        self._coordinator = coordinator

    def create(
        self,
        plan: RecoveryPlan,
        *,
        cancellation: CancellationToken,
        report_progress=lambda progress: None,
    ) -> VerifiedRecoveryPoint:
        try:
            generation = self._coordinator.next_recovery_generation()
            point = self._backup.create_verified_recovery(
                plan, generation, report_progress, cancellation
            )
            self._coordinator.activate_recovery_point(point)
        except Exception as exc:
            if isinstance(exc, RecoveryPointError):
                raise
            raise RecoveryPointError() from exc
        return point

    def reset_after_restore(self, plan: RestoreResetPlan) -> None:
        self._coordinator.reset_recovery_after_restore(plan.workspace_id)
