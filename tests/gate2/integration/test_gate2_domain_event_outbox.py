import json
from datetime import datetime, timezone
from uuid import uuid4

import rfc8785
from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import MonitoringRootSeed, RawFileEventDTO
from research_workspace.application.dto.monitoring_dto import CandidateDetectionResult
from research_workspace.application.dto.monitoring_dto import ReconciliationPlan
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    RawFileEventType,
    ReconciliationReason,
)
from research_workspace.domain.versioning import VersionRuleId
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    MonitoringRootModel,
    RawFileEventModel,
    ReconciliationRunModel,
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


def test_reconciliation_completion_event_collision_rolls_back_page(
    monitoring_database,
) -> None:
    coordinator, root_id, now = _root(monitoring_database)
    root_path = monitoring_database.workspace.parent / "external"
    plan = ReconciliationPlan(
        uuid4(), uuid4(), root_id, ReconciliationReason.USER_VERIFY,
        root_path, None, 10,
    )
    known = coordinator.begin_reconciliation(plan, now)
    from research_workspace.infrastructure.monitoring.reconciliation import BoundedReconciler
    page = BoundedReconciler().scan_page(plan, known)
    with monitoring_database.factory.begin() as session:
        session.add(
            DomainEventModel(
                id=uuid4(), schema_version="2.0",
                event_type="monitoring.reconciliation_completed",
                workspace_id=coordinator.workspace_id(), command_id=None,
                operation_id=uuid4(), aggregate_type="MonitoringRoot",
                aggregate_id=root_id, aggregate_version=None, actor_type="system",
                payload_json="{}", deduplication_key=(
                    f"monitoring.reconciliation_completed:{plan.reconciliation_run_id}"
                ),
                causation_id=None, correlation_id=None, created_at=now,
                occurred_at=now, processed_at=None,
            )
        )
    try:
        coordinator.record_reconciliation_page(plan.reconciliation_run_id, page, now)
    except WriteCoordinatorError:
        pass
    else:
        raise AssertionError("outbox collision must fail closed")
    with monitoring_database.factory() as session:
        run = session.get(ReconciliationRunModel, plan.reconciliation_run_id)
        assert run.status == "running"
        assert run.items_seen == 0


def test_candidate_event_collision_rolls_back_candidate_fact(
    monitoring_database,
) -> None:
    now = datetime(2026, 7, 17, 21, tzinfo=timezone.utc)
    snapshot_operation = uuid4()
    earlier_id, later_id = uuid4(), uuid4()
    from research_workspace.infrastructure.db.models import SourceSnapshotModel
    with monitoring_database.factory.begin() as session:
        session.add(
            BackgroundOperationModel(
                id=snapshot_operation, operation_type="snapshot_import",
                status="completed", work_plan_fingerprint="9" * 64,
                permission_context_json="{}", result_summary_json="{}",
                error_code=None, created_at=now, started_at=now,
                finished_at=now, cancel_requested_at=None,
            )
        )
        for snapshot_id, digest in ((earlier_id, "7" * 64), (later_id, "8" * 64)):
            session.add(
                SourceSnapshotModel(
                    id=snapshot_id, sha256=digest, size_bytes=1,
                    mime_type="application/pdf",
                    storage_relative_path=f"sources/{digest}.pdf", created_at=now,
                    created_by_operation_id=snapshot_operation,
                )
            )
    candidate_id, operation_id = uuid4(), uuid4()
    with monitoring_database.factory.begin() as session:
        session.add(
            DomainEventModel(
                id=uuid4(), schema_version="2.0",
                event_type="paper_version_candidate.detected",
                workspace_id=SqlWriteCoordinator(
                    monitoring_database.factory
                ).workspace_id(),
                command_id=None, operation_id=uuid4(),
                aggregate_type="PaperVersionCandidate", aggregate_id=uuid4(),
                aggregate_version=1, actor_type="system", payload_json="{}",
                deduplication_key=f"paper_version_candidate.detected:{candidate_id}",
                causation_id=None, correlation_id=None, created_at=now,
                occurred_at=now, processed_at=None,
            )
        )
    result = CandidateDetectionResult(
        earlier_id, later_id, "paper-version-detector", "1.0",
        VersionRuleId.R1_SOURCE_CONTINUITY, "6" * 64, b"{}", b"{}", (),
    )
    try:
        SqlWriteCoordinator(
            monitoring_database.factory
        ).register_version_candidate(candidate_id, operation_id, result, now)
    except WriteCoordinatorError:
        pass
    else:
        raise AssertionError("candidate outbox collision must fail closed")
    from research_workspace.infrastructure.db.models import PaperVersionCandidateModel
    with monitoring_database.factory() as session:
        assert session.get(PaperVersionCandidateModel, candidate_id) is None
        assert session.get(BackgroundOperationModel, operation_id) is None
