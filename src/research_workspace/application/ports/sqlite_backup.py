"""Framework-free port for one verified SQLite recovery generation."""

from typing import Callable, Protocol

from research_workspace.application.dto.recovery_dto import (
    RecoveryPlan,
    RecoveryProgress,
    VerifiedRecoveryPoint,
)
from research_workspace.application.ports.operation_runner import CancellationToken


class SQLiteBackupPort(Protocol):
    def create_verified_recovery(
        self,
        plan: RecoveryPlan,
        generation: int,
        report_progress: Callable[[RecoveryProgress], None],
        cancellation: CancellationToken,
    ) -> VerifiedRecoveryPoint:
        """Create, validate, and physically promote one recovery generation."""
