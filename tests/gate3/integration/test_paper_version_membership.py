from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import rfc8785
from sqlalchemy import select

from research_workspace.application.services.relation_graph import (
    ParseContextRef,
    RetractionDependencies,
    VersionGraphError,
    change_version_context,
    create_version_membership,
    resolve_membership,
    retract_version_membership,
)
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint
from research_workspace.application.services.command_dispatcher import CommandPlan
from research_workspace.domain.versioning import PaperVersionRecord
from research_workspace.infrastructure.db.models import (
    ApplicationCommandModel,
    BackgroundOperationModel,
    PaperModel,
    PaperVersionModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository
from research_workspace.infrastructure.db.session import (
    create_engine_for_path,
    session_factory,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _version(**changes) -> PaperVersionRecord:
    values = {
        "id": uuid4(), "paper_id": uuid4(), "source_snapshot_id": uuid4(),
        "context_parse_artifact_id": None, "version_label": "Rev 2",
        "normalized_version_label": "rev 2", "lifecycle_state": "active",
        "row_version": 1, "created_at": NOW, "confirmed_by_command_id": uuid4(),
        "updated_at": NOW, "updated_by_command_id": uuid4(),
        "retracted_at": None, "retracted_by_command_id": None,
    }
    values.update(changes)
    return PaperVersionRecord(**values)


def test_membership_identity_uses_paper_and_snapshot_and_keeps_context_optional() -> None:
    paper_id, snapshot_id = uuid4(), uuid4()
    mutation = create_version_membership(
        uuid4(), uuid4(), paper_id, snapshot_id, "  Rev 2 ", None, NOW
    )
    assert mutation.entity_type == "PaperVersion"
    assert b'"normalized_version_label":"rev 2"' in mutation.after_snapshot
    assert b'"context_parse_artifact_id":null' in mutation.after_snapshot


def test_membership_reuses_only_same_paper_without_silent_edits() -> None:
    existing = _version(version_label="Original", normalized_version_label="original")
    reused, warnings = resolve_membership(
        (existing,), existing.paper_id, existing.source_snapshot_id
    )
    assert reused is existing
    assert reused.version_label == "Original"
    assert warnings == ()
    reused, warnings = resolve_membership(
        (existing,), uuid4(), existing.source_snapshot_id
    )
    assert reused is None
    assert warnings == ("SNAPSHOT_ALREADY_USED_BY_ANOTHER_PAPER",)


def test_context_parse_must_belong_to_snapshot_and_changes_only_context() -> None:
    version = _version()
    wrong = ParseContextRef(uuid4(), uuid4(), "succeeded")
    with pytest.raises(VersionGraphError, match="INVALID_VERSION_ASSIGNMENT"):
        change_version_context(version, uuid4(), wrong, NOW)
    correct = ParseContextRef(uuid4(), version.source_snapshot_id, "succeeded")
    mutation = change_version_context(version, uuid4(), correct, NOW)
    assert mutation.changed_fields == ("context_parse_artifact_id",)
    assert b"evidence" not in mutation.after_snapshot.lower()


def test_retraction_is_blocked_by_current_submission_or_active_edges() -> None:
    version = _version()
    for dependencies in (
        RetractionDependencies(is_current=True),
        RetractionDependencies(active_submissions=1),
        RetractionDependencies(active_edges=1),
    ):
        with pytest.raises(
            VersionGraphError, match="VERSION_RETRACTION_DEPENDENCY_CONFLICT"
        ):
            retract_version_membership(
                version, uuid4(), NOW, dependencies
            )
    mutation = retract_version_membership(
        version, uuid4(), NOW, RetractionDependencies()
    )
    assert mutation.operation == "retract"
    assert b'"lifecycle_state":"retracted"' in mutation.after_snapshot


def test_membership_is_registered_with_command_identity_in_one_transaction(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workspace.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0004")
    engine = create_engine_for_path(path)
    factory = session_factory(engine)
    coordinator = SqlWriteCoordinator(
        factory, repository_factory=SqlGate1WriteRepository, data_directory=tmp_path
    )
    paper_id, snapshot_id, version_id, command_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    operation_id = uuid4()
    try:
        with factory.begin() as session:
            adoption = session.scalar(
                select(ApplicationCommandModel).where(
                    ApplicationCommandModel.command_type
                    == "system.migration_adopt_v01"
                )
            )
            session.add(
                BackgroundOperationModel(
                    id=operation_id, operation_type="snapshot_import",
                    status="completed", work_plan_fingerprint="a" * 64,
                    permission_context_json="{}", result_summary_json="{}",
                    error_code=None, created_at=NOW, started_at=NOW,
                    finished_at=NOW, cancel_requested_at=None,
                )
            )
            session.add(
                SourceSnapshotModel(
                    id=snapshot_id, sha256="b" * 64, size_bytes=1,
                    mime_type="application/pdf",
                    storage_relative_path=f"sources/{snapshot_id}.pdf",
                    created_at=NOW, created_by_operation_id=operation_id,
                )
            )
            session.add(
                PaperModel(
                    id=paper_id, title="Paper", status="active",
                    current_version_id=None, created_at=NOW, updated_at=NOW,
                    deleted_at=None, row_version=1,
                    created_by_command_id=adoption.id,
                    updated_by_command_id=adoption.id,
                    deleted_by_command_id=None,
                )
            )
        permission = rfc8785.dumps({
            "actor_type": "user", "actor_id": "tester",
            "workspace_id": "43000000-0000-0000-0000-000000000001",
        })
        plan = CommandPlan(
            command_id, "paper_version.confirm", "version-create",
            ("%064x" % command_id.int)[-64:], permission,
            (("PaperVersion", version_id),), (), b"{}", True,
        )
        coordinator.persist_command_envelope(plan)
        coordinator.persist_verified_recovery(
            plan,
            VerifiedRecoveryPoint(
                uuid4(), command_id, coordinator.next_recovery_generation(),
                "c" * 64, 1, "d" * 64,
                rfc8785.dumps({
                    "schema_revision": "0004_gate3_protected_crud",
                    "created_at": "2026-07-17T00:00:00Z",
                }), "current",
            ),
        )
        coordinator.commit_mutations(
            plan,
            (create_version_membership(
                command_id, version_id, paper_id, snapshot_id, "Rev 1", None, NOW
            ),),
        )
        with factory() as session:
            row = session.get(PaperVersionModel, version_id)
            assert row.confirmed_by_command_id == command_id
            assert row.normalized_version_label == "rev 1"
    finally:
        engine.dispose()
