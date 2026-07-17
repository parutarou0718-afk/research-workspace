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


def test_undo_create_is_blocked_by_later_dependencies() -> None:
    entity_id = uuid4()
    created = rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Paper",
        "entity_id": str(entity_id), "row_version": 1,
        "fields": {
            "title": "A", "status": "active",
            "current_version_id": None, "deleted_at": None,
        },
    })
    change = UndoChange(
        "Paper", entity_id, "create", None, created,
        ("title",), created, dependency_count=1,
    )
    with pytest.raises(UndoError, match="UNDO_DEPENDENCY_CONFLICT"):
        plan_compensating_undo(
            uuid4(), uuid4(), NOW,
            UndoPreflight("committed", False, False, (change,)),
        )


def test_undo_soft_delete_restores_visibility_and_delete_pair() -> None:
    entity_id = uuid4()
    before = rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Paper",
        "entity_id": str(entity_id), "row_version": 1,
        "fields": {
            "title": "A", "status": "active",
            "current_version_id": None, "deleted_at": None,
        },
    })
    after_value = __import__("json").loads(before)
    after_value["row_version"] = 2
    after_value["fields"]["deleted_at"] = "2026-07-17T00:00:00Z"
    after = rfc8785.dumps(after_value)
    mutation = plan_compensating_undo(
        uuid4(), uuid4(), NOW,
        UndoPreflight(
            "committed", False, False,
            (UndoChange(
                "Paper", entity_id, "soft_delete", before, after,
                ("deleted_at",), after,
            ),),
        ),
    )[0]
    assert b'"deleted_at":null' in mutation.after_snapshot
