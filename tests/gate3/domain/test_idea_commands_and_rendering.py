from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from research_workspace.application.commands.manage_idea import (
    IdeaCommandError,
    IdeaDependencies,
    create_idea,
    soft_delete_idea,
    update_idea,
)
from research_workspace.domain.entities import Idea
from research_workspace.domain.enums import IdeaOriginType, IdeaStatus


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _idea(**changes) -> Idea:
    values = {
        "id": uuid4(),
        "title": "Idea",
        "content": "  original markdown  ",
        "status": IdeaStatus.UNUSED,
        "origin_type": IdeaOriginType.MANUAL,
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
        "row_version": 1,
        "created_by_command_id": uuid4(),
        "updated_by_command_id": uuid4(),
        "deleted_by_command_id": None,
    }
    values.update(changes)
    return Idea(**values)


def test_create_trims_title_but_preserves_content_except_newlines() -> None:
    mutation = create_idea(
        uuid4(), uuid4(), "  Title  ", "  line 1\r\nline 2\r  ", "unused", NOW
    )
    assert b'"title":"Title"' in mutation.after_snapshot
    assert b'"content":"  line 1\\nline 2\\n  "' in mutation.after_snapshot
    assert b'"origin_type":"manual"' in mutation.after_snapshot


@pytest.mark.parametrize(
    "content",
    ["", " \r\n\t", "x" * 1_000_001],
    ids=["empty", "whitespace-only", "over-limit"],
)
def test_content_is_nonblank_and_bounded_without_destructive_trim(content) -> None:
    with pytest.raises(IdeaCommandError, match="COMMAND_VALIDATION_FAILED"):
        create_idea(uuid4(), uuid4(), "Title", content, "unused", NOW)


def test_application_creation_cannot_claim_nonmanual_origin() -> None:
    with pytest.raises(IdeaCommandError, match="COMMAND_VALIDATION_FAILED"):
        create_idea(
            uuid4(), uuid4(), "Title", "body", "unused", NOW, origin_type="document"
        )


def test_update_preserves_manual_origin_and_increments_version() -> None:
    mutation = update_idea(
        _idea(), uuid4(), title="New", content="raw **Markdown**", status="used", now=NOW
    )
    assert mutation.expected_row_version == 1
    assert b'"row_version":2' in mutation.after_snapshot
    assert b'"content":"raw **Markdown**"' in mutation.after_snapshot


@pytest.mark.parametrize(
    "dependencies",
    [IdeaDependencies(active_relations=1), IdeaDependencies(active_evidence_refs=1)],
)
def test_delete_rejects_active_relations_or_evidence(dependencies) -> None:
    with pytest.raises(IdeaCommandError, match="DELETE_DEPENDENCY_CONFLICT"):
        soft_delete_idea(_idea(), uuid4(), NOW, dependencies)
