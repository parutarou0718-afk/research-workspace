"""Read-only repository ports used by foundation queries."""

from dataclasses import dataclass
from typing import Protocol

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO


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
