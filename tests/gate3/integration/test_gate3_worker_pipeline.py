from datetime import datetime, timezone
from pathlib import Path
import threading
from uuid import uuid4

import rfc8785

from research_workspace.application.dto.recovery_dto import (
    RecoveryPlan,
    VerifiedRecoveryPoint,
)
from research_workspace.application.services.command_dispatcher import (
    CommandDispatcher,
    CommandResult,
    ExistingCommand,
    PreparedCommand,
    RawCommandEnvelope,
    canonical_request_fingerprint,
)
from research_workspace.application.services.operation_dispatcher import (
    ProtectedCommandPipeline,
)
from research_workspace.application.services.recovery_points import RecoveryWorkPlan
from research_workspace.infrastructure.workers.operation_worker import (
    CancellationFlag,
    OperationWorker,
)
from research_workspace.infrastructure.workers.worker_signals import (
    RecoveryWorkerResult,
    WorkerCompleted,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _recovery_plan():
    return RecoveryPlan(
        uuid4(), uuid4(), "paper.update", "a" * 64, uuid4(),
        Path("workspace.db"), Path("recovery"),
        "0004_gate3_protected_crud",
    )


class _RecoveryPort:
    def __init__(self):
        self.thread_id = None

    def create_verified_recovery(self, plan, generation, report, cancellation):
        self.thread_id = threading.get_ident()
        report(type(
            "Progress", (),
            {"phase": "copying", "bytes_done": 1, "bytes_total": 1},
        )())
        return VerifiedRecoveryPoint(
            uuid4(), plan.command_id, generation, "a" * 64, 1, "b" * 64,
            rfc8785.dumps({"schema_revision": "0004_gate3_protected_crud"}),
            "staging",
        )


def test_recovery_calculation_runs_off_owner_thread_and_returns_immutable_dto() -> None:
    port = _RecoveryPort()
    worker = OperationWorker.with_recovery(object(), {}, port)
    plan = RecoveryWorkPlan(uuid4(), _recovery_plan(), 1)
    owner = threading.get_ident()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(worker.run(plan, CancellationFlag(), lambda _: None))
    )
    thread.start()
    thread.join()
    assert port.thread_id != owner
    assert isinstance(result[0], WorkerCompleted)
    assert isinstance(result[0].result, RecoveryWorkerResult)


class _WorkerHandle:
    def __init__(self, plan):
        self.plan = plan
        self.callbacks = {}
        self.cancelled = False

    def on_progress(self, callback):
        self.callbacks["progress"] = callback

    def on_completed(self, callback):
        self.callbacks["completed"] = callback

    def on_failed(self, callback):
        self.callbacks["failed"] = callback

    def on_cancelled(self, callback):
        self.callbacks["cancelled"] = callback

    def cancel(self):
        self.cancelled = True

    def shutdown(self, timeout=None):
        self.cancel()
        return True


class _Runner:
    def __init__(self):
        self.handles = []

    def start(self, plan):
        handle = _WorkerHandle(plan)
        self.handles.append(handle)
        return handle


class _Dispatcher:
    def __init__(self):
        self.prepare_thread = None
        self.commit_thread = None
        self.prepare_count = 0
        self.commit_count = 0

    def prepare(self, *args, **kwargs):
        self.prepare_thread = threading.get_ident()
        self.prepare_count += 1
        return PreparedCommand(object(), object(), None)

    def commit_prepared(self, prepared, recovery, build_mutations):
        self.commit_thread = threading.get_ident()
        self.commit_count += 1
        return CommandResult(uuid4(), (), 1, False)


def _envelope():
    identity = uuid4()
    return RawCommandEnvelope(
        identity, "paper.update", "1.0", str(identity), "user", "tester",
        uuid4(), NOW, rfc8785.dumps({"title": "Paper"}),
    )


def test_application_prepares_and_persists_on_owner_thread_once() -> None:
    dispatcher, runner = _Dispatcher(), _Runner()
    pipeline = ProtectedCommandPipeline(dispatcher, runner, lambda: 1)
    owner = threading.get_ident()
    handle = pipeline.start(
        _envelope(), capability="paper.write",
        entity_scopes=(("Paper", uuid4()),), expected_versions=(),
        build_mutations=lambda _: (),
    )
    terminal = WorkerCompleted(
        runner.handles[0].plan.operation_id,
        RecoveryWorkerResult(
            runner.handles[0].plan.operation_id,
            VerifiedRecoveryPoint(
                uuid4(), uuid4(), 1, "a" * 64, 1, "b" * 64, b"{}", "staging"
            ),
        ),
    )
    runner.handles[0].callbacks["completed"](terminal)
    assert handle.status == "completed"
    assert dispatcher.prepare_thread == dispatcher.commit_thread == owner
    assert dispatcher.prepare_count == dispatcher.commit_count == 1


def test_cancelled_recovery_never_commits_or_reports_completed() -> None:
    dispatcher, runner = _Dispatcher(), _Runner()
    pipeline = ProtectedCommandPipeline(dispatcher, runner, lambda: 1)
    handle = pipeline.start(
        _envelope(), capability="paper.write",
        entity_scopes=(("Paper", uuid4()),), expected_versions=(),
        build_mutations=lambda _: (),
    )
    handle.cancel()
    runner.handles[0].callbacks["completed"](
        WorkerCompleted(
            runner.handles[0].plan.operation_id,
            RecoveryWorkerResult(
                runner.handles[0].plan.operation_id,
                VerifiedRecoveryPoint(
                    uuid4(), uuid4(), 1, "a" * 64, 1, "b" * 64, b"{}", "staging"
                ),
            ),
        )
    )
    assert handle.status == "cancelled"
    assert handle.completed_count == dispatcher.commit_count == 0


def test_repeated_active_submit_does_not_create_second_recovery() -> None:
    dispatcher, runner = _Dispatcher(), _Runner()
    pipeline = ProtectedCommandPipeline(dispatcher, runner, lambda: 1)
    envelope = _envelope()
    arguments = {
        "capability": "paper.write",
        "entity_scopes": (("Paper", uuid4()),),
        "expected_versions": (),
        "build_mutations": lambda _: (),
    }
    pipeline.start(envelope, **arguments)
    try:
        pipeline.start(envelope, **arguments)
    except ValueError as exc:
        assert str(exc) == "COMMAND_IDEMPOTENCY_CONFLICT"
    else:
        raise AssertionError("duplicate active submit must fail")
    assert len(runner.handles) == dispatcher.prepare_count == 1


def test_ambiguous_prepare_returns_persisted_replay_as_prepared_command() -> None:
    envelope = _envelope()
    result = CommandResult(envelope.command_id, (uuid4(),), 1, False)

    class Coordinator:
        committed = False

        def find_command_by_idempotency(self, key):
            if not self.committed:
                return None
            return ExistingCommand(
                envelope.command_id,
                canonical_request_fingerprint(envelope.request_payload),
                "committed",
                result,
            )

        def persist_command_envelope(self, plan):
            self.committed = True
            raise OSError("acknowledgement lost")

        def mark_command_failed(self, command_id, error_code):
            raise AssertionError("committed command cannot be marked failed")

    prepared = CommandDispatcher(
        Coordinator(), object(), database_path=Path("workspace.db"),
        recovery_root=Path("recovery"),
    ).prepare(
        envelope, capability="paper.write",
        entity_scopes=(("Paper", result.affected_entity_ids[0]),),
        expected_versions=(),
    )
    assert isinstance(prepared, PreparedCommand)
    assert prepared.replay_result == result
