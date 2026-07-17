"""One-plan deterministic execution with cooperative cancellation."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
import threading
import time
from typing import Callable

from PySide6.QtCore import QCoreApplication, QTimer, Qt

from research_workspace.application.ports.document_parser import DocumentParser
from research_workspace.application.ports.operation_runner import (
    CandidateDetectionWorkPlan,
    DocumentParseWorkPlan,
    FeatureWorkPlan,
    ReconciliationWorkPlan,
    SnapshotImportWorkPlan,
)
from research_workspace.application.services.candidate_detection import (
    PaperMembership,
    detect_candidate,
)
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore
from research_workspace.infrastructure.monitoring.reconciliation import BoundedReconciler
from research_workspace.infrastructure.workers.worker_signals import (
    CallbackRelay,
    CandidateWorkerResult,
    DetectedCandidate,
    ParseWorkerResult,
    ReconciliationWorkerResult,
    SnapshotWorkerResult,
    WorkerCancelled,
    WorkerCompleted,
    WorkerFailed,
    WorkerProgress,
    WorkerSignals,
    WorkerTerminal,
)


class _PlanMemberships:
    def __init__(self, values: tuple[PaperMembership, ...]) -> None:
        self._values = values

    def active_memberships(self, snapshot_id):
        return tuple(
            value for value in self._values if value.snapshot_id == snapshot_id
        )


class CancellationFlag:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


class OperationWorker:
    def __init__(
        self,
        snapshot_port: SnapshotStore,
        parsers: Mapping[str, DocumentParser],
    ) -> None:
        self._snapshot_port = snapshot_port
        self._parsers = MappingProxyType(dict(parsers))

    def run(
        self,
        plan: FeatureWorkPlan,
        cancellation: CancellationFlag,
        emit_progress: Callable[[WorkerProgress], None],
    ) -> WorkerTerminal:
        if cancellation.cancelled:
            return WorkerCancelled(plan.operation_id)
        emit_progress(WorkerProgress(plan.operation_id, "started", 0, 1))
        try:
            if isinstance(plan, SnapshotImportWorkPlan):
                materialized = self._snapshot_port.materialize(
                    plan.source_path, plan.import_item_id
                )
                result = SnapshotWorkerResult(
                    plan.operation_id, plan.import_item_id, materialized
                )
            elif isinstance(plan, DocumentParseWorkPlan):
                parser = self._parsers.get(plan.parser_id)
                if (
                    parser is None
                    or parser.parser_id != plan.parser_id
                    or plan.request.mime_type not in parser.supported_mime_types
                ):
                    return WorkerFailed(plan.operation_id, "COMMAND_VALIDATION_FAILED")
                result = ParseWorkerResult(
                    plan.operation_id, parser.parse(plan.request)
                )
            elif isinstance(plan, ReconciliationWorkPlan):
                page = BoundedReconciler().scan_page(
                    plan.plan,
                    plan.known,
                    cancel_requested=lambda: cancellation.cancelled,
                )
                if page.cancelled or cancellation.cancelled:
                    return WorkerCancelled(plan.operation_id)
                result = ReconciliationWorkerResult(
                    plan.operation_id,
                    plan.plan.reconciliation_run_id,
                    page,
                )
            elif isinstance(plan, CandidateDetectionWorkPlan):
                detected = []
                total = len(plan.jobs)
                for index, job in enumerate(plan.jobs):
                    if cancellation.cancelled:
                        return WorkerCancelled(plan.operation_id)
                    candidate = detect_candidate(
                        job.value, _PlanMemberships(job.memberships)
                    )
                    if candidate is not None:
                        detected.append(DetectedCandidate(job.candidate_id, candidate))
                    emit_progress(
                        WorkerProgress(plan.operation_id, "detecting", index + 1, total)
                    )
                result = CandidateWorkerResult(plan.operation_id, tuple(detected))
            else:  # pragma: no cover - closed plan union
                return WorkerFailed(plan.operation_id, "COMMAND_VALIDATION_FAILED")
        except SourceFailure as failure:
            return WorkerFailed(plan.operation_id, failure.error_code)
        except Exception:
            return WorkerFailed(plan.operation_id, "COMMAND_VALIDATION_FAILED")
        if cancellation.cancelled:
            return WorkerCancelled(plan.operation_id)
        emit_progress(WorkerProgress(plan.operation_id, "finished", 1, 1))
        return WorkerCompleted(plan.operation_id, result)


class ThreadedOperationHandle:
    def __init__(self, worker: OperationWorker, plan: FeatureWorkPlan) -> None:
        self._worker = worker
        self._plan = plan
        self._cancellation = CancellationFlag()
        self._signals = WorkerSignals()
        self._relays: list[CallbackRelay] = []
        self._thread: threading.Thread | None = None
        self._terminal: WorkerTerminal | None = None
        self._lock = threading.Lock()
        self.completed_count = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._execute,
                name=f"gate1-operation-{self._plan.operation_id}",
                daemon=False,
            )
            self._thread.start()

    def _execute(self) -> None:
        terminal = self._worker.run(
            self._plan, self._cancellation, self._signals.progress.emit
        )
        with self._lock:
            self._terminal = terminal
            if isinstance(terminal, WorkerCompleted):
                self.completed_count += 1
        if isinstance(terminal, WorkerCompleted):
            self._signals.completed.emit(terminal)
        elif isinstance(terminal, WorkerFailed):
            self._signals.failed.emit(terminal)
        else:
            self._signals.cancelled.emit(terminal)
        self._signals.finished.emit(terminal)

    def _connect(self, signal, callback: Callable[[object], None]) -> None:
        relay = CallbackRelay(callback)
        self._relays.append(relay)
        signal.connect(relay.deliver, Qt.ConnectionType.QueuedConnection)

    def on_progress(self, callback: Callable[[object], None]) -> None:
        self._connect(self._signals.progress, callback)

    def on_completed(self, callback: Callable[[object], None]) -> None:
        self._connect(self._signals.completed, callback)

    def on_failed(self, callback: Callable[[object], None]) -> None:
        self._connect(self._signals.failed, callback)

    def on_cancelled(self, callback: Callable[[object], None]) -> None:
        self._connect(self._signals.cancelled, callback)

    def on_finished(self, callback: Callable[[object], None]) -> None:
        self._connect(self._signals.finished, callback)

    def cancel(self) -> None:
        self._cancellation.cancel()

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def shutdown(self, timeout: float | None = None) -> bool:
        self.cancel()
        return self.join(timeout)


class ThreadedOperationRunner:
    def __init__(self, worker: OperationWorker) -> None:
        self._worker = worker
        self._handles: list[ThreadedOperationHandle] = []

    def start(self, plan: FeatureWorkPlan) -> ThreadedOperationHandle:
        handle = ThreadedOperationHandle(self._worker, plan)
        self._handles.append(handle)
        if QCoreApplication.instance() is None:
            handle.start()
        else:
            QTimer.singleShot(0, handle.start)
        return handle

    def shutdown(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        complete = True
        for handle in tuple(self._handles):
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            complete = handle.shutdown(remaining) and complete
        return complete
