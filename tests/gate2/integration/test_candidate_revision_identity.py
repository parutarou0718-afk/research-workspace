import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import rfc8785
from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import CandidateDetectionResult
from research_workspace.application.queries.get_version_candidates import GetVersionCandidates
from research_workspace.application.services.candidate_detection import (
    rule_config_fingerprint,
)
from research_workspace.domain.versioning import VersionRuleId
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    PaperVersionCandidateModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.write_coordinator import (
    SqlWriteCoordinator,
    WriteCoordinatorError,
)


def _snapshots(database, now):
    operation_id = uuid4()
    earlier_id, later_id = uuid4(), uuid4()
    with database.factory.begin() as session:
        session.add(
            BackgroundOperationModel(
                id=operation_id, operation_type="snapshot_import", status="completed",
                work_plan_fingerprint="1" * 64, permission_context_json="{}",
                result_summary_json="{}", error_code=None, created_at=now,
                started_at=now, finished_at=now, cancel_requested_at=None,
            )
        )
        for snapshot_id, digest in ((earlier_id, "a" * 64), (later_id, "b" * 64)):
            session.add(
                SourceSnapshotModel(
                    id=snapshot_id, sha256=digest, size_bytes=3,
                    mime_type="application/pdf",
                    storage_relative_path=f"sources/sha256/{digest[:2]}/{digest}/content.pdf",
                    created_at=now, created_by_operation_id=operation_id,
                )
            )
    return earlier_id, later_id


def _result(earlier_id, later_id, *, detector_version="1.0", config=None):
    return CandidateDetectionResult(
        earlier_id,
        later_id,
        "paper-version-detector",
        detector_version,
        VersionRuleId.R1_SOURCE_CONTINUITY,
        rule_config_fingerprint(config or {}),
        rfc8785.dumps({"basis": "source_continuity"}),
        rfc8785.dumps(
            {
                "matched_rules": ["R1_SOURCE_CONTINUITY"],
                "normalized_filename_before": "paper draft",
                "normalized_filename_after": "paper rev2",
            }
        ),
        (uuid4(), uuid4()),
    )


def test_five_part_identity_replay_and_revision_coexistence(monitoring_database) -> None:
    now = datetime(2026, 7, 17, 20, tzinfo=timezone.utc)
    earlier_id, later_id = _snapshots(monitoring_database, now)
    coordinator = SqlWriteCoordinator(monitoring_database.factory)
    first = _result(earlier_id, later_id)
    candidate_id = coordinator.register_version_candidate(
        uuid4(), uuid4(), first, now
    )
    replay_id = coordinator.register_version_candidate(
        uuid4(), uuid4(), first, now
    )
    revised_id = coordinator.register_version_candidate(
        uuid4(), uuid4(),
        _result(earlier_id, later_id, detector_version="1.1"), now,
    )
    configured_id = coordinator.register_version_candidate(
        uuid4(), uuid4(),
        _result(earlier_id, later_id, config={"candidate_window": 4}), now,
    )
    assert replay_id == candidate_id
    assert len({candidate_id, revised_id, configured_id}) == 3
    with monitoring_database.factory() as session:
        assert session.scalar(
            select(func.count()).select_from(PaperVersionCandidateModel)
        ) == 3
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 3


def test_identity_conflict_never_overwrites_immutable_evidence(
    monitoring_database,
) -> None:
    now = datetime(2026, 7, 17, 20, tzinfo=timezone.utc)
    earlier_id, later_id = _snapshots(monitoring_database, now)
    coordinator = SqlWriteCoordinator(monitoring_database.factory)
    original = _result(earlier_id, later_id)
    candidate_id = coordinator.register_version_candidate(
        uuid4(), uuid4(), original, now
    )
    conflicting = CandidateDetectionResult(
        original.earlier_snapshot_id, original.later_snapshot_id,
        original.detector_id, original.detector_version, original.rule_id,
        original.rule_config_fingerprint, original.direction_rationale,
        rfc8785.dumps({"matched_rules": ["R2_REPLACE_CONTINUITY"]}),
        original.input_observation_ids,
    )
    with pytest.raises(WriteCoordinatorError, match="CANDIDATE_IDENTITY_CONFLICT"):
        coordinator.register_version_candidate(uuid4(), uuid4(), conflicting, now)
    with monitoring_database.factory() as session:
        stored = session.get(PaperVersionCandidateModel, candidate_id)
        assert stored.signals_json == original.signals.decode()


def test_query_returns_immutable_evidence_and_explicit_supersession(
    monitoring_database,
) -> None:
    now = datetime(2026, 7, 17, 20, tzinfo=timezone.utc)
    earlier_id, later_id = _snapshots(monitoring_database, now)
    coordinator = SqlWriteCoordinator(monitoring_database.factory)
    old_id = coordinator.register_version_candidate(
        uuid4(), uuid4(), _result(earlier_id, later_id), now
    )
    new_id = coordinator.register_version_candidate(
        uuid4(), uuid4(), _result(
            earlier_id, later_id, detector_version="1.1"
        ), now,
    )
    coordinator.supersede_version_candidate(old_id, new_id, uuid4(), now)
    records = GetVersionCandidates(monitoring_database.factory).execute()
    assert [record.candidate_id for record in records] == [old_id, new_id]
    assert records[0].status == "superseded"
    assert records[0].superseded_by_candidate_id == new_id
    assert isinstance(records[0].signals_json, bytes)
    assert json.loads(records[0].signals_json)["matched_rules"] == [
        "R1_SOURCE_CONTINUITY"
    ]
    with pytest.raises((AttributeError, TypeError)):
        records[0].signals_json = b"{}"
