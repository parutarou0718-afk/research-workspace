import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootSeed,
    RawFileEventDTO,
)
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG, RawFileEventType
from research_workspace.infrastructure.db.models import PendingPathCheckModel
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


def test_dense_out_of_order_events_merge_deterministically(monitoring_database) -> None:
    external = monitoring_database.workspace.parent / "external"
    external.mkdir()
    root_id = uuid4()
    base = datetime(2026, 7, 17, 10, tzinfo=timezone.utc)
    coordinator = SqlWriteCoordinator(monitoring_database.factory)
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
    path = external / "storm.pdf"
    events = (
        (RawFileEventType.MODIFIED, base + timedelta(seconds=2), "1" * 64),
        (RawFileEventType.CREATED, base, "2" * 64),
        (RawFileEventType.DELETED, base + timedelta(seconds=1), "3" * 64),
    )
    for kind, observed_at, key in events:
        coordinator.ingest_raw_file_event(
            RawFileEventDTO(
                uuid4(),
                root_id,
                "watchdog",
                kind,
                path,
                None,
                observed_at,
                observed_at,
                None,
                None,
                key,
            )
        )

    with monitoring_database.factory() as session:
        pending = session.scalar(select(PendingPathCheckModel))
        assert pending is not None
        assert pending.first_event_at == base
        assert pending.last_event_at == base + timedelta(seconds=2)
        assert pending.next_check_at == base + timedelta(seconds=4)
        assert pending.state == "debouncing"
        assert json.loads(pending.merged_event_types_json) == [
            "created",
            "deleted",
            "modified",
        ]
        assert pending.stability_attempt_count == 0
        assert pending.row_version == 3
