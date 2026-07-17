from datetime import datetime, timezone
from uuid import uuid4

import pytest

from research_workspace.application.commands.review_relation import (
    CandidateDecisionError,
    RelationLifecycleRecord,
    retract_relation,
    supersede_relation,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _relation(state="active", version=1) -> RelationLifecycleRecord:
    return RelationLifecycleRecord(
        uuid4(), "version_successor_of", "PaperVersion", uuid4(),
        "PaperVersion", uuid4(), state, version,
    )


def test_active_relation_can_be_retracted_but_never_physically_deleted() -> None:
    mutation = retract_relation(_relation(), uuid4(), NOW)
    assert mutation.operation == "retract"
    assert mutation.after_snapshot is not None
    assert b'"lifecycle_state":"retracted"' in mutation.after_snapshot


def test_supersession_requires_distinct_active_compatible_relation() -> None:
    old, replacement = _relation(), _relation()
    mutation = supersede_relation(old, replacement, uuid4(), NOW)
    assert mutation.operation == "retract"
    assert b'"lifecycle_state":"superseded"' in mutation.after_snapshot
    with pytest.raises(CandidateDecisionError):
        supersede_relation(old, old, uuid4(), NOW)
