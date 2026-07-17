import inspect

from research_workspace.application.ports.repositories import MonitoringRepository
from research_workspace.application.ports.write_coordinator import WriteCoordinator


def test_monitoring_repository_and_coordinator_ports_are_framework_free() -> None:
    repository_source = inspect.getsource(inspect.getmodule(MonitoringRepository))
    coordinator_source = inspect.getsource(inspect.getmodule(WriteCoordinator))
    for source in (repository_source, coordinator_source):
        assert "sqlalchemy" not in source.lower()
        assert "QWidget" not in source
        assert "Qt" not in source
        assert "socket" not in source


def test_task4_defines_interfaces_without_monitoring_runtime_implementations() -> None:
    repository_methods = set(MonitoringRepository.__dict__)
    coordinator_methods = set(WriteCoordinator.__dict__)
    assert {"list_roots", "find_active_root_by_path"} <= repository_methods
    assert {
        "register_monitoring_root",
        "change_monitoring_root_status",
        "remove_monitoring_root",
    } <= coordinator_methods
