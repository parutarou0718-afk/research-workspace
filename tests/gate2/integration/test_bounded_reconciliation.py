import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from research_workspace.application.dto.monitoring_dto import (
    BaselineObservationDTO,
    MonitoringRootSeed,
    ReconciliationPlan,
)
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    ReconciliationReason,
)
from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    PendingPathCheckModel,
    ReconciliationRunModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.monitoring.reconciliation import BoundedReconciler


def _root(database, names=("same.pdf", "changed.pdf")):
    root = database.workspace.parent / "external"
    root.mkdir()
    now = datetime(2026, 7, 17, 17, tzinfo=timezone.utc)
    baseline = []
    for name in names:
        path = root / name
        path.write_bytes(name.encode())
        details = path.stat()
        baseline.append(
            BaselineObservationDTO(
                uuid4(), path, normalize_path_text(path), normalized_path_hash(path),
                name, "file", details.st_size,
                datetime.fromtimestamp(details.st_mtime, timezone.utc),
                None, str(details.st_dev), now,
            )
        )
    root_id = uuid4()
    coordinator = SqlWriteCoordinator(database.factory)
    coordinator.register_monitoring_root(
        MonitoringRootSeed(
            root_id, root, normalize_path_text(root), normalized_path_hash(root),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(), now,
        ),
        tuple(baseline),
    )
    return coordinator, root_id, root, now


def test_root_scoped_pages_checkpoint_and_filter_before_pending(
    monitoring_database, monkeypatch
) -> None:
    coordinator, root_id, root, now = _root(monitoring_database)
    (root / "changed.pdf").write_bytes(b"changed")
    (root / "new.pdf").write_bytes(b"new")
    (root / "ignored.txt").write_bytes(b"ignored")
    plan = ReconciliationPlan(
        uuid4(), uuid4(), root_id, ReconciliationReason.OVERFLOW, root, None, 2
    )
    known = coordinator.begin_reconciliation(plan, now)
    monkeypatch.setattr(Path, "read_bytes", lambda *_: (_ for _ in ()).throw(
        AssertionError("reconciliation must compare metadata before content reads")
    ))
    reconciler = BoundedReconciler()
    checkpoints, page_sizes = [], []
    while True:
        page = reconciler.scan_page(plan, known)
        page_sizes.append(page.items_seen)
        if page.checkpoint is not None:
            checkpoints.append(json.loads(page.checkpoint))
        coordinator.record_reconciliation_page(plan.reconciliation_run_id, page, now)
        if page.completed:
            break
        with monitoring_database.factory() as session:
            persisted = session.get(
                ReconciliationRunModel, plan.reconciliation_run_id
            )
            assert json.loads(persisted.checkpoint_json) == json.loads(page.checkpoint)
            assert persisted.items_seen == sum(page_sizes)
        plan = ReconciliationPlan(
            plan.operation_id, plan.reconciliation_run_id, root_id, plan.reason,
            root, page.checkpoint, 2,
        )

    with monitoring_database.factory() as session:
        run = session.get(ReconciliationRunModel, plan.reconciliation_run_id)
        pending = session.scalars(select(PendingPathCheckModel)).all()
        event = session.scalar(
            select(DomainEventModel).where(
                DomainEventModel.event_type == "monitoring.reconciliation_completed"
            )
        )
        assert run.status == "completed"
        assert run.items_seen == 3
        assert run.items_suspected_changed == 2
        assert {Path(item.normalized_path).name for item in pending} == {
            "changed.pdf", "new.pdf",
        }
        assert json.loads(event.payload_json) == {
            "items_seen": 3,
            "items_suspected_changed": 2,
            "monitoring_root_id": str(root_id),
            "reason": "overflow",
            "reconciliation_run_id": str(run.id),
        }
    assert page_sizes == [2, 1]
    assert checkpoints and all(size <= 2 for size in page_sizes)


def test_pause_resume_and_cancel_are_persisted_terminal_boundaries(
    monitoring_database,
) -> None:
    coordinator, root_id, root, now = _root(monitoring_database, ())
    plan = ReconciliationPlan(
        uuid4(), uuid4(), root_id, ReconciliationReason.USER_VERIFY, root, None, 1
    )
    coordinator.begin_reconciliation(plan, now)
    coordinator.pause_reconciliation(plan.reconciliation_run_id, now)
    coordinator.resume_reconciliation(plan.reconciliation_run_id, now)
    coordinator.cancel_reconciliation(plan.reconciliation_run_id, now)
    with monitoring_database.factory() as session:
        run = session.get(ReconciliationRunModel, plan.reconciliation_run_id)
        assert run.status == "cancelled"
        assert run.finished_at == now


@pytest.mark.parametrize("reason", tuple(ReconciliationReason))
def test_every_closed_reason_starts_only_by_explicit_request(
    monitoring_database, reason
) -> None:
    coordinator, root_id, root, now = _root(monitoring_database, ())
    plan = ReconciliationPlan(uuid4(), uuid4(), root_id, reason, root, None, 1)
    assert coordinator.begin_reconciliation(plan, now) == ()
    coordinator.cancel_reconciliation(plan.reconciliation_run_id, now)


def test_cooperative_cancel_returns_resumable_checkpoint(monitoring_database) -> None:
    coordinator, root_id, root, now = _root(monitoring_database, ("one.pdf",))
    plan = ReconciliationPlan(
        uuid4(), uuid4(), root_id, ReconciliationReason.USER_VERIFY, root, None, 1
    )
    known = coordinator.begin_reconciliation(plan, now)
    page = BoundedReconciler().scan_page(
        plan, known, cancel_requested=lambda: True
    )
    assert page.cancelled is True
    assert page.completed is False
    assert page.items_seen == 0
    assert page.checkpoint is not None
    coordinator.cancel_reconciliation(plan.reconciliation_run_id, now)
