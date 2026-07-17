"""Read-only monitoring projections built only from persisted Gate 2 facts."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
from uuid import UUID

import rfc8785
from sqlalchemy import func, select

from research_workspace.application.dto.monitoring_dto import MonitoringRootRecord
from research_workspace.application.ports.repositories import MonitoringRepository
from research_workspace.domain.monitoring import RAW_EVENT_COUNT_WARNING
from research_workspace.infrastructure.db.models import (
    ImportItemModel,
    MonitoringRootModel,
    PendingPathCheckModel,
    RawFileEventModel,
    ReconciliationRunModel,
    SourceObservationModel,
)


class GetMonitoring:
    def __init__(self, repository: MonitoringRepository) -> None:
        self._repository = repository

    def execute(self) -> tuple[MonitoringRootRecord, ...]:
        return self._repository.list_roots()


@dataclass(frozen=True, slots=True)
class MonitoringRootProjection:
    monitoring_root_id: UUID
    original_path: Path
    status: str
    last_event_at: datetime | None
    waiting_count: int
    failure_count: int
    recent_failure_codes: tuple[str, ...]
    recent_imports: tuple[str, ...]
    reconciliation_run_id: UUID | None
    reconciliation_status: str | None
    reconciliation_items_seen: int
    reconciliation_items_estimated: int | None
    reconciliation_items_changed: int
    overflow_warning: bool
    capacity_warning: bool
    meaningful_update_marker: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "recent_failure_codes", tuple(self.recent_failure_codes)
        )
        object.__setattr__(self, "recent_imports", tuple(self.recent_imports))


@dataclass(frozen=True, slots=True)
class MonitoringDashboard:
    roots: tuple[MonitoringRootProjection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "roots", tuple(self.roots))


class GetMonitoringDashboard:
    """Aggregate read model; execution has no repair or scheduling side effects."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def execute(self) -> MonitoringDashboard:
        with self._session_factory() as session:
            roots = session.scalars(
                select(MonitoringRootModel)
                .where(MonitoringRootModel.removed_at.is_(None))
                .order_by(MonitoringRootModel.normalized_path)
            ).all()
            return MonitoringDashboard(
                tuple(self._project(session, root) for root in roots)
            )

    @staticmethod
    def _project(session, root: MonitoringRootModel) -> MonitoringRootProjection:
        last_event_at = session.scalar(
            select(func.max(RawFileEventModel.observed_at)).where(
                RawFileEventModel.monitoring_root_id == root.id
            )
        )
        waiting_count = session.scalar(
            select(func.count(PendingPathCheckModel.id)).where(
                PendingPathCheckModel.monitoring_root_id == root.id,
                PendingPathCheckModel.state.in_(
                    (
                        "detected",
                        "debouncing",
                        "waiting_for_stability",
                        "importing",
                    )
                ),
            )
        ) or 0
        failure_count = session.scalar(
            select(func.count(PendingPathCheckModel.id)).where(
                PendingPathCheckModel.monitoring_root_id == root.id,
                PendingPathCheckModel.state.in_(("safe_failure", "unstable_source")),
            )
        ) or 0
        failure_codes = tuple(
            value
            for value in session.scalars(
                select(PendingPathCheckModel.last_failure_code)
                .where(
                    PendingPathCheckModel.monitoring_root_id == root.id,
                    PendingPathCheckModel.last_failure_code.is_not(None),
                )
                .order_by(PendingPathCheckModel.last_event_at.desc())
                .limit(5)
            )
            if value is not None
        )
        imports = tuple(
            session.scalars(
                select(SourceObservationModel.original_filename)
                .join(
                    ImportItemModel,
                    ImportItemModel.source_observation_id
                    == SourceObservationModel.id,
                )
                .where(
                    SourceObservationModel.monitoring_root_id == root.id,
                    ImportItemModel.state.in_(("imported", "duplicate_content")),
                )
                .order_by(ImportItemModel.finished_at.desc(), ImportItemModel.id)
                .limit(5)
            )
        )
        reconciliation = session.scalar(
            select(ReconciliationRunModel)
            .where(ReconciliationRunModel.monitoring_root_id == root.id)
            .order_by(
                ReconciliationRunModel.started_at.desc(),
                ReconciliationRunModel.id,
            )
            .limit(1)
        )
        raw_count = session.scalar(
            select(func.count(RawFileEventModel.id)).where(
                RawFileEventModel.monitoring_root_id == root.id
            )
        ) or 0
        facts = {
            "status": root.status,
            "last_event_at": (
                last_event_at.isoformat() if last_event_at is not None else None
            ),
            "waiting_count": waiting_count,
            "failure_count": failure_count,
            "recent_failure_codes": failure_codes,
            "recent_imports": imports,
            "reconciliation": (
                None
                if reconciliation is None
                else {
                    "id": str(reconciliation.id),
                    "status": reconciliation.status,
                    "seen": reconciliation.items_seen,
                    "estimated": reconciliation.items_estimated,
                    "changed": reconciliation.items_suspected_changed,
                }
            ),
        }
        marker = hashlib.sha256(rfc8785.dumps(facts)).hexdigest()
        return MonitoringRootProjection(
            root.id,
            Path(root.original_path),
            root.status,
            last_event_at,
            waiting_count,
            failure_count,
            failure_codes,
            imports,
            reconciliation.id if reconciliation is not None else None,
            reconciliation.status if reconciliation is not None else None,
            reconciliation.items_seen if reconciliation is not None else 0,
            reconciliation.items_estimated if reconciliation is not None else None,
            (
                reconciliation.items_suspected_changed
                if reconciliation is not None
                else 0
            ),
            root.status == "overflow_reconciling",
            raw_count >= RAW_EVENT_COUNT_WARNING,
            marker,
        )
