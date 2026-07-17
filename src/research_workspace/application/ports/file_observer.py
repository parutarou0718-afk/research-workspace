"""Framework-free Gate 2 filesystem observation port."""

from typing import Protocol
from uuid import UUID

from research_workspace.application.dto.monitoring_dto import MonitoringRootPlan


class FileObserver(Protocol):
    def start(self, plan: MonitoringRootPlan) -> None: ...

    def stop(self, monitoring_root_id: UUID) -> None: ...

    def join(self, monitoring_root_id: UUID, timeout_seconds: float) -> bool: ...
