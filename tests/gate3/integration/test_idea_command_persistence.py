from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import rfc8785

from research_workspace.application.commands.manage_idea import create_idea, update_idea
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.queries.get_ideas import GetIdeasQuery
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository, SqlIdeaReadRepository
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _setup(tmp_path: Path):
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    return engine, factory, SqlWriteCoordinator(factory, repository_factory=SqlGate1WriteRepository, data_directory=tmp_path)


def _plan(command_id, key, entity_id):
    return CommandPlan(
        command_id, "idea.create", key, ("%064x" % command_id.int)[-64:],
        rfc8785.dumps({"actor_type": "user", "actor_id": "tester"}),
        (("Idea", entity_id),), (), b"{}", True,
    )


def _protect(coordinator, plan):
    coordinator.persist_command_envelope(plan)
    coordinator.persist_verified_recovery(
        plan,
        VerifiedRecoveryPoint(
            uuid4(), plan.command_id, coordinator.next_recovery_generation(),
            "b" * 64, 0, "c" * 64,
            rfc8785.dumps({"schema_revision": "0004_gate3_protected_crud", "created_at": "2026-07-17T00:00:00Z"}),
            "current",
        ),
    )


def test_create_update_and_query_preserve_raw_markdown(tmp_path) -> None:
    engine, factory, coordinator = _setup(tmp_path)
    idea_id = uuid4()
    try:
        create_id = uuid4()
        plan = _plan(create_id, "idea-create", idea_id)
        _protect(coordinator, plan)
        coordinator.commit_mutations(
            plan, (create_idea(create_id, idea_id, " Idea ", "<b>raw</b>\r\n**bold**", "unused", NOW),)
        )
        with factory() as session:
            current = GetIdeasQuery(SqlIdeaReadRepository(session)).get(idea_id)
        assert current.content == "<b>raw</b>\n**bold**"
        assert current.origin_type.value == "manual"

        update_id = uuid4()
        update_plan = _plan(update_id, "idea-update", idea_id)
        _protect(coordinator, update_plan)
        coordinator.commit_mutations(
            update_plan,
            (update_idea(current, update_id, title="Idea", content="new", status="used", now=NOW),),
        )
        with factory() as session:
            updated = GetIdeasQuery(SqlIdeaReadRepository(session)).get(idea_id)
        assert updated.content == "new"
        assert updated.row_version == 2
        assert updated.created_by_command_id == create_id
        assert updated.updated_by_command_id == update_id
    finally:
        engine.dispose()
