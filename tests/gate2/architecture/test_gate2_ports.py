import inspect
from typing import get_type_hints

from research_workspace.application.dto.monitoring_dto import MonitoringRootPlan
from research_workspace.application.ports.file_observer import FileObserver


def test_file_observer_port_accepts_only_frozen_plan_and_root_identity() -> None:
    start = inspect.signature(FileObserver.start)
    stop = inspect.signature(FileObserver.stop)
    join = inspect.signature(FileObserver.join)
    assert get_type_hints(FileObserver.start)["plan"] is MonitoringRootPlan
    assert tuple(start.parameters) == ("self", "plan")
    assert tuple(stop.parameters) == ("self", "monitoring_root_id")
    assert tuple(join.parameters) == ("self", "monitoring_root_id", "timeout_seconds")


def test_file_observer_port_exposes_no_framework_database_network_or_task_runtime() -> None:
    source = inspect.getsource(inspect.getmodule(FileObserver))
    for forbidden in (
        "Session",
        "Repository",
        "QWidget",
        "Qt",
        "socket",
        "requests",
        "httpx",
        "TaskExecutor",
        "agent",
    ):
        assert forbidden not in source
