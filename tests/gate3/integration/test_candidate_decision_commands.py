from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select

from research_workspace.application.commands.review_relation import (
    CandidateDecisionError,
    confirm_candidate,
    reconsider_candidate,
    reject_candidate,
)
from research_workspace.application.queries.get_version_candidates import (
    VersionCandidateRecord,
)
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    BackgroundOperationModel,
    PaperVersionCandidateModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository
from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _candidate(status="pending", row_version=1) -> VersionCandidateRecord:
    return VersionCandidateRecord(
        uuid4(), uuid4(), uuid4(), "detector", "1.0",
        "R1_SOURCE_CONTINUITY", "a" * 64, b"{}", b"{}", b"[]",
        status, None, row_version,
    )


def test_reject_and_reconsider_are_candidate_only_mutations() -> None:
    candidate = _candidate()
    rejected = reject_candidate(candidate, uuid4(), NOW)
    assert rejected.entity_type == "PaperVersionCandidate"
    assert rejected.event_type == "paper_version_candidate.rejected"
    reconsidered_record = _candidate("rejected", 2)
    reconsidered = reconsider_candidate(reconsidered_record, uuid4(), NOW)
    assert reconsidered.operation == "reconsider"
    assert b'"status":"pending"' in reconsidered.after_snapshot
    assert b"EntityRelation" not in reconsidered.after_snapshot


@pytest.mark.parametrize("status", ["confirmed", "superseded"])
def test_only_pending_can_be_decided(status: str) -> None:
    with pytest.raises(CandidateDecisionError, match="CANDIDATE_STATE_CHANGED"):
        reject_candidate(_candidate(status), uuid4(), NOW)


def test_confirmation_creates_or_reuses_memberships_without_silent_edit() -> None:
    candidate = _candidate()
    paper_id = uuid4()
    result = confirm_candidate(
        candidate, uuid4(), paper_id, "Earlier", "Later", (), (), uuid4(),
        uuid4(), uuid4(), NOW,
    )
    assert result[-1].event_type == "paper_version_candidate.confirmed"
    assert [item.entity_type for item in result].count("PaperVersion") == 2
    assert [item.entity_type for item in result].count("EntityRelation") == 1
    assert b'"status":"confirmed"' in result[-1].after_snapshot


def test_candidate_decision_repository_checks_row_version_and_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    candidate = _candidate()
    operation_id = uuid4()
    try:
        with factory.begin() as session:
            adoption = session.scalar(select(ApplicationCommandModel).where(
                ApplicationCommandModel.command_type
                == "system.migration_adopt_v01"
            ))
            session.add(BackgroundOperationModel(
                id=operation_id, operation_type="version_candidate_detect",
                status="completed", work_plan_fingerprint="a" * 64,
                permission_context_json="{}", result_summary_json="{}",
                error_code=None, created_at=NOW, started_at=NOW,
                finished_at=NOW, cancel_requested_at=None,
            ))
            session.flush()
            for snapshot_id, digest in (
                (candidate.earlier_snapshot_id, "b" * 64),
                (candidate.later_snapshot_id, "c" * 64),
            ):
                session.add(SourceSnapshotModel(
                    id=snapshot_id, sha256=digest, size_bytes=1,
                    mime_type="application/pdf",
                    storage_relative_path=f"sources/{snapshot_id}.pdf",
                    created_at=NOW, created_by_operation_id=operation_id,
                ))
            session.flush()
            session.add(PaperVersionCandidateModel(
                id=candidate.candidate_id,
                earlier_snapshot_id=candidate.earlier_snapshot_id,
                later_snapshot_id=candidate.later_snapshot_id,
                detector_id=candidate.detector_id,
                detector_version=candidate.detector_version,
                rule_id=candidate.rule_id,
                rule_config_fingerprint=candidate.rule_config_fingerprint,
                direction_rationale_json="{}", signals_json="{}",
                input_observation_ids_json="[]", status="pending",
                superseded_by_candidate_id=None, row_version=1, created_at=NOW,
                decided_at=None, decided_by_command_id=None,
            ))
        with factory.begin() as session:
            SqlGate1WriteRepository(session).apply_mutation(
                reject_candidate(candidate, adoption.id, NOW), adoption.id
            )
        with factory() as session:
            row = session.get(PaperVersionCandidateModel, candidate.candidate_id)
            assert row.status == "rejected"
            assert row.row_version == 2
            assert row.decided_by_command_id == adoption.id
    finally:
        engine.dispose()
