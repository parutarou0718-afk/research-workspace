from __future__ import annotations

import inspect

from research_workspace.application.services.command_dispatcher import CommandDispatcher


def test_dispatcher_has_no_orm_qt_network_or_gate4_dependency() -> None:
    source = inspect.getsource(CommandDispatcher)
    for forbidden in (
        "sqlalchemy",
        "Session",
        "QWidget",
        "PySide6",
        "requests",
        "httpx",
        ".rwsbackup",
    ):
        assert forbidden not in source
