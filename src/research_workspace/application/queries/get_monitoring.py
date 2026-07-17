"""Read-only monitoring-root projection."""

from research_workspace.application.dto.monitoring_dto import MonitoringRootRecord
from research_workspace.application.ports.repositories import MonitoringRepository


class GetMonitoring:
    def __init__(self, repository: MonitoringRepository) -> None:
        self._repository = repository

    def execute(self) -> tuple[MonitoringRootRecord, ...]:
        return self._repository.list_roots()
