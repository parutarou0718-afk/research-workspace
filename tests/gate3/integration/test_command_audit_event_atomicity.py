from __future__ import annotations

from datetime import datetime, timezone
import json
import rfc8785
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from research_workspace.application.services.command_dispatcher import (
    CommandPlan,
    DomainMutation,
)
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    AuditChangeModel,
    DomainEventModel,
)
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


def _coordinator(tmp_path: Path, repository_factory):
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    return engine, session_factory(engine), SqlWriteCoordinator(
        session_factory(engine), repository_factory=repository_factory, data_directory=tmp_path
    )


def _plan() -> CommandPlan:
    command_id = uuid4()
    permission = {
        "schema_version": "1.0",
        "actor_type": "user",
        "actor_id": "tester",
        "workspace_id": "43000000-0000-0000-0000-000000000001",
        "capabilities": ["paper.write"],
        "scope_refs": [],
        "path_scopes": [],
        "network_allowed": False,
        "granted_at": "2026-07-17T00:00:00Z",
        "policy_version": "1.0",
        "authorization_decision_id": "43000000-0000-0000-0000-000000000003",
    }
    return CommandPlan(
        command_id,
        "paper.create",
        "key",
        "a" * 64,
        json.dumps(permission, separators=(",", ":"), sort_keys=True).encode(),
        (("Paper", uuid4()),),
        (),
        b'{"title":"A"}',
        True,
    )


def _mutation(entity_id) -> DomainMutation:
    snapshot = json.dumps(
        {
            "schema_version": "1.0",
            "entity_type": "Paper",
            "entity_id": str(entity_id),
            "row_version": 1,
            "fields": {"title": "A", "status": "active"},
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return DomainMutation(
        "Paper",
        entity_id,
        "create",
        None,
        None,
        snapshot,
        ("status", "title"),
        "paper.created",
        json.dumps(
            {
                "entity_id": str(entity_id),
                "row_version": 1,
                "changed_fields": ["status", "title"],
            },
            separators=(",", ":"),
        ).encode(),
    )


def _protect(coordinator, plan) -> None:
    manifest = rfc8785.dumps(
        {
            "schema_revision": "0004_gate3_protected_crud",
            "created_at": "2026-07-17T00:00:00Z",
        }
    )
    coordinator.persist_verified_recovery(
        plan,
        VerifiedRecoveryPoint(
            uuid4(), plan.command_id, 1, "b" * 64, 0, "c" * 64, manifest, "current"
        ),
    )


def test_audit_indices_snapshots_and_events_commit_with_repository_fact(tmp_path) -> None:
    class Repo:
        def __init__(self, session):
            self.session = session

        def apply_mutation(self, mutation):
            return None

    engine, factory, coordinator = _coordinator(tmp_path, Repo)
    try:
        plan = _plan()
        coordinator.persist_command_envelope(plan)
        _protect(coordinator, plan)
        result = coordinator.commit_mutations(plan, (_mutation(plan.entity_scopes[0][1]),))
        assert result.affected_count == 1
        with factory() as session:
            command_row = session.get(ApplicationCommandModel, plan.command_id)
            changes = session.scalars(
                select(AuditChangeModel).where(AuditChangeModel.command_id == plan.command_id)
            ).all()
            events = session.scalars(
                select(DomainEventModel).where(DomainEventModel.command_id == plan.command_id)
            ).all()
            assert command_row.status == "committed"
            assert [change.change_index for change in changes] == [0]
            assert json.loads(changes[0].changed_fields_json) == ["status", "title"]
            assert len(events) == 1
            assert "/" not in events[0].payload_json
    finally:
        engine.dispose()


def test_repository_or_event_failure_rolls_back_audit_and_business_event(tmp_path) -> None:
    class FailingRepo:
        def __init__(self, session):
            pass

        def apply_mutation(self, mutation):
            raise ValueError("CONCURRENT_MODIFICATION")

    engine, factory, coordinator = _coordinator(tmp_path, FailingRepo)
    try:
        plan = _plan()
        coordinator.persist_command_envelope(plan)
        _protect(coordinator, plan)
        try:
            coordinator.commit_mutations(plan, (_mutation(plan.entity_scopes[0][1]),))
        except Exception:
            pass
        with factory() as session:
            assert session.scalar(select(func.count(AuditChangeModel.id))) == 0
            assert session.scalar(
                select(func.count(DomainEventModel.id)).where(
                    DomainEventModel.command_id == plan.command_id
                )
            ) == 0
            assert session.get(ApplicationCommandModel, plan.command_id).status == "running"
    finally:
        engine.dispose()
