from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import rfc8785
from sqlalchemy import select

from research_workspace.application.commands.manage_paper import (
    create_paper,
    update_paper,
)
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.queries.get_papers import GetPapersQuery
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.infrastructure.db.models import PaperModel
from research_workspace.infrastructure.db.repositories import (
    SqlGate1WriteRepository,
    SqlPaperReadRepository,
)
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator, WriteCoordinatorError


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _setup(tmp_path: Path):
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    return engine, factory, SqlWriteCoordinator(
        factory, repository_factory=SqlGate1WriteRepository, data_directory=tmp_path
    )


def _plan(command_id, key, entity_id, expected=()):
    permission = rfc8785.dumps(
        {
            "actor_type": "user",
            "actor_id": "tester",
            "workspace_id": "43000000-0000-0000-0000-000000000001",
        }
    )
    return CommandPlan(
        command_id,
        "paper.create",
        key,
        ("%064x" % command_id.int)[-64:],
        permission,
        (("Paper", entity_id),),
        expected,
        b"{}",
        True,
    )


def _protect(coordinator, plan):
    coordinator.persist_command_envelope(plan)
    coordinator.persist_verified_recovery(
        plan,
        VerifiedRecoveryPoint(
            uuid4(),
            plan.command_id,
            coordinator.next_recovery_generation(),
            "b" * 64,
            0,
            "c" * 64,
            rfc8785.dumps(
                {
                    "schema_revision": "0004_gate3_protected_crud",
                    "created_at": "2026-07-17T00:00:00Z",
                }
            ),
            "current",
        ),
    )


def test_create_update_query_and_atomic_row_version(tmp_path) -> None:
    engine, factory, coordinator = _setup(tmp_path)
    paper_id = uuid4()
    try:
        create_id = uuid4()
        create_plan = _plan(create_id, "paper-create", paper_id)
        _protect(coordinator, create_plan)
        coordinator.commit_mutations(
            create_plan, (create_paper(create_id, paper_id, " Paper ", "active", NOW),)
        )
        with factory() as session:
            current = GetPapersQuery(SqlPaperReadRepository(session)).get(paper_id)
        assert current.title == "Paper"
        assert current.row_version == 1
        assert current.created_by_command_id == create_id

        update_id = uuid4()
        update_plan = _plan(update_id, "paper-update", paper_id, (("Paper", paper_id, 1),))
        _protect(coordinator, update_plan)
        coordinator.commit_mutations(
            update_plan,
            (update_paper(current, update_id, title="Revised", status="archived", now=NOW),),
        )
        with factory() as session:
            row = session.get(PaperModel, paper_id)
            assert row.title == "Revised"
            assert row.row_version == 2
            assert row.created_by_command_id == create_id
            assert row.updated_by_command_id == update_id

        stale_id = uuid4()
        stale = _plan(stale_id, "paper-stale", paper_id, (("Paper", paper_id, 1),))
        _protect(coordinator, stale)
        try:
            coordinator.commit_mutations(
                stale,
                (update_paper(current, stale_id, title="Lost", status="active", now=NOW),),
            )
        except WriteCoordinatorError as exc:
            assert exc.error_code == "CONCURRENT_MODIFICATION"
        else:
            raise AssertionError("stale update must fail")
    finally:
        engine.dispose()
