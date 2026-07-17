from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from research_workspace.application.queries.get_version_candidates import (
    VersionCandidateRecord,
    build_decision_review_bundle,
)


def _candidate(status="pending", row_version=1) -> VersionCandidateRecord:
    return VersionCandidateRecord(
        uuid4(), uuid4(), uuid4(), "detector", "1.0",
        "R1_SOURCE_CONTINUITY", "a" * 64, b'{"reason":"stable"}',
        b'{"score":1}', b'["43000000-0000-0000-0000-000000000001"]',
        status, None, row_version,
    )


def test_review_bundle_is_immutable_and_does_not_duplicate_paths_or_text() -> None:
    candidate = _candidate()
    bundle = build_decision_review_bundle(
        candidate, (uuid4(),), (uuid4(),)
    )
    assert bundle.candidate_id == candidate.candidate_id
    assert b"path" not in bundle.direction_rationale.lower()
    assert b"research_text" not in bundle.signals.lower()
    with pytest.raises(FrozenInstanceError):
        bundle.candidate_row_version = 2
    assert candidate.status == "pending"
    assert candidate.row_version == 1
