from __future__ import annotations

import inspect

from research_workspace.application.dto.recovery_dto import RecoveryProgress
from research_workspace.application.ports.sqlite_backup import SQLiteBackupPort
from research_workspace.infrastructure.recovery.sqlite_recovery import SQLiteRecoveryAdapter


def test_recovery_port_and_progress_are_framework_free_and_immutable() -> None:
    source = inspect.getsource(SQLiteBackupPort)
    assert "Session" not in source
    assert "QWidget" not in source
    assert "create_verified_recovery" in source
    progress = RecoveryProgress("verifying", 10, 100)
    assert progress.bytes_done == 10
    try:
        progress.bytes_done = 11
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("progress DTO must be immutable")


def test_adapter_has_no_gate4_or_qt_semantics() -> None:
    source = inspect.getsource(SQLiteRecoveryAdapter)
    assert ".rwsbackup" not in source
    assert "QWidget" not in source
    assert "PySide6" not in source
    assert "restore" not in source.lower()
