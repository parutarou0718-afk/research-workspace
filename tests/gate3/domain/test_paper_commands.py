from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from research_workspace.application.commands.manage_paper import (
    PaperCommandError,
    PaperDependencies,
    PaperVersionRef,
    create_paper,
    set_current_version,
    soft_delete_paper,
    update_paper,
)
from research_workspace.domain.entities import Paper
from research_workspace.domain.enums import PaperStatus


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _paper(**changes) -> Paper:
    values = {
        "id": uuid4(),
        "title": "Title",
        "status": PaperStatus.ACTIVE,
        "current_version_id": None,
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
        "row_version": 1,
        "created_by_command_id": uuid4(),
        "updated_by_command_id": uuid4(),
        "deleted_by_command_id": None,
    }
    values.update(changes)
    return Paper(**values)


def test_create_normalizes_unicode_outer_whitespace_and_keeps_exact_statuses() -> None:
    command_id, paper_id = uuid4(), uuid4()
    mutation = create_paper(command_id, paper_id, "\u3000 Research \u00a0", "active", NOW)
    assert mutation.entity_type == "Paper"
    assert b'"title":"Research"' in mutation.after_snapshot
    assert b'"row_version":1' in mutation.after_snapshot
    with pytest.raises(PaperCommandError, match="COMMAND_VALIDATION_FAILED"):
        create_paper(command_id, paper_id, "x", "draft", NOW)


@pytest.mark.parametrize("title", ["", " " * 3, "x" * 501])
def test_title_must_be_one_to_500_unicode_code_points(title: str) -> None:
    with pytest.raises(PaperCommandError, match="COMMAND_VALIDATION_FAILED"):
        create_paper(uuid4(), uuid4(), title, "active", NOW)


def test_update_increments_version_and_preserves_creator_command() -> None:
    paper = _paper()
    mutation = update_paper(paper, uuid4(), title=" Revised ", status="archived", now=NOW)
    assert mutation.expected_row_version == 1
    assert b'"row_version":2' in mutation.after_snapshot
    assert str(paper.created_by_command_id).encode() not in mutation.changed_fields


@pytest.mark.parametrize(
    "dependencies",
    [
        PaperDependencies(active_submissions=1),
        PaperDependencies(active_relations=1),
        PaperDependencies(active_versions=1),
        PaperDependencies(active_evidence_refs=1),
    ],
)
def test_soft_delete_is_conservative_and_never_cascades(dependencies) -> None:
    with pytest.raises(PaperCommandError, match="DELETE_DEPENDENCY_CONFLICT"):
        soft_delete_paper(_paper(), uuid4(), NOW, dependencies)


def test_current_version_requires_active_member_of_same_paper() -> None:
    paper = _paper()
    with pytest.raises(PaperCommandError, match="INVALID_VERSION_ASSIGNMENT"):
        set_current_version(
            paper,
            uuid4(),
            PaperVersionRef(uuid4(), uuid4(), "active"),
            NOW,
        )
    with pytest.raises(PaperCommandError, match="INVALID_VERSION_ASSIGNMENT"):
        set_current_version(
            paper,
            uuid4(),
            PaperVersionRef(uuid4(), paper.id, "retracted"),
            NOW,
        )
