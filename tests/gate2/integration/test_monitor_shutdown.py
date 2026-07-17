from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootSeed,
    RawFileEventDTO,
)
from research_workspace.application.services.operation_dispatcher import MonitoringLifecycle
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    RawFileEventType,
)
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    RawFileEventModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


class _Observer:
    def __init__(self, root_id, event, order, *, joined=True):
        self.active_root_ids = (root_id,)
        self._event = event
        self._drains = 0
        self._joined = joined
        self._order = order

    def stop(self, root_id):
        self._order.append(("stop", root_id))

    def drain_events(self):
        self._drains += 1
        self._order.append(("drain", self._drains))
        return (self._event,) if self._drains == 1 else ()

    def join(self, root_id, timeout):
        self._order.append(("join", root_id))
        return self._joined


class _Runner:
    def __init__(self, order, joined=True):
        self._order, self._joined = order, joined

    def shutdown(self, timeout=None):
        self._order.append(("worker_join", timeout))
        return self._joined


def _lifecycle(database, *, observer_joined=True, worker_joined=True):
    external = database.workspace.parent / "external"
    external.mkdir()
    now, root_id = datetime(2026, 7, 17, 18, tzinfo=timezone.utc), uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id, external, normalize_path_text(external),
            normalized_path_hash(external), DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(), now,
        ),
        (),
    )
    coordinator.begin_monitoring_session(now)
    event = RawFileEventDTO(
        uuid4(), root_id, "watchdog", RawFileEventType.CREATED,
        external / "paper.pdf", None, now, now, None, None, "d" * 64,
    )
    order = []
    lifecycle = MonitoringLifecycle(
        coordinator,
        _Observer(root_id, event, order, joined=observer_joined),
        _Runner(order, worker_joined),
    )
    return lifecycle, coordinator, order, now


def test_shutdown_stops_intake_persists_queue_joins_then_marks_clean(
    monitoring_database,
) -> None:
    lifecycle, _, order, now = _lifecycle(monitoring_database)
    assert lifecycle.shutdown(now=now, timeout=2) is True
    with monitoring_database.factory() as session:
        metadata = session.scalar(select(WorkspaceMetadataModel))
        assert metadata.clean_shutdown is True
        assert session.scalar(select(func.count()).select_from(RawFileEventModel)) == 1
    assert [item[0] for item in order] == [
        "stop", "drain", "join", "drain", "worker_join",
    ]


def test_failed_join_leaves_dirty_and_never_completes_unfinished_operation(
    monitoring_database,
) -> None:
    lifecycle, coordinator, _, now = _lifecycle(
        monitoring_database, observer_joined=False
    )
    operation_id = uuid4()
    with monitoring_database.factory.begin() as session:
        session.add(
            BackgroundOperationModel(
                id=operation_id, operation_type="source_observe", status="running",
                work_plan_fingerprint="f" * 64, permission_context_json="{}",
                result_summary_json=None, error_code=None, created_at=now,
                started_at=now, finished_at=None, cancel_requested_at=None,
            )
        )
    assert lifecycle.shutdown(now=now, timeout=0.01) is False
    with monitoring_database.factory() as session:
        assert session.scalar(select(WorkspaceMetadataModel.clean_shutdown)) is False
        assert session.get(BackgroundOperationModel, operation_id).status == "running"
