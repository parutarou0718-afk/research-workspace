from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootSeed,
    RawFileEventDTO,
)
from research_workspace.application.services.import_orchestrator import ImportOrchestrator
from research_workspace.domain.capabilities import PathScope, PermissionContext
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG, RawFileEventType
from research_workspace.infrastructure.db.models import (
    PaperVersionCandidateModel,
    PendingPathCheckModel,
    SourceObservationEventModel,
    SourceObservationModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore


def test_verified_same_hash_move_preserves_provenance_without_new_snapshot(
    monitoring_database,
) -> None:
    external = monitoring_database.workspace.parent / "external"
    external.mkdir()
    source = external / "draft.docx"
    source.write_bytes(b"same immutable bytes")
    now = datetime(2026, 7, 17, 13, tzinfo=timezone.utc)
    root_id = uuid4()
    coordinator = SqlWriteCoordinator(monitoring_database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id,
            external,
            normalize_path_text(external),
            normalized_path_hash(external),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(),
            now,
        ),
        (),
    )
    context = PermissionContext(
        "1.0",
        "system",
        "source-observer",
        coordinator.workspace_id(),
        ("source.snapshot_import.request",),
        (),
        (
            PathScope(
                "import_source",
                normalized_path_hash(external),
                root_id,
                "copy",
                True,
            ),
        ),
        False,
        now,
        "1.0",
        uuid4(),
    )
    orchestrator = ImportOrchestrator(
        monitoring_database.workspace, SnapshotStore(monitoring_database.workspace), coordinator
    )
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(), root_id, "watchdog", RawFileEventType.CREATED, source, None,
            now, now, None, None, "8" * 64,
        )
    )
    with monitoring_database.factory() as session:
        source_pending = session.scalar(select(PendingPathCheckModel.id))
    original = orchestrator.execute_pending(
        source_pending, context, now=now + timedelta(seconds=2)
    )

    destination = external / "final.docx"
    source.rename(destination)
    moved_at = now + timedelta(minutes=1)
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(), root_id, "watchdog", RawFileEventType.MOVED, source, destination,
            moved_at, moved_at, None, "move-1", "9" * 64,
        )
    )
    with monitoring_database.factory() as session:
        destination_pending = session.scalar(
            select(PendingPathCheckModel.id).where(
                PendingPathCheckModel.normalized_path == normalize_path_text(destination)
            )
        )
    relocated = orchestrator.execute_pending(
        destination_pending, context, now=moved_at + timedelta(seconds=2)
    )

    assert original.snapshot_id == relocated.snapshot_id
    assert relocated.state == "duplicate_content"
    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceSnapshotModel)) == 1
        assert session.scalar(select(func.count()).select_from(PaperVersionCandidateModel)) == 0
        old = session.scalar(
            select(SourceObservationModel).where(
                SourceObservationModel.normalized_path == normalize_path_text(source)
            )
        )
        new = session.scalar(
            select(SourceObservationModel).where(
                SourceObservationModel.normalized_path == normalize_path_text(destination)
            )
        )
        assert old.availability_status == "missing"
        assert old.current_snapshot_id == new.current_snapshot_id == original.snapshot_id
        assert new.monitoring_root_id == root_id
        provenance = session.scalar(
            select(SourceObservationEventModel).where(
                SourceObservationEventModel.source_observation_id == new.id,
                SourceObservationEventModel.event_type == "moved",
            )
        )
        assert provenance is not None
        assert provenance.path_before_hash == normalized_path_hash(source)
        assert provenance.path_after_hash == normalized_path_hash(destination)
