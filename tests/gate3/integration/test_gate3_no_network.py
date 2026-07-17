from pathlib import Path
from uuid import uuid4

from research_workspace.application.dto.recovery_dto import RecoveryPlan
from research_workspace.application.services.recovery_points import RecoveryWorkPlan
from research_workspace.infrastructure.workers.operation_worker import (
    CancellationFlag,
    OperationWorker,
)


class _OfflineRecovery:
    def create_verified_recovery(self, plan, generation, report, cancellation):
        raise RuntimeError("offline fixture")


def test_gate3_recovery_worker_has_no_network_fallback() -> None:
    worker = OperationWorker.with_recovery(object(), {}, _OfflineRecovery())
    plan = RecoveryPlan(
        uuid4(), uuid4(), "paper.update", "a" * 64, uuid4(),
        Path("workspace.db"), Path("recovery"),
        "0004_gate3_protected_crud",
    )
    result = worker.run(
        RecoveryWorkPlan(uuid4(), plan, 1), CancellationFlag(), lambda _: None
    )
    assert result.error_code == "COMMAND_VALIDATION_FAILED"
