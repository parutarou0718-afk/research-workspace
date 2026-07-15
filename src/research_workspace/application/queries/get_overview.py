"""Application query for the foundation Overview page."""

from research_workspace.application.ports.repositories import OverviewRepository
from research_workspace.presentation.view_models.overview import OverviewViewModel


class GetOverview:
    def __init__(self, repository: OverviewRepository) -> None:
        self._repository = repository

    def execute(self) -> OverviewViewModel:
        data = self._repository.get_overview()
        return OverviewViewModel(
            revision_count=data.revision_count,
            ready_count=data.ready_count,
            upcoming_conference_count=data.upcoming_conference_count,
            upcoming_grant_count=data.upcoming_grant_count,
            suggestions=data.suggestions,
            submission_rows=data.submission_rows,
            activities=data.activities,
            focus_items=data.focus_items,
            focus_progress=data.focus_progress,
        )
