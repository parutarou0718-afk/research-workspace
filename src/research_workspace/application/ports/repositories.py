"""Read-only repository ports used by foundation queries."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseSuccessDTO,
    PreparedParseAttempt,
)
from research_workspace.application.dto.monitoring_dto import MonitoringRootRecord
from research_workspace.domain.parsing import ParseArtifactIdentity
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.services.command_dispatcher import DomainMutation


@dataclass(frozen=True, slots=True)
class OverviewData:
    revision_count: int
    ready_count: int
    upcoming_conference_count: int
    upcoming_grant_count: int
    suggestions: tuple[str, ...]
    submission_rows: tuple[str, ...]
    activities: tuple[str, ...]
    focus_items: tuple[str, ...]
    focus_progress: int


class OverviewRepository(Protocol):
    def get_overview(self) -> OverviewData:
        """Return the complete read-only overview projection."""


class MonitoringRepository(Protocol):
    def list_roots(self) -> tuple[MonitoringRootRecord, ...]: ...

    def get_root(self, monitoring_root_id: UUID) -> MonitoringRootRecord | None: ...

    def find_active_root_by_path(self, normalized_path: str) -> MonitoringRootRecord | None: ...


class Gate1WriteRepository(Protocol):
    """Session-bound repository; callers never receive its persistence handle."""

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO: ...

    def start_parse_attempt(
        self, seed: ParseAttemptSeed, identity: ParseArtifactIdentity
    ) -> PreparedParseAttempt: ...

    def register_parse_failure(self, result: ParseFailureDTO) -> tuple[object, object]: ...

    def register_parse_success(
        self, result: ParseSuccessDTO, parsed_document: dict[str, object]
    ) -> tuple[object, object, object]: ...


class RecoveryRepository(Protocol):
    def next_generation(self) -> int: ...

    def activate(self, point: VerifiedRecoveryPoint) -> None: ...


class ProtectedWriteRepository(Protocol):
    def apply_mutation(self, mutation: DomainMutation) -> None: ...
