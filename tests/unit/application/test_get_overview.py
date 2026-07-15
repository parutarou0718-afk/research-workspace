from dataclasses import FrozenInstanceError

import pytest

from research_workspace.application.ports.repositories import OverviewData
from research_workspace.application.queries.get_overview import GetOverview
from research_workspace.presentation.view_models.overview import OverviewViewModel


class StubOverviewRepository:
    def get_overview(self) -> OverviewData:
        return OverviewData(
            revision_count=7,
            ready_count=2,
            upcoming_conference_count=11,
            upcoming_grant_count=5,
            suggestions=("repository suggestion",),
            submission_rows=("repository row",),
            activities=("repository activity",),
            focus_items=("repository focus",),
            focus_progress=73,
        )


def test_overview_is_built_only_from_repository_values():
    view_model = GetOverview(StubOverviewRepository()).execute()

    assert view_model.revision_count == 7
    assert view_model.ready_count == 2
    assert view_model.upcoming_conference_count == 11
    assert view_model.upcoming_grant_count == 5
    assert view_model.suggestions == ("repository suggestion",)
    assert view_model.submission_rows == ("repository row",)
    assert view_model.activities == ("repository activity",)
    assert view_model.focus_items == ("repository focus",)
    assert view_model.focus_progress == 73


def test_overview_view_model_and_its_collections_are_immutable():
    view_model = GetOverview(StubOverviewRepository()).execute()

    assert isinstance(view_model.suggestions, tuple)
    assert isinstance(view_model.submission_rows, tuple)
    assert isinstance(view_model.activities, tuple)
    assert isinstance(view_model.focus_items, tuple)
    with pytest.raises(FrozenInstanceError):
        view_model.revision_count = 8


def test_overview_view_model_copies_collection_inputs_to_tuples():
    suggestions = ["mutable input"]
    view_model = OverviewViewModel(
        revision_count=1,
        ready_count=2,
        upcoming_conference_count=3,
        upcoming_grant_count=4,
        suggestions=suggestions,
        submission_rows=[],
        activities=[],
        focus_items=[],
        focus_progress=5,
    )

    suggestions.append("later mutation")

    assert view_model.suggestions == ("mutable input",)
    assert view_model.submission_rows == ()
    assert view_model.activities == ()
    assert view_model.focus_items == ()
