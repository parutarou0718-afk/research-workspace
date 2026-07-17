from datetime import datetime, timezone
from uuid import uuid4

from research_workspace.application.queries.get_ideas import project_idea
from research_workspace.application.queries.get_papers import project_paper
from research_workspace.application.queries.get_submissions import project_submission
from research_workspace.domain.entities import Idea, Paper, Submission
from research_workspace.domain.enums import (
    IdeaOriginType,
    IdeaStatus,
    PaperStatus,
    SubmissionStatus,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def test_crud_read_models_are_immutable_and_expose_only_current_actions() -> None:
    command_id = uuid4()
    paper = Paper(
        uuid4(), "Paper", PaperStatus.ACTIVE, None, NOW, NOW, None, 3,
        command_id, command_id, None,
    )
    idea = Idea(
        uuid4(), "Idea", "Markdown", IdeaStatus.UNUSED,
        IdeaOriginType.MANUAL, NOW, NOW, NOW, 4, command_id, command_id,
        command_id,
    )
    submission = Submission(
        uuid4(), paper.id, "Venue", SubmissionStatus.READY, None, None, None,
        NOW, NOW, None, 2, command_id, command_id, None,
    )

    paper_view = project_paper(paper)
    idea_view = project_idea(idea)
    submission_view = project_submission(submission)

    assert paper_view.actions == ("edit", "soft_delete", "set_current_version")
    assert idea_view.actions == ("restore",)
    assert submission_view.allowed_transitions == ("preparing", "submitted")
    assert submission_view.actions == ("edit", "soft_delete", "transition")
    assert paper_view.row_version == 3


def test_deleted_and_history_rows_remain_explicit_not_silently_filtered() -> None:
    command_id = uuid4()
    deleted = Paper(
        uuid4(), "Deleted", PaperStatus.ARCHIVED, None, NOW, NOW, NOW, 2,
        command_id, command_id, command_id,
    )
    view = project_paper(deleted)
    assert view.deleted_at == NOW
    assert view.actions == ("restore",)

