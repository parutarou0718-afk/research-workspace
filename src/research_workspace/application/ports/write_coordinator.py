"""Framework-free persistent-write boundary."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseSuccessDTO,
    PreparedParseAttempt,
)
from research_workspace.application.dto.monitoring_dto import (
    BaselineObservationDTO,
    CandidateDetectionResult,
    MonitoringRootSeed,
    MonitoringRestartState,
    PendingPathCheckDTO,
    RawFileEventDTO,
    ReconciliationObservation,
    ReconciliationPage,
    ReconciliationPlan,
)
from research_workspace.domain.monitoring import MonitoringRootStatus, RawEventCapacity
from research_workspace.application.dto.recovery_dto import VerifiedRecoveryPoint


@dataclass(frozen=True)
class ImportItemSeed:
    item_id: UUID
    observation_id: UUID
    source_path: Path
    normalized_path: str
    normalized_path_hash: str
    original_filename: str
    size_bytes: int | None
    modified_at_ns: int | None
    file_id_hint: str | None
    volume_serial_hint: str | None


@dataclass(frozen=True)
class ImportBatchSeed:
    operation_id: UUID
    batch_id: UUID
    work_plan_fingerprint: str
    permission_context_json: str
    items: tuple[ImportItemSeed, ...]
    estimated_total_bytes: int


@dataclass(frozen=True)
class PreparedImportItem:
    item_id: UUID
    observation_id: UUID
    source_path: Path


@dataclass(frozen=True)
class ParseOperationSeed:
    attempt: ParseAttemptSeed
    work_plan_fingerprint: str
    permission_context_json: str


class WriteCoordinator(Protocol):
    def workspace_id(self) -> UUID: ...

    def next_recovery_generation(self) -> int: ...

    def activate_recovery_point(self, point: VerifiedRecoveryPoint) -> None: ...

    def reset_recovery_after_restore(self, workspace_id: UUID) -> None: ...

    def begin_import(self, seed: ImportBatchSeed) -> tuple[PreparedImportItem, ...]: ...

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO: ...

    def mark_import_item(self, item_id: UUID, state: str, error_code: str | None) -> None: ...

    def finalize_import(
        self, operation_id: UUID, batch_id: UUID, batch_status: str, result_summary_json: str
    ) -> None: ...

    def mark_import_batch_parsing(self, operation_id: UUID, batch_id: UUID) -> None: ...

    def register_parse_success(self, result: ParseSuccessDTO) -> None: ...

    def register_parse_failure(self, result: ParseFailureDTO) -> None: ...

    def start_parse_attempt(self, seed: ParseAttemptSeed) -> PreparedParseAttempt: ...

    def begin_parse_operation(self, seed: ParseOperationSeed) -> PreparedParseAttempt: ...

    def mark_import_parse_result(
        self,
        item_id: UUID,
        parse_artifact_id: UUID | None,
        status: str,
        error_code: str | None,
    ) -> None: ...

    def cancel_parse_attempt(
        self, operation_id: UUID, parse_artifact_id: UUID, parse_attempt_id: UUID
    ) -> None: ...

    def set_parse_preference(
        self, source_snapshot_id: UUID, parse_artifact_id: UUID, operation_id: UUID
    ) -> int: ...

    def register_monitoring_root(
        self, seed: MonitoringRootSeed, baseline: tuple[BaselineObservationDTO, ...]
    ) -> UUID: ...

    def change_monitoring_root_status(
        self,
        monitoring_root_id: UUID,
        expected_status: MonitoringRootStatus,
        new_status: MonitoringRootStatus,
    ) -> int: ...

    def remove_monitoring_root(
        self, monitoring_root_id: UUID, expected_status: MonitoringRootStatus
    ) -> int: ...

    def ingest_raw_file_event(self, event: RawFileEventDTO) -> tuple[UUID, ...]: ...

    def record_monitoring_health(
        self, monitoring_root_id: UUID, new_status: MonitoringRootStatus,
        operation_id: UUID, now: datetime,
    ) -> MonitoringRootStatus: ...
    def assess_raw_event_capacity(
        self, monitoring_root_id: UUID, operation_id: UUID, now: datetime
    ) -> RawEventCapacity: ...

    def begin_reconciliation(
        self, plan: ReconciliationPlan, now: datetime
    ) -> tuple[ReconciliationObservation, ...]: ...
    def record_reconciliation_page(
        self, reconciliation_run_id: UUID, page: ReconciliationPage, now: datetime
    ) -> None: ...
    def pause_reconciliation(self, reconciliation_run_id: UUID, now: datetime) -> None: ...
    def resume_reconciliation(self, reconciliation_run_id: UUID, now: datetime) -> None: ...
    def cancel_reconciliation(self, reconciliation_run_id: UUID, now: datetime) -> None: ...

    def begin_monitoring_session(self, now: datetime) -> MonitoringRestartState: ...

    def complete_monitoring_session(self, now: datetime) -> None: ...

    def register_version_candidate(
        self,
        candidate_id: UUID,
        operation_id: UUID,
        result: CandidateDetectionResult,
        now: datetime,
    ) -> UUID: ...

    def supersede_version_candidate(
        self,
        candidate_id: UUID,
        replacement_candidate_id: UUID,
        operation_id: UUID,
        now: datetime,
    ) -> None: ...
    def begin_pending_import(
        self, pending_path_check_id: UUID, now: datetime
    ) -> PendingPathCheckDTO: ...

    def fail_pending_import(
        self, pending_path_check_id: UUID, error_code: str, now: datetime
    ) -> PendingPathCheckDTO: ...

    def reactivate_pending_check(
        self, pending_path_check_id: UUID, now: datetime
    ) -> PendingPathCheckDTO: ...

    def register_monitored_import(
        self, pending_path_check_id: UUID, result: SnapshotRegistrationDTO
    ) -> ImportCommitDTO: ...
