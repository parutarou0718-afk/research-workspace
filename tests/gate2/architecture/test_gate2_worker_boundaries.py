from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path
from uuid import uuid4

import pytest

from research_workspace.application.dto.monitoring_dto import (
    ReconciliationPage,
    ReconciliationPlan,
)
from research_workspace.application.ports.operation_runner import (
    CandidateDetectionJob,
    CandidateDetectionWorkPlan,
    ReconciliationWorkPlan,
)
from research_workspace.application.services.candidate_detection import (
    CandidateInput,
    PaperMembership,
)
from research_workspace.domain.monitoring import ReconciliationReason
from research_workspace.infrastructure.workers import operation_worker
from research_workspace.infrastructure.workers.operation_worker import OperationWorker
from research_workspace.infrastructure.workers.worker_signals import (
    CandidateWorkerResult,
    ReconciliationWorkerResult,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _candidate_input() -> CandidateInput:
    first, second = uuid4(), uuid4()
    return CandidateInput(
        first,
        second,
        "a" * 64,
        "b" * 64,
        "application/pdf",
        "application/pdf",
        (uuid4(),),
        NOW,
        NOW.replace(second=1),
        NOW,
        NOW,
        "paper-v1.pdf",
        "paper-v2.pdf",
        "Paper",
        "Paper",
        None,
        None,
        False,
        False,
        None,
        None,
        ((first, second),),
        (),
        True,
    )


def test_gate2_worker_has_no_persistence_widget_network_or_event_authority() -> None:
    source = inspect.getsource(operation_worker).lower()
    for forbidden in (
        "sqlalchemy",
        "session",
        "repository",
        "qwidget",
        "qtwidgets",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "domainevent",
        "writecoordinator",
        "taskexecutor",
        "lease",
        "agentruntime",
    ):
        assert forbidden not in source
    assert set(inspect.signature(OperationWorker).parameters) == {
        "snapshot_port",
        "parsers",
    }


def test_gate2_plans_and_results_are_deeply_immutable(tmp_path: Path) -> None:
    operation_id = uuid4()
    reconciliation = ReconciliationWorkPlan(
        operation_id,
        ReconciliationPlan(
            operation_id,
            uuid4(),
            uuid4(),
            ReconciliationReason.USER_VERIFY,
            tmp_path,
            None,
            10,
        ),
        (),
    )
    value = _candidate_input()
    candidate = CandidateDetectionWorkPlan(
        uuid4(),
        (
            CandidateDetectionJob(
                uuid4(),
                value,
                (
                    PaperMembership(value.snapshot_a_id, uuid4(), 1),
                    PaperMembership(value.snapshot_b_id, uuid4(), 2),
                ),
            ),
        ),
    )
    results = (
        ReconciliationWorkerResult(
            reconciliation.operation_id,
            reconciliation.plan.reconciliation_run_id,
            ReconciliationPage(None, 0, (), True),
        ),
        CandidateWorkerResult(candidate.operation_id, ()),
    )

    for item in (reconciliation, candidate, *results):
        with pytest.raises((FrozenInstanceError, AttributeError)):
            item.operation_id = uuid4()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        candidate.jobs[0].memberships += ()


def test_candidate_work_plan_is_closed_at_twelve_jobs() -> None:
    value = _candidate_input()
    jobs = tuple(
        CandidateDetectionJob(uuid4(), value, ())
        for _ in range(13)
    )

    with pytest.raises(ValueError, match="CANDIDATE_COMPARISON_LIMIT_EXCEEDED"):
        CandidateDetectionWorkPlan(uuid4(), jobs)
