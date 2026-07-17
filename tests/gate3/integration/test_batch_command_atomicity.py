from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import rfc8785
from sqlalchemy import func, select

from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.services.command_dispatcher import (
    CommandPlan,
    CommandDispatchError,
    CommandDispatcher,
    CommandResult,
    DomainMutation,
    RawCommandEnvelope,
)
from research_workspace.infrastructure.db.models import (
    AuditChangeModel,
    DomainEventModel,
    PaperModel,
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


class _Coordinator:
    def __init__(self):
        self.envelopes = 0
        self.commits = 0
        self.failed = 0

    def find_command_by_idempotency(self, key):
        return None

    def persist_command_envelope(self, plan):
        self.envelopes += 1

    def commit_mutations(self, plan, mutations):
        self.commits += 1
        return CommandResult(
            plan.command_id, tuple(item.entity_id for item in mutations),
            len(mutations), False,
        )

    def mark_command_failed(self, command_id, error_code):
        self.failed += 1


class _Recovery:
    def __init__(self):
        self.calls = 0

    def create(self, plan, *, cancellation):
        self.calls += 1
        return object()


class _Cancellation:
    @property
    def is_cancelled(self):
        return False


def _envelope():
    identity = uuid4()
    return RawCommandEnvelope(
        identity, "batch.execute", "1.0", str(identity), "user", "tester",
        uuid4(), NOW, rfc8785.dumps({"batch": True}),
    )


def _mutation(entity_id):
    snapshot = rfc8785.dumps({
        "schema_version": "1.0", "entity_type": "Paper",
        "entity_id": str(entity_id), "row_version": 1,
        "fields": {"title": "A", "status": "active",
                   "current_version_id": None, "deleted_at": None},
    })
    return DomainMutation(
        "Paper", entity_id, "create", None, None, snapshot, ("title",),
        "paper.created", rfc8785.dumps({
            "entity_id": str(entity_id), "row_version": 1,
            "changed_fields": ["title"],
        }),
    )


def _plan(identities):
    command_id = uuid4()
    permission = rfc8785.dumps({
        "schema_version": "1.0",
        "actor_type": "user",
        "actor_id": "tester",
        "workspace_id": str(uuid4()),
        "capabilities": ["paper.write"],
        "scope_refs": [],
        "path_scopes": [],
        "network_allowed": False,
        "granted_at": "2026-07-17T00:00:00Z",
        "policy_version": "1.0",
        "authorization_decision_id": str(uuid4()),
    })
    return CommandPlan(
        command_id, "batch.execute", str(command_id), "a" * 64, permission,
        tuple(("Paper", identity) for identity in identities), (),
        rfc8785.dumps({"batch": True}), True,
    )


def _database_coordinator(tmp_path, repository_factory=SqlGate1WriteRepository):
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    coordinator = SqlWriteCoordinator(
        factory, repository_factory=repository_factory, data_directory=tmp_path
    )
    return engine, factory, coordinator


def _protect(coordinator, plan):
    coordinator.persist_command_envelope(plan)
    coordinator.persist_verified_recovery(
        plan,
        VerifiedRecoveryPoint(
            uuid4(), plan.command_id, 1, "b" * 64, 0, "c" * 64,
            rfc8785.dumps({
                "schema_revision": "0004_gate3_protected_crud",
                "created_at": "2026-07-17T00:00:00Z",
            }),
            "current",
        ),
    )


@pytest.mark.parametrize("count", [0, 101])
def test_invalid_batch_size_fails_before_recovery(count: int) -> None:
    coordinator, recovery = _Coordinator(), _Recovery()
    dispatcher = CommandDispatcher(
        coordinator, recovery, database_path=Path("workspace.db"),
        recovery_root=Path("recovery"),
    )
    scopes = tuple(("Paper", uuid4()) for _ in range(count))
    with pytest.raises(CommandDispatchError, match="COMMAND_VALIDATION_FAILED"):
        dispatcher.dispatch(
            _envelope(), capability="paper.write", entity_scopes=scopes,
            expected_versions=(), build_mutations=lambda plan: (),
            cancellation=_Cancellation(),
        )
    assert recovery.calls == coordinator.envelopes == coordinator.commits == 0


@pytest.mark.parametrize("count", [1, 100])
def test_accepted_batch_uses_one_recovery_and_one_commit(count: int) -> None:
    coordinator, recovery = _Coordinator(), _Recovery()
    dispatcher = CommandDispatcher(
        coordinator, recovery, database_path=Path("workspace.db"),
        recovery_root=Path("recovery"),
    )
    identities = tuple(uuid4() for _ in range(count))
    result = dispatcher.dispatch(
        _envelope(), capability="paper.write",
        entity_scopes=tuple(("Paper", item) for item in identities),
        expected_versions=(),
        build_mutations=lambda plan: tuple(_mutation(item) for item in identities),
        cancellation=_Cancellation(),
    )
    assert result.affected_count == count
    assert recovery.calls == coordinator.envelopes == coordinator.commits == 1


def test_batch_commits_one_indexed_audit_and_event_per_entity(tmp_path) -> None:
    identities = (uuid4(), uuid4())
    engine, factory, coordinator = _database_coordinator(tmp_path)
    try:
        plan = _plan(identities)
        _protect(coordinator, plan)
        result = coordinator.commit_mutations(
            plan, tuple(_mutation(identity) for identity in identities)
        )
        assert result.affected_entity_ids == identities
        with factory() as session:
            changes = session.scalars(
                select(AuditChangeModel)
                .where(AuditChangeModel.command_id == plan.command_id)
                .order_by(AuditChangeModel.change_index)
            ).all()
            assert [change.change_index for change in changes] == [0, 1]
            assert [change.entity_id for change in changes] == list(identities)
            assert session.scalar(
                select(func.count(DomainEventModel.id)).where(
                    DomainEventModel.command_id == plan.command_id
                )
            ) == 2
    finally:
        engine.dispose()


def test_one_item_failure_rolls_back_the_whole_batch(tmp_path) -> None:
    identities = (uuid4(), uuid4())

    class FailSecondRepository:
        def __init__(self, session):
            self._delegate = SqlGate1WriteRepository(session)
            self._count = 0

        def apply_mutation(self, mutation, command_id):
            self._count += 1
            self._delegate.apply_mutation(mutation, command_id)
            if self._count == 2:
                raise ValueError("COMMAND_VALIDATION_FAILED")

    engine, factory, coordinator = _database_coordinator(
        tmp_path, FailSecondRepository
    )
    try:
        plan = _plan(identities)
        _protect(coordinator, plan)
        with pytest.raises(WriteCoordinatorError, match="COMMAND_VALIDATION_FAILED"):
            coordinator.commit_mutations(
                plan, tuple(_mutation(identity) for identity in identities)
            )
        with factory() as session:
            assert session.scalar(
                select(func.count(PaperModel.id)).where(
                    PaperModel.id.in_(identities)
                )
            ) == 0
            assert session.scalar(
                select(func.count(AuditChangeModel.id)).where(
                    AuditChangeModel.command_id == plan.command_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(DomainEventModel.id)).where(
                    DomainEventModel.command_id == plan.command_id
                )
            ) == 0
    finally:
        engine.dispose()
