from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootSeed,
    RawFileEventDTO,
)
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG, RawFileEventType
from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    PendingPathCheckModel,
    RawEventPendingLinkModel,
    RawFileEventModel,
    SourceObservationModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


def _root(database, root: Path):
    now = datetime(2026, 7, 17, 9, tzinfo=timezone.utc)
    root.mkdir()
    root_id = uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id,
            root,
            normalize_path_text(root),
            normalized_path_hash(root),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(),
            now,
        ),
        (),
    )
    return coordinator, root_id


def _event(root_id, path: Path, kind: RawFileEventType, when: datetime, key: str):
    return RawFileEventDTO(
        uuid4(),
        root_id,
        "watchdog",
        kind,
        path,
        None,
        when,
        when,
        None,
        None,
        key,
    )


def test_duplicate_and_replayed_events_are_append_idempotent(monitoring_database) -> None:
    coordinator, root_id = _root(
        monitoring_database, monitoring_database.workspace.parent / "external"
    )
    path = monitoring_database.workspace.parent / "external" / "paper.pdf"
    when = datetime(2026, 7, 17, 9, 1, tzinfo=timezone.utc)
    event = _event(root_id, path, RawFileEventType.CREATED, when, "a" * 64)

    first = coordinator.ingest_raw_file_event(event)
    replay = coordinator.ingest_raw_file_event(event)

    assert replay == first
    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 1
        assert session.scalar(select(func.count()).select_from(PendingPathCheckModel)) == 1
        assert session.scalar(select(func.count()).select_from(RawEventPendingLinkModel)) == 1
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 0
        assert session.scalar(select(func.count()).select_from(SourceObservationModel)) == 0

def test_move_is_two_path_checks_but_never_mutates_observation_or_domain_event(
    monitoring_database,
) -> None:
    coordinator, root_id = _root(
        monitoring_database, monitoring_database.workspace.parent / "external"
    )
    source = monitoring_database.workspace.parent / "external" / "draft.docx"
    destination = monitoring_database.workspace.parent / "external" / "final.docx"
    when = datetime(2026, 7, 17, 9, 2, tzinfo=timezone.utc)
    event = RawFileEventDTO(
        uuid4(),
        root_id,
        "watchdog",
        RawFileEventType.MOVED,
        source,
        destination,
        when,
        when,
        None,
        "rename",
        "b" * 64,
    )

    pending_ids = coordinator.ingest_raw_file_event(event)

    assert len(pending_ids) == 2
    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 1
        assert session.scalar(select(func.count()).select_from(PendingPathCheckModel)) == 2
        assert session.scalar(select(func.count()).select_from(RawEventPendingLinkModel)) == 2
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 0
        assert session.scalar(select(func.count()).select_from(SourceObservationModel)) == 0
