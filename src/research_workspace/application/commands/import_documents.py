"""Application command for deterministic read-only document import."""

from __future__ import annotations

from collections.abc import Callable

from research_workspace.application.dto.import_dto import ImportBatchResult, ImportRequest
from research_workspace.application.services.import_orchestrator import ImportOrchestrator


class ImportDocumentsCommand:
    def __init__(
        self,
        orchestrator: ImportOrchestrator,
        *,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        self.orchestrator = orchestrator
        self._cancel_requested = cancel_requested

    def execute(self, request: ImportRequest) -> ImportBatchResult:
        return self.orchestrator.execute(request, cancel_requested=self._cancel_requested)
