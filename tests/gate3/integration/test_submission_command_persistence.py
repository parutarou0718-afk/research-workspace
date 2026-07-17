from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import rfc8785
from sqlalchemy import select

from research_workspace.application.commands.manage_submission import create_submission
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.queries.get_submissions import GetSubmissionsQuery
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    PaperModel,
    SubmissionModel,
)
from research_workspace.infrastructure.db.repositories import (
    SqlGate1WriteRepository,
    SqlSubmissionReadRepository,
)
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def test_submission_create_persists_command_context_and_is_queryable(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    coordinator = SqlWriteCoordinator(
        factory, repository_factory=SqlGate1WriteRepository, data_directory=tmp_path
    )
    paper_id, submission_id, command_id = uuid4(), uuid4(), uuid4()
    try:
        with factory.begin() as session:
            adoption = session.scalar(
                select(ApplicationCommandModel).where(
                    ApplicationCommandModel.command_type
                    == "system.migration_adopt_v01"
                )
            )
            session.add(
                PaperModel(
                    id=paper_id, title="Paper", status="active", current_version_id=None,
                    created_at=NOW, updated_at=NOW, deleted_at=None, row_version=1,
                    created_by_command_id=adoption.id, updated_by_command_id=adoption.id,
                    deleted_by_command_id=None,
                )
            )
        permission = rfc8785.dumps(
            {
                "actor_type": "user", "actor_id": "tester",
                "workspace_id": "43000000-0000-0000-0000-000000000001",
            }
        )
        plan = CommandPlan(
            command_id, "submission.create", "submission-create",
            ("%064x" % command_id.int)[-64:], permission,
            (("Submission", submission_id),), (), b"{}", True,
        )
        coordinator.persist_command_envelope(plan)
        coordinator.persist_verified_recovery(
            plan,
            VerifiedRecoveryPoint(
                uuid4(), command_id, coordinator.next_recovery_generation(),
                "b" * 64, 0, "c" * 64,
                rfc8785.dumps(
                    {
                        "schema_revision": "0004_gate3_protected_crud",
                        "created_at": "2026-07-17T00:00:00Z",
                    }
                ),
                "current",
            ),
        )
        mutation = create_submission(
            command_id, submission_id, paper_id, "  Journal  ", "preparing",
            None, None, None, NOW,
        )
        coordinator.commit_mutations(plan, (mutation,))
        with factory() as session:
            row = session.get(SubmissionModel, submission_id)
            assert row.venue == "Journal"
            assert row.created_by_command_id == command_id
            record = GetSubmissionsQuery(SqlSubmissionReadRepository(session)).get(
                submission_id
            )
            assert record.row_version == 1
    finally:
        engine.dispose()
