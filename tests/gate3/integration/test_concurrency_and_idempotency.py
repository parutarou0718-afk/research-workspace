from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from research_workspace.application.services.authorization import RawActorEnvelope
from research_workspace.application.services.command_dispatcher import (
    CommandDispatchError,
    RawCommandEnvelope,
    canonical_request_fingerprint,
)


def _envelope(key: str, payload: bytes = b'{"title":"A"}') -> RawCommandEnvelope:
    return RawCommandEnvelope(
        uuid4(),
        "paper.create",
        "1.0",
        key,
        "user",
        "local-user",
        UUID("43000000-0000-0000-0000-000000000001"),
        datetime(2026, 7, 17, tzinfo=timezone.utc),
        payload,
    )


def test_request_fingerprint_is_canonical_and_ignores_transport_fields() -> None:
    assert canonical_request_fingerprint(b'{"b":2,"a":1}') == canonical_request_fingerprint(
        b'{ "a": 1, "b": 2 }'
    )
    with pytest.raises(CommandDispatchError, match="COMMAND_VALIDATION_FAILED"):
        canonical_request_fingerprint(b"not-json")


def test_raw_command_rejects_disabled_actor_before_permission_snapshot() -> None:
    envelope = _envelope("key")
    for actor in ("agent", "task_executor"):
        disabled = RawCommandEnvelope(
            envelope.command_id,
            envelope.command_type,
            envelope.contract_version,
            envelope.idempotency_key,
            actor,
            envelope.actor_id,
            envelope.workspace_id,
            envelope.requested_at,
            envelope.request_payload,
        )
        with pytest.raises(CommandDispatchError, match="ACTOR_NOT_ENABLED"):
            disabled.validate_outer_actor()


def test_same_idempotency_key_with_different_fingerprint_is_conflict() -> None:
    from research_workspace.application.services.command_dispatcher import check_idempotency

    existing = type("Existing", (), {"request_fingerprint": "a" * 64, "status": "committed"})()
    assert check_idempotency(existing, "a" * 64) == "replay"
    with pytest.raises(CommandDispatchError, match="COMMAND_IDEMPOTENCY_CONFLICT"):
        check_idempotency(existing, "b" * 64)


def test_disabled_or_unauthorized_request_never_reaches_recovery() -> None:
    from research_workspace.application.services.command_dispatcher import CommandDispatcher

    class Coordinator:
        failed = []

        def find_command_by_idempotency(self, key):
            return None

        def mark_command_failed(self, command_id, error_code):
            self.failed.append((command_id, error_code))

    class Recovery:
        called = False

        def create(self, *args, **kwargs):
            self.called = True
            raise AssertionError("recovery must not run")

    class Token:
        cancelled = False

    coordinator = Coordinator()
    recovery = Recovery()
    dispatcher = CommandDispatcher(
        coordinator,
        recovery,
        database_path=__import__("pathlib").Path("workspace.db"),
        recovery_root=__import__("pathlib").Path("recovery"),
    )
    with pytest.raises(CommandDispatchError, match="COMMAND_PERMISSION_DENIED"):
        dispatcher.dispatch(
            _envelope("denied"),
            capability="paper.admin",
            entity_scopes=(),
            expected_versions=(),
            build_mutations=lambda plan: (),
            cancellation=Token(),
        )
    assert recovery.called is False


def test_ambiguous_commit_is_resolved_from_persisted_command_fact() -> None:
    from research_workspace.application.services.command_dispatcher import (
        CommandDispatcher,
        CommandResult,
        ExistingCommand,
    )

    envelope = _envelope("ambiguous")
    result = CommandResult(envelope.command_id, (uuid4(),), 1, False)

    class Coordinator:
        committed = False

        def find_command_by_idempotency(self, key):
            if self.committed:
                return ExistingCommand(
                    envelope.command_id,
                    canonical_request_fingerprint(envelope.request_payload),
                    "committed",
                    result,
                )
            return None

        def persist_command_envelope(self, plan):
            pass

        def commit_mutations(self, plan, mutations):
            self.committed = True
            raise OSError("acknowledgement lost")

        def mark_command_failed(self, command_id, error_code):
            raise AssertionError("a committed command must not be marked failed")

    class Recovery:
        def create(self, *args, **kwargs):
            return object()

    class Token:
        cancelled = False

    coordinator = Coordinator()
    dispatcher = CommandDispatcher(
        coordinator,
        Recovery(),
        database_path=__import__("pathlib").Path("workspace.db"),
        recovery_root=__import__("pathlib").Path("recovery"),
    )
    resolved = dispatcher.dispatch(
        envelope,
        capability="paper.write",
        entity_scopes=(("Paper", result.affected_entity_ids[0]),),
        expected_versions=(),
        build_mutations=lambda plan: (object(),),
        cancellation=Token(),
    )
    assert resolved.command_id == envelope.command_id
    assert resolved.affected_count == 1
