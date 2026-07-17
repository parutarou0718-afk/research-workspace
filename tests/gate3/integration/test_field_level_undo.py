from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import rfc8785
from sqlalchemy import select

from research_workspace.application.commands.undo_command import (
    UndoChange,
    UndoPreflight,
    plan_compensating_undo,
)
from research_workspace.application.commands.manage_paper import create_paper
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    DomainEventModel,
)
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository
from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)
from research_workspace.infrastructure.db.write_coordinator import (
    SqlWriteCoordinator,
    WriteCoordinatorError,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _idea(entity_id, version, title, content):
    return rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Idea",
        "entity_id": str(entity_id), "row_version": version,
        "fields": {
            "title": title, "content": content, "status": "unused",
            "origin_type": "manual", "deleted_at": None,
        },
    })


def test_multi_entity_preflight_creates_field_aware_compensations() -> None:
    first, second = uuid4(), uuid4()
    changes = (
        UndoChange(
            "Idea", first, "update", _idea(first, 1, "A", "one"),
            _idea(first, 2, "B", "one"), ("title",),
            _idea(first, 2, "B", "one"),
        ),
        UndoChange(
            "Idea", second, "update", _idea(second, 1, "C", "two"),
            _idea(second, 2, "D", "two"), ("title",),
            _idea(second, 3, "D", "later content"),
        ),
    )
    mutations = plan_compensating_undo(
        uuid4(), uuid4(), NOW,
        UndoPreflight("committed", False, False, changes),
    )
    assert len(mutations) == 2
    assert b'"title":"A"' in mutations[0].after_snapshot
    assert b'"content":"later content"' in mutations[1].after_snapshot


def _protect(coordinator, plan):
    coordinator.persist_command_envelope(plan)
    coordinator.persist_verified_recovery(
        plan,
        VerifiedRecoveryPoint(
            uuid4(), plan.command_id, coordinator.next_recovery_generation(),
            "b" * 64, 0, "c" * 64,
            rfc8785.dumps({
                "schema_revision": "0004_gate3_protected_crud",
                "created_at": "2026-07-17T00:00:00Z",
            }), "current",
        ),
    )


def test_undo_command_links_original_and_emits_new_undo_event(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    coordinator = SqlWriteCoordinator(
        factory, repository_factory=SqlGate1WriteRepository, data_directory=tmp_path
    )
    paper_id, create_id, undo_id = uuid4(), uuid4(), uuid4()
    permission = rfc8785.dumps({
        "actor_type": "user", "actor_id": "tester",
        "workspace_id": "43000000-0000-0000-0000-000000000001",
    })
    try:
        create_plan = CommandPlan(
            create_id, "paper.create", "paper-create",
            ("%064x" % create_id.int)[-64:], permission,
            (("Paper", paper_id),), (), b"{}", True,
        )
        _protect(coordinator, create_plan)
        created = create_paper(create_id, paper_id, "Paper", "active", NOW)
        coordinator.commit_mutations(create_plan, (created,))
        change = UndoChange(
            "Paper", paper_id, "create", None, created.after_snapshot,
            created.changed_fields, created.after_snapshot,
        )
        undo_plan = CommandPlan(
            undo_id, "undo.execute", "paper-create-undo",
            ("%064x" % undo_id.int)[-64:], permission,
            (("Paper", paper_id),), (("Paper", paper_id, 1),), b"{}",
            True, create_id,
        )
        _protect(coordinator, undo_plan)
        coordinator.commit_mutations(
            undo_plan,
            plan_compensating_undo(
                create_id, undo_id, NOW,
                UndoPreflight("committed", False, False, (change,)),
            ),
        )
        with factory() as session:
            undo_row = session.get(ApplicationCommandModel, undo_id)
            assert undo_row.undo_of_command_id == create_id
            event = session.scalar(select(DomainEventModel).where(
                DomainEventModel.command_id == undo_id,
                DomainEventModel.event_type == "command.undo_applied",
            ))
            assert event is not None
        repeat_id = uuid4()
        repeat = CommandPlan(
            repeat_id, "undo.execute", "paper-create-undo-repeat",
            ("%064x" % repeat_id.int)[-64:], permission,
            (("Paper", paper_id),), (("Paper", paper_id, 2),), b"{}",
            True, create_id,
        )
        try:
            coordinator.persist_command_envelope(repeat)
        except WriteCoordinatorError as exc:
            assert exc.error_code == "UNDO_ALREADY_APPLIED"
        else:
            raise AssertionError("one original command may be undone only once")
    finally:
        engine.dispose()
