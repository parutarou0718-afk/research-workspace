from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import rfc8785

from research_workspace.application.services.authorization import (
    AuthorizationRequest,
    RawActorEnvelope,
    authorize_request,
)
from research_workspace.application.services.command_dispatcher import (
    CommandDispatchError,
    CommandDispatcher,
    RawCommandEnvelope,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


class _Forbidden:
    def __getattr__(self, name):
        raise AssertionError(f"must reject before {name}")


@pytest.mark.parametrize("actor", ["agent", "task_executor", "unknown"])
def test_forged_actor_is_rejected_before_recovery_or_persistence(actor: str) -> None:
    dispatcher = CommandDispatcher(
        _Forbidden(), _Forbidden(), database_path=Path("workspace.db"),
        recovery_root=Path("recovery"),
    )
    envelope = RawCommandEnvelope(
        uuid4(), "paper.update", "1.0", "key", actor, "forged", uuid4(),
        NOW, rfc8785.dumps({}),
    )
    with pytest.raises(CommandDispatchError):
        dispatcher.dispatch(
            envelope, capability="paper.write",
            entity_scopes=(("Paper", uuid4()),), expected_versions=(),
            build_mutations=lambda plan: (), cancellation=_Forbidden(),
        )


def test_historical_permission_snapshot_cannot_be_replayed_as_request() -> None:
    request = AuthorizationRequest(
        RawActorEnvelope("user", "tester"), uuid4(), "paper.write",
        ("Paper:value",), (), NOW, "1.0", uuid4(),
    )
    context = authorize_request(request)
    with pytest.raises((AttributeError, TypeError)):
        authorize_request(context)  # type: ignore[arg-type]
    assert context.network_allowed is False
