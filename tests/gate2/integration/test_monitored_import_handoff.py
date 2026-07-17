import json
from datetime import datetime, timezone
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
    DomainEventModel,
    PaperVersionCandidateModel,
    ParseArtifactModel,
    PendingPathCheckModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore


def _runtime(database):
    external = database.workspace.parent / "external"
    external.mkdir()
    root_id = uuid4()
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    coordinator = SqlWriteCoordinator(database.factory)
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
    return (
        external,
        root_id,
        now,
        coordinator,
        context,
        ImportOrchestrator(database.workspace, SnapshotStore(database.workspace), coordinator),
    )


def _enqueue(database, coordinator, root_id, source, now, key):
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(),
            root_id,
            "watchdog",
            RawFileEventType.MODIFIED,
            source,
            None,
            now,
            now,
            None,
            None,
            key,
        )
    )
    with database.factory() as session:
        return session.scalar(
            select(PendingPathCheckModel.id).where(
                PendingPathCheckModel.normalized_path == normalize_path_text(source)
            )
        )


def test_changed_content_uses_gate1_immutable_import_without_parse_or_candidate(
    monitoring_database,
) -> None:
    external, root_id, now, coordinator, context, orchestrator = _runtime(
        monitoring_database
    )
    source = external / "paper.pdf"
    source.write_bytes(b"revision one")
    pending_id = _enqueue(
        monitoring_database, coordinator, root_id, source, now, "6" * 64
    )

    first = orchestrator.execute_pending(
        pending_id, context, now=now.replace(second=2)
    )
    source.write_bytes(b"revision two with changed content")
    later = now.replace(minute=1)
    _enqueue(monitoring_database, coordinator, root_id, source, later, "7" * 64)
    second = orchestrator.execute_pending(
        pending_id, context, now=later.replace(second=2)
    )

    assert first.state == "imported"
    assert second.state == "imported"
    with monitoring_database.factory() as session:
        pending = session.get(PendingPathCheckModel, pending_id)
        assert pending.stability_attempt_count == 1
        assert session.scalar(select(func.count()).select_from(SourceSnapshotModel)) == 2
        assert session.scalar(select(func.count()).select_from(ParseArtifactModel)) == 0
        assert session.scalar(select(func.count()).select_from(PaperVersionCandidateModel)) == 0
        events = session.scalars(select(DomainEventModel)).all()
        assert len(events) == 2
        assert all(
            "external" not in event.payload_json
            and str(source) not in event.payload_json
            and set(json.loads(event.payload_json))
            == {
                "import_item_id",
                "sha256",
                "size_bytes",
                "snapshot_id",
                "source_observation_id",
            }
            for event in events
        )
    assert not tuple((monitoring_database.workspace / "staging").rglob("*.partial"))
