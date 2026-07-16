from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from research_workspace.application.dto.import_dto import SnapshotRegistrationDTO
from research_workspace.application.ports import filesystem, operation_runner, write_coordinator
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator, WriteCoordinatorError


def registration() -> SnapshotRegistrationDTO:
    return SnapshotRegistrationDTO(
        operation_id=UUID("40000000-0000-0000-0000-000000000001"),
        batch_id=UUID("40000000-0000-0000-0000-000000000002"),
        import_item_id=UUID("40000000-0000-0000-0000-000000000003"),
        source_observation_id=UUID("40000000-0000-0000-0000-000000000004"),
        snapshot_id=UUID("40000000-0000-0000-0000-000000000005"),
        source_path=Path("C:/Research/Paper.pdf"),
        original_filename="Paper.pdf",
        sha256="c" * 64,
        size_bytes=123,
        mime_type="application/pdf",
        storage_relative_path="sources/sha256/cc/content.pdf",
        duplicate_content=False,
    )


def _migrated_factory(tmp_path):
    from research_workspace import bootstrap

    database = tmp_path / "workspace.db"
    bootstrap._run_migrations(database)
    engine = create_engine_for_path(database)
    return engine, session_factory(engine)


def _seed_registration_prerequisites(factory, dto) -> None:
    from research_workspace.infrastructure.db.models import ImportBatchModel, ImportItemModel, SourceObservationModel

    with factory.begin() as session:
        session.add(BackgroundOperationModel(
            id=dto.operation_id, operation_type="snapshot_import", status="running",
            work_plan_fingerprint="d" * 64, permission_context_json="{}",
            result_summary_json=None, error_code=None, created_at="2026-07-16T00:00:00Z",
            started_at="2026-07-16T00:00:00Z", finished_at=None, cancel_requested_at=None,
        ))
        session.add(ImportBatchModel(
            id=dto.batch_id, operation_id=dto.operation_id, status="importing", selected_count=1,
            estimated_total_bytes=dto.size_bytes, estimated_added_bytes=dto.size_bytes,
            estimate_is_exact=True, disclosure_accepted_at="2026-07-16T00:00:00Z",
            created_at="2026-07-16T00:00:00Z", finished_at=None,
        ))
        session.add(SourceObservationModel(
            id=dto.source_observation_id, original_path=str(dto.source_path),
            normalized_path=str(dto.source_path).casefold(), normalized_path_hash="e" * 64,
            original_filename=dto.original_filename, current_snapshot_id=None,
            availability_status="available", baseline_only=False, size_bytes=dto.size_bytes,
            modified_at=None, file_id_hint=None, volume_serial_hint=None,
            first_seen_at="2026-07-16T00:00:00Z", last_seen_at="2026-07-16T00:00:00Z",
            missing_at=None, row_version=1,
        ))
        session.flush()
        session.add(ImportItemModel(
            id=dto.import_item_id, batch_id=dto.batch_id,
            source_observation_id=dto.source_observation_id, snapshot_id=None,
            parse_artifact_id=None, state="pending", parse_status="not_requested",
            error_code=None, created_at="2026-07-16T00:00:00Z", finished_at=None,
        ))


def test_worker_facing_ports_have_no_framework_or_unbounded_task_authority() -> None:
    for module in (filesystem, operation_runner, write_coordinator):
        source = inspect.getsource(module)
        assert "sqlalchemy" not in source.lower()
        assert "PySide6" not in source
        assert "QWidget" not in source
        assert "TaskContract" not in source
        assert "TaskExecutor" not in source
    filesystem_source = inspect.getsource(filesystem.FilesystemPort)
    assert "allowed_scope: PathScope" in filesystem_source
    assert set(filesystem.FilesystemPort.__dict__) >= {
        "validate_source", "stage_stable_copy", "promote_snapshot"
    }


def test_write_coordinator_commits_database_fact_and_v2_event_together(tmp_path) -> None:
    engine, factory = _migrated_factory(tmp_path)
    dto = registration()
    _seed_registration_prerequisites(factory, dto)
    result = SqlWriteCoordinator(factory).register_import(dto)
    try:
        with factory() as session:
            assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 1
            event = session.scalar(select(DomainEventModel))
            assert event.schema_version == "2.0"
            assert event.event_type == "source.snapshot_imported"
            assert event.operation_id == dto.operation_id
            assert result.snapshot_id == dto.snapshot_id
    finally:
        engine.dispose()


def test_write_coordinator_rolls_back_fact_when_repository_fails(tmp_path) -> None:
    engine, factory = _migrated_factory(tmp_path)

    class FailingRepository:
        def __init__(self, session):
            self.session = session

        def register_import(self, dto):
            self.session.add(BackgroundOperationModel(
                id=dto.operation_id, operation_type="snapshot_import", status="running",
                work_plan_fingerprint="f" * 64, permission_context_json="{}",
                result_summary_json=None, error_code=None, created_at="2026-07-16T00:00:00Z",
                started_at=None, finished_at=None, cancel_requested_at=None,
            ))
            self.session.flush()
            raise RuntimeError("injected repository failure")

    with pytest.raises(RuntimeError, match="injected repository failure"):
        SqlWriteCoordinator(factory, repository_factory=FailingRepository).register_import(registration())
    try:
        with factory() as session:
            assert session.scalar(select(func.count(BackgroundOperationModel.id))) == 0
            assert session.scalar(select(func.count(DomainEventModel.id))) == 0
    finally:
        engine.dispose()


def test_write_coordinator_only_maps_explicit_sqlite_busy_as_retryable(tmp_path) -> None:
    engine, factory = _migrated_factory(tmp_path)

    class OperationalFailureRepository:
        def __init__(self, session):
            self.session = session

        def register_import(self, dto):
            original = sqlite3.OperationalError("no such table: missing")
            original.sqlite_errorcode = sqlite3.SQLITE_ERROR
            raise OperationalError("SELECT * FROM missing", {}, original)

    class BusyRepository:
        def __init__(self, session):
            self.session = session

        def register_import(self, dto):
            original = sqlite3.OperationalError("database is locked")
            original.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise OperationalError("INSERT INTO source_snapshots", {}, original)

    with pytest.raises(WriteCoordinatorError) as raised:
        SqlWriteCoordinator(
            factory, repository_factory=OperationalFailureRepository
        ).register_import(registration())
    try:
        assert raised.value.error_code == "DATABASE_OPERATION_FAILED"
        with pytest.raises(WriteCoordinatorError) as busy:
            SqlWriteCoordinator(
                factory, repository_factory=BusyRepository
            ).register_import(registration())
        assert busy.value.error_code == "SQLITE_BUSY"
    finally:
        engine.dispose()
