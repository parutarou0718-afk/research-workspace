from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import rfc8785

from research_workspace.application.services.command_dispatcher import (
    CommandDispatchError,
    CommandDispatcher,
    CommandResult,
    ExistingCommand,
    RawCommandEnvelope,
    canonical_request_fingerprint,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


class _Recovery:
    def create(self, plan, *, cancellation):
        return object()


class _Cancellation:
    is_cancelled = False


class _AmbiguousCoordinator:
    def __init__(self, *, committed: bool):
        self.committed = committed
        self.plan = None
        self.commit_calls = 0

    def find_command_by_idempotency(self, key):
        if self.plan is None or not self.committed:
            return None
        return ExistingCommand(
            self.plan.command_id, self.plan.request_fingerprint, "committed",
            CommandResult(self.plan.command_id, (self.plan.entity_scopes[0][1],), 1, False),
        )

    def persist_command_envelope(self, plan):
        self.plan = plan

    def commit_mutations(self, plan, mutations):
        self.commit_calls += 1
        raise RuntimeError("commit outcome unavailable")

    def mark_command_failed(self, command_id, error_code):
        pass


def _dispatch(coordinator):
    identity, entity_id = uuid4(), uuid4()
    payload = rfc8785.dumps({"value": 1})
    envelope = RawCommandEnvelope(
        identity, "paper.update", "1.0", str(identity), "user", "tester",
        uuid4(), NOW, payload,
    )
    dispatcher = CommandDispatcher(
        coordinator, _Recovery(), database_path=Path("workspace.db"),
        recovery_root=Path("recovery"),
    )
    return dispatcher.dispatch(
        envelope, capability="paper.write",
        entity_scopes=(("Paper", entity_id),), expected_versions=(),
        build_mutations=lambda plan: (object(),), cancellation=_Cancellation(),
    )


def test_unknown_commit_uses_command_facts_without_replaying() -> None:
    coordinator = _AmbiguousCoordinator(committed=True)
    result = _dispatch(coordinator)
    assert result.affected_count == 1
    assert coordinator.commit_calls == 1


def test_unknown_uncommitted_result_fails_without_blind_retry() -> None:
    coordinator = _AmbiguousCoordinator(committed=False)
    with pytest.raises(CommandDispatchError):
        _dispatch(coordinator)
    assert coordinator.commit_calls == 1


def test_request_fingerprint_is_canonical_for_fact_reconciliation() -> None:
    assert canonical_request_fingerprint(b'{"b":2,"a":1}') == (
        canonical_request_fingerprint(b'{"a":1,"b":2}')
    )
