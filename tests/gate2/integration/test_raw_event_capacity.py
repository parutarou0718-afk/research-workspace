from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from watchdog.events import FileCreatedEvent

from research_workspace.application.dto.monitoring_dto import MonitoringRootPlan, MonitoringRootSeed
from research_workspace.domain import monitoring
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    RawFileEventType,
    assess_raw_event_capacity,
)
from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    RawFileEventModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.monitoring.watchdog_observer import WatchdogObserver


def test_capacity_thresholds_are_fixed_and_non_destructive() -> None:
    assert assess_raw_event_capacity(999_999, 2**30 - 1).warning is False
    by_count = assess_raw_event_capacity(1_000_000, 0)
    by_bytes = assess_raw_event_capacity(0, 2**30)
    assert by_count.reasons == ("event_count",)
    assert by_bytes.reasons == ("estimated_bytes",)


def test_callback_queue_is_bounded_and_coalesces_drops_into_overflow(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 15, tzinfo=timezone.utc)
    plan = MonitoringRootPlan(
        uuid4(),
        tmp_path,
        True,
        4,
        DEFAULT_MONITORING_CONFIG.fingerprint(),
        DEFAULT_MONITORING_CONFIG.canonical_json(),
    )
    observer = WatchdogObserver(clock=lambda: now, queue_capacity=1)
    handler = observer._make_handler(plan)
    handler.on_created(FileCreatedEvent(str(tmp_path / "one.pdf")))
    handler.on_created(FileCreatedEvent(str(tmp_path / "two.pdf")))

    events = observer.drain_events()
    assert [event.event_type for event in events] == [
        RawFileEventType.CREATED,
        RawFileEventType.OVERFLOW,
    ]
    assert observer.queue_policy == "bounded-coalesce-to-overflow"


def test_capacity_warning_degrades_root_without_deleting_raw_history(
    monitoring_database, monkeypatch
) -> None:
    external = monitoring_database.workspace.parent / "external"
    external.mkdir()
    now, root_id = datetime(2026, 7, 17, 15, tzinfo=timezone.utc), uuid4()
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
    from research_workspace.application.dto.monitoring_dto import RawFileEventDTO
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(), root_id, "watchdog", RawFileEventType.MODIFIED,
            external / "paper.pdf", None, now, now, None, None, "a" * 64,
        )
    )
    monkeypatch.setattr(monitoring, "RAW_EVENT_COUNT_WARNING", 1)
    result = coordinator.assess_raw_event_capacity(root_id, uuid4(), now)

    assert result.warning is True
    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 1
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 1
