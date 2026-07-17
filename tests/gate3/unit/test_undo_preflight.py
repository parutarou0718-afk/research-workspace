from datetime import datetime, timezone
from uuid import uuid4

import pytest
import rfc8785

from research_workspace.application.commands.undo_command import (
    UndoChange,
    UndoError,
    UndoPreflight,
    plan_compensating_undo,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _snapshot(entity_id, version, title, status):
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Paper",
        "entity_id": str(entity_id), "row_version": version,
        "fields": {
            "title": title, "status": status,
            "current_version_id": None, "deleted_at": None,
        },
    })


def test_update_undo_restores_only_original_fields_and_keeps_disjoint_change() -> None:
    entity_id = uuid4()
    change = UndoChange(
        "Paper", entity_id, "update",
        _snapshot(entity_id, 1, "A", "active"),
        _snapshot(entity_id, 2, "B", "active"),
        ("title",),
        _snapshot(entity_id, 3, "B", "archived"),
    )
    mutation = plan_compensating_undo(
        uuid4(), uuid4(), NOW,
        UndoPreflight("committed", False, False, (change,)),
    )[0]
    assert b'"title":"A"' in mutation.after_snapshot
    assert b'"status":"archived"' in mutation.after_snapshot
    assert b'"row_version":4' in mutation.after_snapshot
    assert mutation.operation == "undo"


def test_overlapping_later_change_is_an_undo_conflict() -> None:
    entity_id = uuid4()
    change = UndoChange(
        "Paper", entity_id, "update",
        _snapshot(entity_id, 1, "A", "active"),
        _snapshot(entity_id, 2, "B", "active"),
        ("title",), _snapshot(entity_id, 3, "C", "active"),
    )
    with pytest.raises(UndoError, match="UNDO_CONFLICT"):
        plan_compensating_undo(
            uuid4(), uuid4(), NOW,
            UndoPreflight("committed", False, False, (change,)),
        )


@pytest.mark.parametrize(
    "preflight,code",
    [
        (UndoPreflight("failed", False, False, ()), "UNDO_NOT_AVAILABLE"),
        (UndoPreflight("committed", True, False, ()), "UNDO_ALREADY_APPLIED"),
        (UndoPreflight("committed", False, True, ()), "UNDO_NOT_AVAILABLE"),
    ],
)
def test_original_command_must_be_committed_once_and_not_an_undo(
    preflight, code
) -> None:
    with pytest.raises(UndoError, match=code):
        plan_compensating_undo(uuid4(), uuid4(), NOW, preflight)
