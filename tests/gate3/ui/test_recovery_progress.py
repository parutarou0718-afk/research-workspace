from uuid import uuid4

from research_workspace.application.services.operation_dispatcher import (
    ImportParseHandle,
)
from research_workspace.infrastructure.workers.worker_signals import WorkerProgress


def test_recovery_progress_is_immutable_ui_ready_state() -> None:
    handle = ImportParseHandle(__import__("threading").get_ident())
    operation_id = uuid4()
    handle.record_progress(WorkerProgress(operation_id, "copying", 2, 5))
    assert handle.progress_phase == "copying"
    assert (handle.progress_completed, handle.progress_total) == (2, 5)


def test_recovery_handle_suppresses_progress_after_terminal_state() -> None:
    handle = ImportParseHandle(__import__("threading").get_ident())
    handle.finish("cancelled")
    handle.record_progress(WorkerProgress(uuid4(), "copying", 5, 5))
    assert handle.progress_phase is None
