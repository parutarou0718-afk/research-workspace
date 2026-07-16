"""Read-only repository ports used by foundation queries."""

from dataclasses import dataclass
from typing import Protocol

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseSuccessDTO,
    PreparedParseAttempt,
)
from research_workspace.domain.parsing import ParseArtifactIdentity


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
