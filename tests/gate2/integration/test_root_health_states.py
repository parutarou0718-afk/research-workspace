import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from research_workspace.application.dto.monitoring_dto import (
    BaselineObservationDTO,
    MonitoringRootSeed,
)
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    MonitoringRootStatus,
)
from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    MonitoringRootModel,
    SourceObservationModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


def _root_with_observation(database):
    external = database.workspace.parent / "external"
    external.mkdir()
    source = external / "paper.pdf"
    source.write_bytes(b"baseline metadata only")
    now = datetime(2026, 7, 17, 14, tzinfo=timezone.utc)
    root_id, observation_id = uuid4(), uuid4()
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
        (
            BaselineObservationDTO(
                observation_id,
                source,
                normalize_path_text(source),
                normalized_path_hash(source),
                source.name,
                "file",
                source.stat().st_size,
                now,
                None,
                None,
                now,
            ),
        ),
    )
    return coordinator, root_id, observation_id, now


def test_disconnect_permission_loss_and_error_are_exact_non_delete_states(
    monitoring_database,
) -> None:
    coordinator, root_id, observation_id, now = _root_with_observation(
        monitoring_database
    )
    coordinator.record_monitoring_health(
        root_id, MonitoringRootStatus.DISCONNECTED, uuid4(), now
    )
    coordinator.record_monitoring_health(
        root_id, MonitoringRootStatus.ACTIVE, uuid4(), now
    )
    coordinator.record_monitoring_health(
        root_id, MonitoringRootStatus.DEGRADED, uuid4(), now
    )
    coordinator.record_monitoring_health(
        root_id, MonitoringRootStatus.ERROR, uuid4(), now
    )

    with monitoring_database.factory() as session:
        root = session.get(MonitoringRootModel, root_id)
        observation = session.get(SourceObservationModel, observation_id)
        events = session.scalars(
            select(DomainEventModel).where(
                DomainEventModel.event_type == "monitoring.root_status_changed"
            )
        ).all()
        assert root.status == "error"
        assert root.removed_at is None
        assert observation.availability_status == "available"
        assert observation.missing_at is None
        assert len(events) == 4
        assert [
            (json.loads(event.payload_json)["old_status"],
             json.loads(event.payload_json)["new_status"])
            for event in events
        ] == [
            ("active", "disconnected"),
            ("disconnected", "active"),
            ("active", "degraded"),
            ("degraded", "error"),
        ]
        assert all(
            str(monitoring_database.workspace.parent) not in event.payload_json
            for event in events
        )
