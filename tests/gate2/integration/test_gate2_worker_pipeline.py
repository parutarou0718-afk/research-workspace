from datetime import datetime, timezone
from pathlib import Path
import threading
from uuid import uuid4

from research_workspace.application.dto.monitoring_dto import ReconciliationPlan
from research_workspace.application.ports.operation_runner import (
    CandidateDetectionJob,
    CandidateDetectionWorkPlan,
    ReconciliationWorkPlan,
)
from research_workspace.application.services.candidate_detection import CandidateInput
from research_workspace.application.services.operation_dispatcher import (
    Gate2OperationPipeline,
)
from research_workspace.domain.monitoring import ReconciliationReason
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore
from research_workspace.infrastructure.monitoring.reconciliation import BoundedReconciler
from research_workspace.infrastructure.workers.operation_worker import (
    OperationWorker,
    ThreadedOperationRunner,
)
from research_workspace.infrastructure.workers import operation_worker


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


class RecordingCoordinator:
    def __init__(self) -> None:
        self.pages = []
        self.candidates = []
        self.thread_ids = []

    def record_reconciliation_page(self, run_id, page, now) -> None:
        self.thread_ids.append(threading.get_ident())
        self.pages.append((run_id, page, now))

    def register_version_candidate(self, candidate_id, operation_id, value, now):
        self.thread_ids.append(threading.get_ident())
        self.candidates.append((candidate_id, operation_id, value, now))
        return candidate_id


def _candidate_job() -> CandidateDetectionJob:
    first, second = uuid4(), uuid4()
    return CandidateDetectionJob(
        uuid4(),
        CandidateInput(
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
            "draft.pdf",
            "final.pdf",
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
        ),
        (),
    )


def _runtime(tmp_path: Path):
    coordinator = RecordingCoordinator()
    runner = ThreadedOperationRunner(
        OperationWorker(SnapshotStore(tmp_path / "workspace"), {})
    )
    return Gate2OperationPipeline(coordinator, runner), coordinator, runner


def test_reconciliation_computes_off_thread_and_persists_on_main_thread(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "external"
    root.mkdir()
    (root / "paper.pdf").write_bytes(b"content")
    worker_threads = []
    original = BoundedReconciler.scan_page

    def recording_scan(self, *args, **kwargs):
        worker_threads.append(threading.get_ident())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BoundedReconciler, "scan_page", recording_scan)
    plan = ReconciliationPlan(
        uuid4(),
        uuid4(),
        uuid4(),
        ReconciliationReason.USER_VERIFY,
        root,
        None,
        10,
    )
    pipeline, coordinator, runner = _runtime(tmp_path)
    main_thread = threading.get_ident()

    handle = pipeline.start_reconciliation(
        ReconciliationWorkPlan(plan.operation_id, plan, ()), NOW
    )
    qtbot.waitUntil(lambda: handle.done, timeout=5000)

    assert handle.status == "completed"
    assert worker_threads and worker_threads[0] != main_thread
    assert coordinator.thread_ids == [main_thread]
    assert coordinator.pages[0][0] == plan.reconciliation_run_id
    assert coordinator.pages[0][1].completed is True
    assert runner.shutdown(timeout=1)


def test_candidate_results_are_validated_then_persisted_on_main_thread(
    qtbot, tmp_path: Path
) -> None:
    pipeline, coordinator, runner = _runtime(tmp_path)
    job = _candidate_job()
    plan = CandidateDetectionWorkPlan(uuid4(), (job,))
    main_thread = threading.get_ident()

    handle = pipeline.start_candidate_detection(plan, NOW)
    qtbot.waitUntil(lambda: handle.done, timeout=5000)

    assert handle.status == "completed"
    assert coordinator.thread_ids == [main_thread]
    assert coordinator.candidates[0][0] == job.candidate_id
    assert coordinator.candidates[0][2].earlier_snapshot_id == (
        job.value.snapshot_a_id
    )
    assert runner.shutdown(timeout=1)


def test_cancelled_gate2_operation_never_persists_or_reports_completed(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    started, release = threading.Event(), threading.Event()

    def blocked_detect(*_args, **_kwargs):
        started.set()
        release.wait(timeout=5)
        return None

    monkeypatch.setattr(operation_worker, "detect_candidate", blocked_detect)
    pipeline, coordinator, runner = _runtime(tmp_path)
    handle = pipeline.start_candidate_detection(
        CandidateDetectionWorkPlan(uuid4(), (_candidate_job(),)), NOW
    )
    qtbot.waitUntil(started.is_set, timeout=5000)
    handle.cancel()
    release.set()
    qtbot.waitUntil(lambda: handle.done, timeout=5000)

    assert handle.status == "cancelled"
    assert handle.completed_count == 0
    assert coordinator.candidates == []
    assert runner.shutdown(timeout=1)
