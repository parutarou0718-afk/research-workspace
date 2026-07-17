from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from research_workspace.application.dto.recovery_dto import RecoveryPlan
from research_workspace.application.services.recovery_points import RecoveryPointService
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    RecoveryPointModel,
    RecoverySlotModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.recovery.sqlite_recovery import SQLiteRecoveryAdapter


def _database(tmp_path: Path):
    database_path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(database_path)
    factory = session_factory(engine)
    with factory.begin() as session:
        workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
    assert workspace_id is not None
    return database_path, engine, factory, workspace_id


class _NotCancelled:
    cancelled = False


def _plan(factory, workspace_id, database_path, root, command_type: str, key: str) -> RecoveryPlan:
    command_id = uuid4()
    now = datetime.now(timezone.utc)
    fingerprint = ("%064x" % command_id.int)[-64:]
    with factory.begin() as session:
        session.add(
            ApplicationCommandModel(
                id=command_id,
                command_type=command_type,
                contract_version="1.0",
                idempotency_key=key,
                request_fingerprint=fingerprint,
                actor_type="user",
                actor_id="tester",
                permission_context_json='{"schema_version":"1.0"}',
                status="running",
                requested_at=now,
                started_at=now,
                committed_at=None,
                failed_at=None,
                recovery_point_id=None,
                undo_of_command_id=None,
                result_summary_json=None,
                error_code=None,
                migration_batch_id=None,
            )
        )
    return RecoveryPlan(
        uuid4(),
        command_id,
        command_type,
        fingerprint,
        workspace_id,
        database_path,
        root / "recovery",
        "0004_gate3_protected_crud",
    )


def test_first_and_later_recovery_points_rotate_two_verified_slots(tmp_path) -> None:
    database_path, engine, factory, workspace_id = _database(tmp_path)
    try:
        adapter = SQLiteRecoveryAdapter()
        coordinator = SqlWriteCoordinator(factory, data_directory=tmp_path)
        service = RecoveryPointService(adapter, coordinator)

        first = service.create(_plan(factory, workspace_id, database_path, tmp_path, "paper.create", "key-1"), cancellation=_NotCancelled())
        second = service.create(_plan(factory, workspace_id, database_path, tmp_path, "idea.create", "key-2"), cancellation=_NotCancelled())
        third = service.create(_plan(factory, workspace_id, database_path, tmp_path, "submission.create", "key-3"), cancellation=_NotCancelled())

        assert (first.generation, second.generation, third.generation) == (1, 2, 3)
        assert third.database_sha256 != ""
        assert third.snapshot_count == 0
        assert (tmp_path / "recovery" / "current" / "workspace.db").is_file()
        assert (tmp_path / "recovery" / "previous" / "workspace.db").is_file()

        with factory() as session:
            slots = {
                row.slot_name: row
                for row in session.scalars(
                    select(RecoverySlotModel).where(
                        RecoverySlotModel.workspace_id == workspace_id
                    )
                )
            }
            assert slots["current"].generation == 3
            assert slots["previous"].generation == 2
            assert session.get(RecoveryPointModel, first.recovery_point_id).physical_state == "superseded"
            assert session.get(ApplicationCommandModel, third.command_id).recovery_point_id == third.recovery_point_id
    finally:
        engine.dispose()


def test_recovery_failure_never_binds_command_or_destroys_prior_slot(
    tmp_path, monkeypatch
) -> None:
    database_path, engine, factory, _ = _database(tmp_path)
    try:
        adapter = SQLiteRecoveryAdapter()
        service = RecoveryPointService(adapter, SqlWriteCoordinator(factory, data_directory=tmp_path))
        workspace_id = service._coordinator.workspace_id()
        first = service.create(_plan(factory, workspace_id, database_path, tmp_path, "paper.create", "key-1"), cancellation=_NotCancelled())
        current_hash = (tmp_path / "recovery" / "current" / "manifest.sha256").read_text("ascii")

        plan = _plan(factory, workspace_id, database_path, tmp_path, "idea.create", "key-2")
        monkeypatch.setattr(
            adapter,
            "_build_manifest",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
        )
        try:
            service.create(plan, cancellation=_NotCancelled())
        except Exception as exc:
            assert getattr(exc, "error_code", str(exc)) == "RECOVERY_POINT_FAILED"
        else:
            raise AssertionError("corrupt source database must fail")

        assert (tmp_path / "recovery" / "current" / "manifest.sha256").read_text("ascii") == current_hash
        with factory() as session:
            assert session.get(ApplicationCommandModel, plan.command_id).recovery_point_id is None
            assert session.get(RecoveryPointModel, first.recovery_point_id) is not None
    finally:
        engine.dispose()
