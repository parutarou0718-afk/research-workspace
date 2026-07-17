from datetime import datetime, timezone
import inspect
from pathlib import Path
from uuid import uuid4

from watchdog.events import FileCreatedEvent, FileMovedEvent

from research_workspace.application.dto.monitoring_dto import MonitoringRootPlan
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG, RawFileEventType
from research_workspace.infrastructure.monitoring.watchdog_observer import WatchdogObserver


def _plan(root: Path) -> MonitoringRootPlan:
    return MonitoringRootPlan(
        uuid4(),
        root,
        True,
        0,
        DEFAULT_MONITORING_CONFIG.fingerprint(),
        DEFAULT_MONITORING_CONFIG.canonical_json(),
    )


def test_watchdog_callback_only_enqueues_immutable_raw_event_dtos(tmp_path: Path) -> None:
    observed_at = datetime(2026, 7, 17, 8, 30, tzinfo=timezone.utc)
    observer = WatchdogObserver(clock=lambda: observed_at)
    plan = _plan(tmp_path)
    handler = observer._make_handler(plan)

    handler.on_created(FileCreatedEvent(str(tmp_path / "paper.pdf")))
    handler.on_moved(
        FileMovedEvent(str(tmp_path / "draft.docx"), str(tmp_path / "final.docx"))
    )

    events = observer.drain_events()
    assert [event.event_type for event in events] == [
        RawFileEventType.CREATED,
        RawFileEventType.MOVED,
    ]
    assert events[0].source_path == tmp_path / "paper.pdf"
    assert events[1].destination_path == tmp_path / "final.docx"
    assert all(event.observed_at == observed_at for event in events)
    assert all(event.ingested_at == observed_at for event in events)


def test_watchdog_callback_has_no_database_domain_or_blocking_io_authority() -> None:
    source = inspect.getsource(
        __import__(
            "research_workspace.infrastructure.monitoring.watchdog_observer",
            fromlist=["WatchdogObserver"],
        )
    )
    forbidden = (
        "Session",
        "SqlWriteCoordinator",
        "SourceObservationModel",
        "DomainEventModel",
        "ImportOrchestrator",
        "sha256_file",
        "read_bytes",
        "copy",
        "open(",
        "QWidget",
        "requests",
        "socket",
    )
    assert all(token not in source for token in forbidden)
