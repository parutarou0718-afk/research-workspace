from __future__ import annotations

import inspect

from research_workspace.application.services.command_dispatcher import CommandDispatchError
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


def test_failed_command_path_is_separate_and_privacy_safe() -> None:
    signature = inspect.signature(SqlWriteCoordinator.mark_command_failed)
    assert tuple(signature.parameters) == ("self", "command_id", "error_code")
    assert "path" not in str(signature).lower()
    assert "content" not in str(signature).lower()


def test_dispatch_errors_expose_only_stable_code() -> None:
    error = CommandDispatchError("COMMAND_PERMISSION_DENIED")
    assert str(error) == "COMMAND_PERMISSION_DENIED"
    assert error.error_code == "COMMAND_PERMISSION_DENIED"
