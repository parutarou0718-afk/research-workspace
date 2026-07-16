from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from research_workspace.application.dto.parsing_dto import ParseRequest, ParseResult
from research_workspace.application.ports.operation_runner import (
    DocumentParseWorkPlan,
    SnapshotImportWorkPlan,
)
from research_workspace.domain.parsing import DEFAULT_PARSER_CONFIG
from research_workspace.infrastructure.filesystem.snapshots import MaterializedSnapshot
from research_workspace.infrastructure.workers import operation_worker
from research_workspace.infrastructure.workers.operation_worker import (
    CancellationFlag,
    OperationWorker,
    ThreadedOperationRunner,
)
from research_workspace.infrastructure.workers.worker_signals import (
    ParseWorkerResult,
    SnapshotWorkerResult,
    WorkerCompleted,
    WorkerProgress,
)


class RecordingSnapshotPort:
    def __init__(self, *, started=None, release=None) -> None:
        self.thread_ids: list[int] = []
        self.paths: list[Path] = []
        self.started = started
        self.release = release

    def materialize(self, source: Path, item_id):
        self.thread_ids.append(threading.get_ident())
        self.paths.append(source)
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            self.release.wait(timeout=5)
        return MaterializedSnapshot("a" * 64, 1, "sources/sha256/aa/a/content", False)


class RecordingParser:
    parser_id = "recording"
    parser_version = "1.0"
    supported_mime_types = frozenset({"application/pdf"})

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def parse(self, request: ParseRequest) -> ParseResult:
        self.paths.append(request.snapshot_path)
        return ParseResult(None, (), "PDF_CORRUPT")


def _parse_request(path: Path) -> ParseRequest:
    return ParseRequest(
        uuid4(), uuid4(), path, "b" * 64, "application/pdf", DEFAULT_PARSER_CONFIG
    )


def test_worker_has_no_database_widget_repository_or_network_authority() -> None:
    source = inspect.getsource(operation_worker)
    lowered = source.lower()
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
    ):
        assert forbidden not in lowered
    signature = inspect.signature(OperationWorker)
    assert set(signature.parameters) == {"snapshot_port", "parsers"}


def test_worker_plans_and_signal_payloads_are_immutable(tmp_path: Path) -> None:
    plan = SnapshotImportWorkPlan(uuid4(), uuid4(), tmp_path / "source.pdf")
    progress = WorkerProgress(plan.operation_id, "copying", 0, 1)
    result = SnapshotWorkerResult(
        plan.operation_id,
        plan.import_item_id,
        MaterializedSnapshot("a" * 64, 1, "sources/sha256/aa/a/content", False),
    )
    completed = WorkerCompleted(plan.operation_id, result)

    for value in (plan, progress, result, completed):
        with pytest.raises((FrozenInstanceError, AttributeError)):
            value.operation_id = uuid4()


def test_parser_receives_only_the_frozen_declared_snapshot(tmp_path: Path) -> None:
    declared = tmp_path / "declared-snapshot"
    parser = RecordingParser()
    worker = OperationWorker(RecordingSnapshotPort(), {parser.parser_id: parser})
    request = _parse_request(declared)
    plan = DocumentParseWorkPlan(uuid4(), parser.parser_id, request)

    terminal = worker.run(plan, CancellationFlag(), lambda _progress: None)

    assert isinstance(terminal, WorkerCompleted)
    assert isinstance(terminal.result, ParseWorkerResult)
    assert parser.paths == [declared]
    assert terminal.result.parse_result.error_code == "PDF_CORRUPT"


def test_runner_executes_io_off_thread_and_delivers_result_on_main_thread(
    qtbot, tmp_path: Path
) -> None:
    main_thread = threading.get_ident()
    port = RecordingSnapshotPort()
    runner = ThreadedOperationRunner(OperationWorker(port, {}))
    handle = runner.start(SnapshotImportWorkPlan(uuid4(), uuid4(), tmp_path / "source.pdf"))
    delivered: list[int] = []
    handle.on_completed(lambda _result: delivered.append(threading.get_ident()))

    qtbot.waitUntil(lambda: bool(delivered), timeout=5000)

    assert port.thread_ids and port.thread_ids[0] != main_thread
    assert delivered == [main_thread]
    assert handle.join(timeout=1)
    assert runner.shutdown(timeout=1)


def test_cancelled_work_never_emits_completed(qtbot, tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    port = RecordingSnapshotPort(started=started, release=release)
    runner = ThreadedOperationRunner(OperationWorker(port, {}))
    handle = runner.start(SnapshotImportWorkPlan(uuid4(), uuid4(), tmp_path / "source.pdf"))
    completed: list[object] = []
    cancelled: list[object] = []
    handle.on_completed(completed.append)
    handle.on_cancelled(cancelled.append)

    qtbot.waitUntil(started.is_set, timeout=5000)
    handle.cancel()
    release.set()
    qtbot.waitUntil(lambda: bool(cancelled), timeout=5000)

    assert completed == []
    assert handle.join(timeout=1)
    assert runner.shutdown(timeout=1)


def test_shutdown_waits_for_safe_boundary_without_force_termination(qtbot, tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    port = RecordingSnapshotPort(started=started, release=release)
    runner = ThreadedOperationRunner(OperationWorker(port, {}))
    handle = runner.start(SnapshotImportWorkPlan(uuid4(), uuid4(), tmp_path / "source.pdf"))

    qtbot.waitUntil(started.is_set, timeout=5000)
    assert handle.shutdown(timeout=0.01) is False
    release.set()
    assert handle.shutdown(timeout=2) is True
    assert runner.shutdown(timeout=1)
