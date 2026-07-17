import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import rfc8785
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from research_workspace.application.dto.monitoring_dto import MonitoringRootSeed, RawFileEventDTO
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG, RawFileEventType
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    MonitoringRootModel,
    RawFileEventModel,
)
from research_workspace.infrastructure.db.write_coordinator import (
    SqlWriteCoordinator,
    WriteCoordinatorError,
)
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


def _root(database):
    external = database.workspace.parent / "external"
    external.mkdir()
    now, root_id = datetime(2026, 7, 17, 16, tzinfo=timezone.utc), uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id, external, normalize_path_text(external),
            normalized_path_hash(external), DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(), now,
        ),
        (),
    )
    return coordinator, root_id, now


def _overflow(root_id, now, event_id=None):
    return RawFileEventDTO(
        event_id or uuid4(), root_id, "watchdog", RawFileEventType.OVERFLOW,
        None, None, now, now, b'{"provider_queue":"overflow"}', None, "b" * 64,
    )


def test_overflow_raw_fact_root_state_and_closed_event_commit_together(
    monitoring_database,
) -> None:
    coordinator, root_id, now = _root(monitoring_database)
    coordinator.ingest_raw_file_event(_overflow(root_id, now))

    with monitoring_database.factory() as session:
        root = session.get(MonitoringRootModel, root_id)
        event = session.scalar(select(DomainEventModel))
        assert root.status == "overflow_reconciling"
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 1
        assert json.loads(event.payload_json) == {
            "monitoring_root_id": str(root_id),
            "new_status": "overflow_reconciling",
            "old_status": "active",
        }


def test_overflow_operation_collision_rolls_back_raw_and_root_state(
    monitoring_database,
) -> None:
    coordinator, root_id, now = _root(monitoring_database)
    event_id = uuid4()
    with monitoring_database.factory.begin() as session:
        session.add(
            BackgroundOperationModel(
                id=event_id,
                operation_type="source_observe",
                status="completed",
                work_plan_fingerprint="c" * 64,
                permission_context_json=rfc8785.dumps({}).decode(),
                result_summary_json=None,
                error_code=None,
                created_at=now,
                started_at=now,
                finished_at=now,
                cancel_requested_at=None,
            )
        )
    try:
        coordinator.ingest_raw_file_event(_overflow(root_id, now, event_id))
    except WriteCoordinatorError:
        pass
    else:
        raise AssertionError("operation collision must fail closed")

    with monitoring_database.factory() as session:
        assert session.get(MonitoringRootModel, root_id).status == "active"
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 0
        assert session.scalar(select(func.count()).select_from(DomainEventModel)) == 0
