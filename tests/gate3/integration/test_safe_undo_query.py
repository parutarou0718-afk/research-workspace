from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import rfc8785

from research_workspace.application.commands.manage_paper import create_paper
from research_workspace.application.commands.undo_command import (
    UndoChange,
    UndoPreflight,
)
from research_workspace.application.queries.get_version_candidates import (
    GetSafeUndoQuery,
    UndoHistoryRecord,
)
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.infrastructure.db.repositories import (
    SqlGate1WriteRepository,
    SqlUndoHistoryRepository,
)
from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _snapshot(entity_id, version, title):
    return rfc8785.dumps({
        "schema_version": "1.0",
        "entity_type": "Paper",
        "entity_id": str(entity_id),
        "row_version": version,
        "fields": {
            "title": title,
            "status": "active",
            "current_version_id": None,
            "deleted_at": None,
        },
    })


def _record(*, actor="user", undone=False, is_undo=False, overlap=False):
    entity_id, command_id = uuid4(), uuid4()
    current_title = "Later" if overlap else "Changed"
    change = UndoChange(
        "Paper", entity_id, "update",
        _snapshot(entity_id, 1, "Original"),
        _snapshot(entity_id, 2, "Changed"),
        ("title",),
        _snapshot(entity_id, 3, current_title),
    )
    return UndoHistoryRecord(
        command_id, "paper.update", actor, NOW,
        UndoPreflight("committed", undone, is_undo, (change,)),
    )


class _Repository:
    def __init__(self, records):
        self.records = tuple(records)

    def list_undo_history(self):
        return self.records


def test_safe_undo_query_filters_system_undo_repeat_and_current_conflicts() -> None:
    safe = _record()
    records = (
        safe,
        _record(actor="system"),
        _record(undone=True),
        _record(is_undo=True),
        _record(overlap=True),
    )
    result = GetSafeUndoQuery(_Repository(records)).execute(as_of=NOW)
    assert [item.command_id for item in result] == [safe.command_id]
    assert result[0].affected_entity_ids == (
        safe.preflight.changes[0].entity_id,
    )


def test_safe_undo_query_is_deterministic_and_read_only() -> None:
    later = _record()
    earlier = UndoHistoryRecord(
        later.command_id, later.command_type, later.actor_type,
        NOW.replace(hour=0), later.preflight,
    )
    repository = _Repository((later, earlier))
    first = GetSafeUndoQuery(repository).execute(as_of=NOW)
    second = GetSafeUndoQuery(repository).execute(as_of=NOW)
    assert first == second
    assert tuple(item.committed_at for item in first) == tuple(
        sorted((item.committed_at for item in first), reverse=True)
    )


def test_sql_history_projects_current_facts_for_safe_undo(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    coordinator = SqlWriteCoordinator(
        factory, repository_factory=SqlGate1WriteRepository,
        data_directory=tmp_path,
    )
    paper_id, command_id = uuid4(), uuid4()
    permission = rfc8785.dumps({
        "actor_type": "user",
        "actor_id": "tester",
        "workspace_id": str(uuid4()),
    })
    plan = CommandPlan(
        command_id, "paper.create", str(command_id), "a" * 64, permission,
        (("Paper", paper_id),), (), b"{}", True,
    )
    try:
        coordinator.persist_command_envelope(plan)
        coordinator.persist_verified_recovery(
            plan,
            VerifiedRecoveryPoint(
                uuid4(), command_id, 1, "b" * 64, 0, "c" * 64,
                rfc8785.dumps({
                    "schema_revision": "0004_gate3_protected_crud",
                    "created_at": "2026-07-17T00:00:00Z",
                }),
                "current",
            ),
        )
        coordinator.commit_mutations(
            plan, (create_paper(command_id, paper_id, "Paper", "active", NOW),)
        )
        with factory() as session:
            result = GetSafeUndoQuery(
                SqlUndoHistoryRepository(session)
            ).execute(as_of=NOW)
        assert [item.command_id for item in result] == [command_id]
        assert result[0].affected_entity_ids == (paper_id,)
    finally:
        engine.dispose()
