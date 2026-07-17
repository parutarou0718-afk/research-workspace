from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from research_workspace.application.dto.monitoring_dto import (
    MonitoringRootPlan,
    MonitoringRootSeed,
    RawFileEventDTO,
    ReconciliationPlan,
)
from research_workspace.application.services.operation_dispatcher import MonitoringLifecycle
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    RawFileEventType,
    ReconciliationReason,
)
from research_workspace.infrastructure.db.models import (
    MonitoringRootModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.monitoring.reconciliation import BoundedReconciler


class _IdleObserver:
    active_root_ids = ()

    def drain_events(self):
        return ()


class _IdleRunner:
    def shutdown(self, timeout=None):
        return True


def _root(database):
    root = database.workspace.parent / "external"
    root.mkdir()
    now, root_id = datetime(2026, 7, 17, 19, tzinfo=timezone.utc), uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id, root, normalize_path_text(root), normalized_path_hash(root),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(), now,
        ),
        (),
    )
    plan = MonitoringRootPlan(
        root_id, root, True, 0, DEFAULT_MONITORING_CONFIG.fingerprint(),
        DEFAULT_MONITORING_CONFIG.canonical_json(),
    )
    return coordinator, plan, now


def test_clean_healthy_restart_has_no_reconciliation_or_full_scan(
    monitoring_database,
) -> None:
    coordinator, plan, now = _root(monitoring_database)
    state = MonitoringLifecycle(
        coordinator, _IdleObserver(), _IdleRunner()
    ).startup((plan,), now)
    assert state.previous_clean_shutdown is True
    assert state.reconciliations == ()
    assert state.pending_check_ids == ()
    assert state.watcher_generation == 1


@pytest.mark.parametrize("cause", ("dirty", "stale"))
def test_dirty_or_stale_generation_requests_only_bounded_unclean_recovery(
    monitoring_database, cause,
) -> None:
    coordinator, plan, now = _root(monitoring_database)
    with monitoring_database.factory.begin() as session:
        metadata = session.scalar(select(WorkspaceMetadataModel))
        root = session.get(MonitoringRootModel, plan.monitoring_root_id)
        if cause == "dirty":
            metadata.clean_shutdown = False
        else:
            root.watcher_generation = 9
    state = MonitoringLifecycle(
        coordinator, _IdleObserver(), _IdleRunner()
    ).startup((plan,), now)
    assert [(item.monitoring_root_id, item.reason) for item in state.reconciliations] == [
        (plan.monitoring_root_id, ReconciliationReason.UNCLEAN_SHUTDOWN)
    ]


def test_overflow_and_pending_facts_drive_explicit_restart_recovery(
    monitoring_database,
) -> None:
    coordinator, plan, now = _root(monitoring_database)
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(), plan.monitoring_root_id, "watchdog",
            RawFileEventType.MODIFIED, plan.root_path / "paper.pdf", None,
            now, now, None, None, "e" * 64,
        )
    )
    coordinator.ingest_raw_file_event(
        RawFileEventDTO(
            uuid4(), plan.monitoring_root_id, "watchdog",
            RawFileEventType.OVERFLOW, None, None, now, now,
            b'{"overflow":true}', None, "f" * 64,
        )
    )
    state = MonitoringLifecycle(
        coordinator, _IdleObserver(), _IdleRunner()
    ).startup((plan,), now)
    assert [item.reason for item in state.reconciliations] == [
        ReconciliationReason.OVERFLOW
    ]
    assert len(state.pending_check_ids) == 1


def test_unavailable_root_becomes_disconnected_without_marking_children_missing(
    monitoring_database,
) -> None:
    coordinator, plan, now = _root(monitoring_database)
    plan.root_path.rmdir()
    state = MonitoringLifecycle(
        coordinator, _IdleObserver(), _IdleRunner()
    ).startup((plan,), now)
    assert [item.reason for item in state.reconciliations] == [
        ReconciliationReason.DISCONNECT
    ]
    with monitoring_database.factory() as session:
        assert session.get(MonitoringRootModel, plan.monitoring_root_id).status == (
            "disconnected"
        )


def test_running_reconciliation_resumes_from_persisted_checkpoint(
    monitoring_database,
) -> None:
    coordinator, root_plan, now = _root(monitoring_database)
    (root_plan.root_path / "one.pdf").write_bytes(b"one")
    (root_plan.root_path / "two.pdf").write_bytes(b"two")
    plan = ReconciliationPlan(
        uuid4(), uuid4(), root_plan.monitoring_root_id,
        ReconciliationReason.USER_VERIFY, root_plan.root_path, None, 1,
    )
    known = coordinator.begin_reconciliation(plan, now)
    page = BoundedReconciler().scan_page(plan, known)
    assert page.completed is False
    coordinator.record_reconciliation_page(plan.reconciliation_run_id, page, now)

    state = MonitoringLifecycle(
        coordinator, _IdleObserver(), _IdleRunner()
    ).startup((root_plan,), now)
    assert len(state.reconciliations) == 1
    recovery = state.reconciliations[0]
    assert recovery.reconciliation_run_id == plan.reconciliation_run_id
    assert recovery.reason is ReconciliationReason.USER_VERIFY
    assert recovery.checkpoint == page.checkpoint
