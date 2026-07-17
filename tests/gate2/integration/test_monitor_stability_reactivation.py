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
    DomainEventModel,
    ImportItemModel,
    PendingPathCheckModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    SourceFailure,
    normalize_path_text,
    normalized_path_hash,
)


class _AlwaysBusySnapshots:
    def materialize(self, source: Path, import_item_id):
        raise SourceFailure("SOURCE_BUSY")


def _setup(database):
    external = database.workspace.parent / "external"
    external.mkdir()
    source = external / "changing.pdf"
    source.write_bytes(b"not yet stable")
    base = datetime(2026, 7, 17, 11, tzinfo=timezone.utc)
    root_id = uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id,
            external,
            normalize_path_text(external),
            normalized_path_hash(external),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(),
            base,
        ),
        (),
    )
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(),
            root_id,
            "watchdog",
            RawFileEventType.MODIFIED,
            source,
            None,
            base,
            base,
            None,
            None,
            "4" * 64,
        )
    )
    with database.factory() as session:
        pending_id = session.scalar(select(PendingPathCheckModel.id))
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
        base,
        "1.0",
        uuid4(),
    )
    return coordinator, source, pending_id, context, base


def test_busy_source_retries_five_times_then_becomes_recoverably_unstable(
    monitoring_database,
) -> None:
    coordinator, _, pending_id, context, base = _setup(monitoring_database)
    orchestrator = ImportOrchestrator(
        monitoring_database.workspace, _AlwaysBusySnapshots(), coordinator
    )
    due = base + timedelta(seconds=2)
    expected_backoff = (2, 5, 15, 30, 60)

    for attempt, delay in enumerate(expected_backoff, start=1):
        result = orchestrator.execute_pending(pending_id, context, now=due)
        assert result.error_code == "SOURCE_BUSY"
        with monitoring_database.factory() as session:
            pending = session.get(PendingPathCheckModel, pending_id)
            assert pending.stability_attempt_count == attempt
            assert pending.next_check_at == due + timedelta(seconds=delay)
            expected = "unstable_source" if attempt == 5 else "waiting_for_stability"
            assert pending.state == expected
        due += timedelta(seconds=delay)

    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceSnapshotModel)) == 0
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 0
        assert session.scalar(select(func.count()).select_from(ImportItemModel)) == 5
        assert session.scalar(
            select(func.count()).select_from(ImportItemModel).where(
                ImportItemModel.state == "failed"
            )
        ) == 5

    reactivated = coordinator.reactivate_pending_check(pending_id, due)
    assert reactivated.state == "debouncing"
    assert reactivated.stability_attempt_count == 0
    assert reactivated.last_failure_code is None


def test_new_event_reactivates_unstable_source(monitoring_database) -> None:
    coordinator, source, pending_id, _, base = _setup(monitoring_database)
    with monitoring_database.factory.begin() as session:
        pending = session.get(PendingPathCheckModel, pending_id)
        pending.state = "unstable_source"
        pending.stability_attempt_count = 5
        pending.last_failure_code = "SOURCE_BUSY"
    next_event = base + timedelta(minutes=1)

    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(),
            _root_id(monitoring_database, pending_id),
            "watchdog",
            RawFileEventType.MODIFIED,
            source,
            None,
            next_event,
            next_event,
            None,
            None,
            "5" * 64,
        )
    )

    with monitoring_database.factory() as session:
        pending = session.get(PendingPathCheckModel, pending_id)
        assert pending.state == "debouncing"
        assert pending.stability_attempt_count == 0
        assert pending.last_failure_code is None


def _root_id(database, pending_id):
    with database.factory() as session:
        return session.get(PendingPathCheckModel, pending_id).monitoring_root_id
