"""The sole Gate 1 SQLite transaction owner for approved database facts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
from typing import Callable
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import rfc8785
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.monitoring_dto import (
    BaselineObservationDTO,
    MonitoringRootSeed,
    RawFileEventDTO,
)
from research_workspace.application.ports.write_coordinator import (
    ImportBatchSeed,
    ParseOperationSeed,
    PreparedImportItem,
)
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseSuccessDTO,
    PreparedParseAttempt,
)
from research_workspace.domain.import_model import FileStat, StagedSource
from research_workspace.domain.monitoring import MonitoringRootStatus, RawFileEventType
from research_workspace.domain.parsing import (
    ParseContractError,
    build_parse_artifact_identity,
)
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    ImportBatchModel,
    ImportItemModel,
    MonitoringRootModel,
    PendingPathCheckModel,
    ParseArtifactModel,
    ParseAttemptModel,
    RawEventPendingLinkModel,
    RawFileEventModel,
    SnapshotParsePreferenceModel,
    SourceObservationModel,
    SourceObservationEventModel,
    SourceSnapshotModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository
from research_workspace.infrastructure.filesystem.atomic_files import (
    PromotionState,
    fsync_file_and_parent,
    promote_no_replace,
)
from research_workspace.infrastructure.filesystem.path_safety import reject_reparse_chain
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)
from research_workspace.infrastructure.filesystem.stability import sha256_file


class WriteCoordinatorError(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


RepositoryFactory = Callable[[Session], object]


class SqlWriteCoordinator:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        repository_factory: RepositoryFactory = SqlGate1WriteRepository,
        data_directory: Path | None = None,
    ) -> None:
        self._factory = factory
        self._repository_factory = repository_factory
        self._data_directory = data_directory

    def workspace_id(self) -> UUID:
        with self._factory() as session:
            workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
        if workspace_id is None:
            raise WriteCoordinatorError("WORKSPACE_METADATA_MISSING")
        return workspace_id

    def register_monitoring_root(
        self, seed: MonitoringRootSeed, baseline: tuple[BaselineObservationDTO, ...]
    ) -> UUID:
        try:
            with self._factory.begin() as session:
                session.add(
                    MonitoringRootModel(
                        id=seed.monitoring_root_id,
                        original_path=str(seed.original_path),
                        normalized_path=seed.normalized_path,
                        normalized_path_hash=seed.normalized_path_hash,
                        status=MonitoringRootStatus.ACTIVE.value,
                        recursive=True,
                        config_json=seed.semantic_config_json.decode("utf-8"),
                        config_fingerprint=seed.config_fingerprint,
                        watcher_generation=0,
                        last_event_at=None,
                        last_reconciled_at=None,
                        created_at=seed.created_at,
                        updated_at=seed.created_at,
                        removed_at=None,
                    )
                )
                for item in baseline:
                    if item.entry_type != "file":
                        raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
                    observation = session.scalar(
                        select(SourceObservationModel).where(
                            SourceObservationModel.normalized_path == item.normalized_path
                        )
                    )
                    if observation is None:
                        observation = SourceObservationModel(
                            id=item.observation_id,
                            original_path=str(item.original_path),
                            normalized_path=item.normalized_path,
                            normalized_path_hash=item.normalized_path_hash,
                            original_filename=item.original_filename,
                            monitoring_root_id=seed.monitoring_root_id,
                            current_snapshot_id=None,
                            availability_status="available",
                            baseline_only=True,
                            size_bytes=item.size_bytes,
                            modified_at=item.modified_at,
                            file_id_hint=item.file_id_hint,
                            volume_serial_hint=item.volume_serial_hint,
                            first_seen_at=item.observed_at,
                            last_seen_at=item.observed_at,
                            missing_at=None,
                            row_version=1,
                        )
                        session.add(observation)
                    elif (
                        observation.monitoring_root_id is not None
                        and observation.monitoring_root_id != seed.monitoring_root_id
                    ):
                        raise WriteCoordinatorError("MONITOR_ROOT_OVERLAP")
                    else:
                        observation.monitoring_root_id = seed.monitoring_root_id
                        observation.last_seen_at = item.observed_at
                        observation.row_version += 1
                    session.flush()
                    facts = {
                        "entry_type": item.entry_type,
                        "size_bytes": item.size_bytes,
                        "modified_at": (
                            item.modified_at.isoformat().replace("+00:00", "Z")
                            if item.modified_at is not None
                            else None
                        ),
                        "file_id_hint": item.file_id_hint,
                        "volume_serial_hint": item.volume_serial_hint,
                    }
                    session.add(
                        SourceObservationEventModel(
                            id=uuid4(),
                            source_observation_id=observation.id,
                            raw_file_event_id=None,
                            event_type="baseline",
                            snapshot_id=None,
                            path_before_hash=None,
                            path_after_hash=item.normalized_path_hash,
                            facts_json=rfc8785.dumps(facts).decode("utf-8"),
                            observed_at=item.observed_at,
                        )
                    )
            return seed.monitoring_root_id
        except WriteCoordinatorError:
            raise
        except IntegrityError as exc:
            raise WriteCoordinatorError("MONITOR_ROOT_CONFLICT") from exc

    def change_monitoring_root_status(
        self,
        monitoring_root_id: UUID,
        expected_status: MonitoringRootStatus,
        new_status: MonitoringRootStatus,
    ) -> int:
        allowed = {
            (MonitoringRootStatus.ACTIVE, MonitoringRootStatus.PAUSED),
            (MonitoringRootStatus.PAUSED, MonitoringRootStatus.ACTIVE),
        }
        if (expected_status, new_status) not in allowed:
            raise WriteCoordinatorError("MONITOR_ROOT_STATE_CHANGED")
        with self._factory.begin() as session:
            root = session.get(MonitoringRootModel, monitoring_root_id)
            if (
                root is None
                or root.removed_at is not None
                or root.status != expected_status.value
            ):
                raise WriteCoordinatorError("MONITOR_ROOT_STATE_CHANGED")
            root.status = new_status.value
            root.updated_at = datetime.now(timezone.utc)
            if new_status is MonitoringRootStatus.ACTIVE:
                root.watcher_generation += 1
            return root.watcher_generation

    def remove_monitoring_root(
        self, monitoring_root_id: UUID, expected_status: MonitoringRootStatus
    ) -> int:
        with self._factory.begin() as session:
            root = session.get(MonitoringRootModel, monitoring_root_id)
            if (
                root is None
                or root.removed_at is not None
                or root.status != expected_status.value
            ):
                raise WriteCoordinatorError("MONITOR_ROOT_STATE_CHANGED")
            now = datetime.now(timezone.utc)
            root.status = MonitoringRootStatus.PAUSED.value
            root.removed_at = now
            root.updated_at = now
            return root.watcher_generation

    def ingest_raw_file_event(self, event: RawFileEventDTO) -> tuple[UUID, ...]:
        """Append one raw provider fact and merge its affected path checks."""

        try:
            with self._factory.begin() as session:
                existing = session.scalar(
                    select(RawFileEventModel).where(
                        RawFileEventModel.deduplication_key == event.deduplication_key
                    )
                )
                if existing is not None:
                    return self._linked_pending_ids(session, existing.id)

                root = session.get(MonitoringRootModel, event.monitoring_root_id)
                if (
                    root is None
                    or root.removed_at is not None
                    or root.status != MonitoringRootStatus.ACTIVE.value
                ):
                    raise WriteCoordinatorError("MONITOR_ROOT_STATE_CHANGED")
                paths = self._event_paths(event)
                for path in paths:
                    if not self._path_belongs_to_root(path, root.normalized_path):
                        raise WriteCoordinatorError("MONITOR_ROOT_PATH_UNSAFE")

                raw = RawFileEventModel(
                    id=event.event_id,
                    monitoring_root_id=event.monitoring_root_id,
                    provider=event.provider,
                    event_type=event.event_type.value,
                    source_path=str(event.source_path) if event.source_path is not None else None,
                    destination_path=(
                        str(event.destination_path)
                        if event.destination_path is not None
                        else None
                    ),
                    source_path_hash=(
                        normalized_path_hash(event.source_path)
                        if event.source_path is not None
                        else None
                    ),
                    destination_path_hash=(
                        normalized_path_hash(event.destination_path)
                        if event.destination_path is not None
                        else None
                    ),
                    observed_at=event.observed_at,
                    ingested_at=event.ingested_at,
                    raw_sequence_json=(
                        event.raw_sequence_json.decode("utf-8")
                        if event.raw_sequence_json is not None
                        else None
                    ),
                    correlation_hint=event.correlation_hint,
                    deduplication_key=event.deduplication_key,
                )
                session.add(raw)
                session.flush()

                config = json.loads(root.config_json)
                quiet_seconds = int(config["quiet_window_seconds"])
                pending_ids: list[UUID] = []
                for path in paths:
                    normalized = normalize_path_text(path)
                    pending = session.scalar(
                        select(PendingPathCheckModel).where(
                            PendingPathCheckModel.monitoring_root_id == root.id,
                            PendingPathCheckModel.normalized_path == normalized,
                        )
                    )
                    observation = session.scalar(
                        select(SourceObservationModel).where(
                            SourceObservationModel.normalized_path == normalized
                        )
                    )
                    if pending is None:
                        pending = PendingPathCheckModel(
                            id=uuid4(),
                            monitoring_root_id=root.id,
                            normalized_path=normalized,
                            normalized_path_hash=normalized_path_hash(path),
                            first_event_at=event.observed_at,
                            last_event_at=event.observed_at,
                            merged_event_types_json=rfc8785.dumps(
                                [event.event_type.value]
                            ).decode("utf-8"),
                            state="debouncing",
                            stability_attempt_count=0,
                            next_check_at=event.observed_at + timedelta(seconds=quiet_seconds),
                            last_failure_code=None,
                            source_observation_id=observation.id if observation is not None else None,
                            row_version=1,
                        )
                        session.add(pending)
                        session.flush()
                    else:
                        merged = set(json.loads(pending.merged_event_types_json))
                        merged.add(event.event_type.value)
                        pending.merged_event_types_json = rfc8785.dumps(
                            sorted(merged)
                        ).decode("utf-8")
                        pending.first_event_at = min(
                            pending.first_event_at, event.observed_at
                        )
                        pending.last_event_at = max(
                            pending.last_event_at, event.observed_at
                        )
                        pending.next_check_at = pending.last_event_at + timedelta(
                            seconds=quiet_seconds
                        )
                        pending.state = "debouncing"
                        pending.row_version += 1
                    session.add(
                        RawEventPendingLinkModel(
                            raw_file_event_id=raw.id,
                            pending_path_check_id=pending.id,
                            linked_at=event.ingested_at,
                        )
                    )
                    pending_ids.append(pending.id)
                root.last_event_at = (
                    event.observed_at
                    if root.last_event_at is None
                    else max(root.last_event_at, event.observed_at)
                )
                root.updated_at = max(root.updated_at, event.ingested_at)
                return tuple(sorted(pending_ids, key=str))
        except WriteCoordinatorError:
            raise
        except (IntegrityError, ValueError, KeyError, UnicodeDecodeError) as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc

    @staticmethod
    def _event_paths(event: RawFileEventDTO) -> tuple[Path, ...]:
        if event.event_type in {RawFileEventType.OVERFLOW, RawFileEventType.ROOT_STATE}:
            return ()
        if event.source_path is None:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        if event.event_type is RawFileEventType.MOVED:
            if event.destination_path is None:
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            return (event.source_path, event.destination_path)
        if event.destination_path is not None:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        return (event.source_path,)

    @staticmethod
    def _path_belongs_to_root(path: Path, normalized_root: str) -> bool:
        normalized = normalize_path_text(path)
        try:
            return os.path.commonpath((normalized, normalized_root)) == normalized_root
        except ValueError:
            return False

    @staticmethod
    def _linked_pending_ids(session: Session, raw_event_id: UUID) -> tuple[UUID, ...]:
        ids = session.scalars(
            select(RawEventPendingLinkModel.pending_path_check_id).where(
                RawEventPendingLinkModel.raw_file_event_id == raw_event_id
            )
        ).all()
        return tuple(sorted(ids, key=str))

    def begin_import(self, seed: ImportBatchSeed) -> tuple[PreparedImportItem, ...]:
        now = datetime.now(timezone.utc)
        prepared: list[PreparedImportItem] = []
        with self._factory.begin() as session:
            session.add(
                BackgroundOperationModel(
                    id=seed.operation_id,
                    operation_type="snapshot_import",
                    status="running",
                    work_plan_fingerprint=seed.work_plan_fingerprint,
                    permission_context_json=seed.permission_context_json,
                    result_summary_json=None,
                    error_code=None,
                    created_at=now,
                    started_at=now,
                    finished_at=None,
                    cancel_requested_at=None,
                )
            )
            session.add(
                ImportBatchModel(
                    id=seed.batch_id,
                    operation_id=seed.operation_id,
                    status="importing",
                    selected_count=len(seed.items),
                    estimated_total_bytes=seed.estimated_total_bytes,
                    estimated_added_bytes=None,
                    estimate_is_exact=False,
                    disclosure_accepted_at=now,
                    created_at=now,
                    finished_at=None,
                )
            )
            for item in seed.items:
                observation = session.scalar(
                    select(SourceObservationModel).where(
                        SourceObservationModel.normalized_path == item.normalized_path
                    )
                )
                if observation is None:
                    observation = SourceObservationModel(
                        id=item.observation_id,
                        original_path=str(item.source_path),
                        normalized_path=item.normalized_path,
                        normalized_path_hash=item.normalized_path_hash,
                        original_filename=item.original_filename,
                        current_snapshot_id=None,
                        availability_status="available" if item.size_bytes is not None else "unavailable",
                        baseline_only=False,
                        size_bytes=item.size_bytes,
                        modified_at=(
                            datetime.fromtimestamp(item.modified_at_ns / 1_000_000_000, timezone.utc)
                            if item.modified_at_ns is not None
                            else None
                        ),
                        file_id_hint=item.file_id_hint,
                        volume_serial_hint=item.volume_serial_hint,
                        first_seen_at=now,
                        last_seen_at=now,
                        missing_at=None,
                        row_version=1,
                    )
                    session.add(observation)
                    session.flush()
                else:
                    observation.last_seen_at = now
                    observation.row_version += 1
                session.add(
                    ImportItemModel(
                        id=item.item_id,
                        batch_id=seed.batch_id,
                        source_observation_id=observation.id,
                        snapshot_id=None,
                        parse_artifact_id=None,
                        state="pending",
                        parse_status="not_requested",
                        error_code=None,
                        created_at=now,
                        finished_at=None,
                    )
                )
                prepared.append(PreparedImportItem(item.item_id, observation.id, item.source_path))
        return tuple(prepared)

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO:
        try:
            with self._factory.begin() as session:
                repository = self._repository_factory(session)
                committed = repository.register_import(result)
                workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
                if workspace_id is None:
                    raise WriteCoordinatorError("WORKSPACE_METADATA_MISSING")
                event_type = (
                    "source.snapshot_reused"
                    if committed.state == "duplicate_content"
                    else "source.snapshot_imported"
                )
                payload = {
                    "snapshot_id": str(committed.snapshot_id),
                    "source_observation_id": str(committed.source_observation_id),
                    "import_item_id": str(committed.import_item_id),
                    "sha256": result.sha256,
                    "size_bytes": result.size_bytes,
                }
                now = datetime.now(timezone.utc)
                session.add(
                    DomainEventModel(
                        id=uuid4(),
                        schema_version="2.0",
                        event_type=event_type,
                        workspace_id=workspace_id,
                        command_id=None,
                        operation_id=result.operation_id,
                        aggregate_type="SourceSnapshot",
                        aggregate_id=committed.snapshot_id,
                        aggregate_version=None,
                        actor_type="system",
                        payload_json=rfc8785.dumps(payload).decode("utf-8"),
                        deduplication_key=f"{event_type}:{result.import_item_id}",
                        causation_id=None,
                        correlation_id=result.operation_id,
                        created_at=now,
                        occurred_at=now,
                        processed_at=None,
                    )
                )
            return committed
        except WriteCoordinatorError:
            raise
        except IntegrityError as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc
        except OperationalError as exc:
            sqlite_errorcode = getattr(exc.orig, "sqlite_errorcode", None)
            if sqlite_errorcode in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise WriteCoordinatorError("SQLITE_BUSY") from exc
            raise WriteCoordinatorError("DATABASE_OPERATION_FAILED") from exc

    def mark_import_item(self, item_id: UUID, state: str, error_code: str | None) -> None:
        if state not in {"failed", "cancelled"}:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        with self._factory.begin() as session:
            item = session.get(ImportItemModel, item_id)
            if item is None or item.state != "pending":
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            item.state = state
            item.error_code = error_code
            item.finished_at = datetime.now(timezone.utc)

    def finalize_import(
        self,
        operation_id: UUID,
        batch_id: UUID,
        batch_status: str,
        result_summary_json: str,
    ) -> None:
        operation_status = {
            "completed": "completed",
            "completed_with_failures": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }.get(batch_status)
        if operation_status is None:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        now = datetime.now(timezone.utc)
        with self._factory.begin() as session:
            operation = session.get(BackgroundOperationModel, operation_id)
            batch = session.get(ImportBatchModel, batch_id)
            if operation is None or batch is None:
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            batch.status = batch_status
            batch.finished_at = now
            operation.status = operation_status
            operation.result_summary_json = result_summary_json
            operation.error_code = None
            operation.finished_at = now

    def mark_import_batch_parsing(self, operation_id: UUID, batch_id: UUID) -> None:
        with self._factory.begin() as session:
            operation = self._required_running_operation(session, operation_id)
            batch = session.get(ImportBatchModel, batch_id)
            if batch is None or batch.operation_id != operation.id or batch.status != "importing":
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            batch.status = "parsing"

    def start_parse_attempt(self, seed: ParseAttemptSeed) -> PreparedParseAttempt:
        identity = build_parse_artifact_identity(
            seed.source_snapshot_id,
            seed.parser_id,
            seed.parser_version,
            seed.parser_config,
            seed.contract_version,
        )
        try:
            with self._factory.begin() as session:
                repository = self._repository_factory(session)
                prepared = repository.start_parse_attempt(seed, identity)
                operation = self._required_running_operation(session, seed.operation_id)
                operation.result_summary_json = rfc8785.dumps(
                    {
                        "parse_artifact_id": str(prepared.parse_artifact_id),
                        "parse_attempt_id": str(prepared.parse_attempt_id),
                        "source_snapshot_id": str(prepared.source_snapshot_id),
                        "status": "running",
                    }
                ).decode("utf-8")
                return prepared
        except ValueError as exc:
            raise WriteCoordinatorError(str(exc)) from exc
        except IntegrityError as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc

    def begin_parse_operation(self, seed: ParseOperationSeed) -> PreparedParseAttempt:
        """Create the bounded technical operation and its first parse attempt atomically."""

        now = datetime.now(timezone.utc)
        identity = build_parse_artifact_identity(
            seed.attempt.source_snapshot_id,
            seed.attempt.parser_id,
            seed.attempt.parser_version,
            seed.attempt.parser_config,
            seed.attempt.contract_version,
        )
        try:
            with self._factory.begin() as session:
                session.add(
                    BackgroundOperationModel(
                        id=seed.attempt.operation_id,
                        operation_type="document_parse",
                        status="running",
                        work_plan_fingerprint=seed.work_plan_fingerprint,
                        permission_context_json=seed.permission_context_json,
                        result_summary_json=None,
                        error_code=None,
                        created_at=now,
                        started_at=now,
                        finished_at=None,
                        cancel_requested_at=None,
                    )
                )
                session.flush()
                repository = self._repository_factory(session)
                prepared = repository.start_parse_attempt(seed.attempt, identity)
                operation = self._required_running_operation(session, seed.attempt.operation_id)
                operation.result_summary_json = rfc8785.dumps(
                    {
                        "parse_artifact_id": str(prepared.parse_artifact_id),
                        "parse_attempt_id": str(prepared.parse_attempt_id),
                        "source_snapshot_id": str(prepared.source_snapshot_id),
                        "status": "running",
                    }
                ).decode("utf-8")
                return prepared
        except ValueError as exc:
            raise WriteCoordinatorError(str(exc)) from exc
        except IntegrityError as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc

    def mark_import_parse_result(
        self,
        item_id: UUID,
        parse_artifact_id: UUID | None,
        status: str,
        error_code: str | None,
    ) -> None:
        if status not in {"pending", "succeeded", "failed", "cancelled"}:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        with self._factory.begin() as session:
            item = session.get(ImportItemModel, item_id)
            if item is None or item.state not in {"imported", "duplicate_content"}:
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            item.parse_status = status
            item.parse_artifact_id = parse_artifact_id
            item.error_code = error_code

    def cancel_parse_attempt(
        self, operation_id: UUID, parse_artifact_id: UUID, parse_attempt_id: UUID
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._factory.begin() as session:
            operation = self._required_running_operation(session, operation_id)
            artifact = session.get(ParseArtifactModel, parse_artifact_id)
            attempt = session.get(ParseAttemptModel, parse_attempt_id)
            if (
                artifact is None
                or attempt is None
                or attempt.parse_artifact_id != artifact.id
                or artifact.status != "running"
                or attempt.status != "running"
            ):
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            artifact.status = "cancelled"
            artifact.updated_at = now
            attempt.status = "cancelled"
            attempt.finished_at = now
            operation.status = "cancelled"
            operation.cancel_requested_at = now
            operation.finished_at = now
            operation.result_summary_json = rfc8785.dumps(
                {
                    "parse_artifact_id": str(artifact.id),
                    "parse_attempt_id": str(attempt.id),
                    "status": "cancelled",
                }
            ).decode("utf-8")

    def register_parse_success(self, result: ParseSuccessDTO) -> None:
        self._validate_parse_operation(
            result.operation_id, result.parse_artifact_id, result.parse_attempt_id
        )
        document, canonical = self._validate_parse_success(result)
        self._promote_derived_output(result, canonical)
        try:
            with self._factory.begin() as session:
                repository = self._repository_factory(session)
                artifact, attempt, source_document = repository.register_parse_success(
                    result, document
                )
                workspace_id = self._required_workspace_id(session)
                warning_codes = sorted({warning["code"] for warning in document["warnings"]})
                payload = {
                    "parse_artifact_id": str(artifact.id),
                    "source_snapshot_id": str(artifact.source_snapshot_id),
                    "parse_attempt_id": str(attempt.id),
                    "block_count": source_document.block_count,
                    "warning_codes": warning_codes,
                }
                session.add(
                    self._system_event(
                        event_type="document.parse_succeeded",
                        workspace_id=workspace_id,
                        operation_id=result.operation_id,
                        aggregate_type="ParseArtifact",
                        aggregate_id=artifact.id,
                        payload=payload,
                        deduplication_key=f"document.parse_succeeded:{attempt.id}",
                    )
                )
                operation = self._required_running_operation(session, result.operation_id)
                operation.status = "completed"
                operation.result_summary_json = rfc8785.dumps(
                    {
                        "parse_artifact_id": str(artifact.id),
                        "parse_attempt_id": str(attempt.id),
                        "status": "succeeded",
                    }
                ).decode("utf-8")
                operation.error_code = None
                operation.finished_at = datetime.now(timezone.utc)
        except ValueError as exc:
            raise WriteCoordinatorError(str(exc)) from exc
        except IntegrityError as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc

    def register_parse_failure(self, result: ParseFailureDTO) -> None:
        self._validate_parse_operation(
            result.operation_id, result.parse_artifact_id, result.parse_attempt_id
        )
        try:
            with self._factory.begin() as session:
                repository = self._repository_factory(session)
                artifact, attempt = repository.register_parse_failure(result)
                workspace_id = self._required_workspace_id(session)
                payload = {
                    "parse_artifact_id": str(artifact.id),
                    "source_snapshot_id": str(artifact.source_snapshot_id),
                    "parse_attempt_id": str(attempt.id),
                    "error_code": result.error_code,
                }
                session.add(
                    self._system_event(
                        event_type="document.parse_failed",
                        workspace_id=workspace_id,
                        operation_id=result.operation_id,
                        aggregate_type="ParseArtifact",
                        aggregate_id=artifact.id,
                        payload=payload,
                        deduplication_key=f"document.parse_failed:{attempt.id}",
                    )
                )
                operation = self._required_running_operation(session, result.operation_id)
                operation.status = "failed"
                operation.result_summary_json = rfc8785.dumps(
                    {
                        "parse_artifact_id": str(artifact.id),
                        "parse_attempt_id": str(attempt.id),
                        "status": "failed",
                    }
                ).decode("utf-8")
                operation.error_code = result.error_code
                operation.finished_at = datetime.now(timezone.utc)
        except ValueError as exc:
            raise WriteCoordinatorError(str(exc)) from exc
        except IntegrityError as exc:
            raise WriteCoordinatorError("DATABASE_CONSTRAINT_VIOLATION") from exc

    def set_parse_preference(
        self, source_snapshot_id: UUID, parse_artifact_id: UUID, operation_id: UUID
    ) -> int:
        with self._factory.begin() as session:
            operation = self._required_running_operation(session, operation_id)
            artifact = session.get(ParseArtifactModel, parse_artifact_id)
            snapshot = session.get(SourceSnapshotModel, source_snapshot_id)
            if (
                snapshot is None
                or artifact is None
                or artifact.status != "succeeded"
                or artifact.source_snapshot_id != source_snapshot_id
            ):
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            preference = session.get(SnapshotParsePreferenceModel, source_snapshot_id)
            old_artifact_id = preference.parse_artifact_id if preference is not None else None
            now = datetime.now(timezone.utc)
            if preference is None:
                preference = SnapshotParsePreferenceModel(
                    source_snapshot_id=source_snapshot_id,
                    parse_artifact_id=parse_artifact_id,
                    row_version=1,
                    updated_at=now,
                    updated_by_operation_id=operation_id,
                )
                session.add(preference)
            else:
                preference.parse_artifact_id = parse_artifact_id
                preference.row_version += 1
                preference.updated_at = now
                preference.updated_by_operation_id = operation_id
            operation.status = "completed"
            operation.result_summary_json = rfc8785.dumps(
                {
                    "source_snapshot_id": str(source_snapshot_id),
                    "old_parse_artifact_id": (
                        str(old_artifact_id) if old_artifact_id is not None else None
                    ),
                    "new_parse_artifact_id": str(parse_artifact_id),
                }
            ).decode("utf-8")
            operation.error_code = None
            operation.finished_at = now
            session.flush()
            return preference.row_version

    def _validate_parse_success(
        self, result: ParseSuccessDTO
    ) -> tuple[dict[str, object], bytes]:
        document = _plain_json(result.parsed_document)
        if not isinstance(document, dict):
            raise ParseContractError("COMMAND_VALIDATION_FAILED")
        schema_path = Path(__file__).resolve().parents[4] / "contracts" / "parsed_document.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
        except ValidationError as exc:
            raise ParseContractError("COMMAND_VALIDATION_FAILED", exc.message) from exc

        with self._factory() as session:
            artifact = session.get(ParseArtifactModel, result.parse_artifact_id)
            snapshot = (
                session.get(SourceSnapshotModel, artifact.source_snapshot_id)
                if artifact is not None
                else None
            )
            if artifact is None or snapshot is None:
                raise ParseContractError("COMMAND_VALIDATION_FAILED")
            expected_parser = {
                "parser_id": artifact.parser_id,
                "parser_version": artifact.parser_version,
                "config_fingerprint": artifact.config_fingerprint,
                "contract_version": artifact.contract_version,
            }
            source = document["source"]
            if (
                document["parse_artifact_id"] != str(artifact.id)
                or document["parser"] != expected_parser
                or source["source_snapshot_id"] != str(snapshot.id)
                or source["sha256"] != snapshot.sha256
                or source["size_bytes"] != snapshot.size_bytes
                or source["mime_type"] != snapshot.mime_type
                or source["storage_relative_path"] != snapshot.storage_relative_path
                or [block["block_index"] for block in document["blocks"]]
                != list(range(len(document["blocks"])))
            ):
                raise ParseContractError("COMMAND_VALIDATION_FAILED")

        expected_relative = f"derived/parse/{result.parse_artifact_id}/parsed_document.json"
        relative = PurePosixPath(result.derived_relative_path)
        if (
            result.derived_relative_path != expected_relative
            or relative.is_absolute()
            or ".." in relative.parts
            or len(result.output_sha256) != 64
            or any(character not in "0123456789abcdef" for character in result.output_sha256)
        ):
            raise ParseContractError("COMMAND_VALIDATION_FAILED")
        canonical = rfc8785.dumps(document)
        if hashlib.sha256(canonical).hexdigest() != result.derived_file_sha256:
            raise ParseContractError("COMMAND_VALIDATION_FAILED")
        return document, canonical

    def _validate_parse_operation(
        self, operation_id: UUID, parse_artifact_id: UUID, parse_attempt_id: UUID
    ) -> None:
        with self._factory() as session:
            operation = session.get(BackgroundOperationModel, operation_id)
            if operation is None or operation.status != "running":
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
            try:
                summary = json.loads(operation.result_summary_json or "null")
            except json.JSONDecodeError as exc:
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED") from exc
            if not isinstance(summary, dict) or (
                summary.get("parse_artifact_id") != str(parse_artifact_id)
                or summary.get("parse_attempt_id") != str(parse_attempt_id)
                or summary.get("status") != "running"
            ):
                raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")

    def _promote_derived_output(self, result: ParseSuccessDTO, canonical: bytes) -> None:
        if self._data_directory is None:
            raise WriteCoordinatorError("COMMAND_VALIDATION_FAILED")
        final = self._data_directory / PurePosixPath(result.derived_relative_path)
        staging = (
            self._data_directory
            / "staging"
            / "parse"
            / str(result.parse_artifact_id)
            / f"{result.parse_attempt_id}.partial"
        )
        staging.parent.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(staging.parent)
        reject_reparse_chain(final.parent if final.parent.exists() else final.parent.parent)

        if final.exists() or final.is_symlink():
            if not _ordinary_file_with_hash(final, result.derived_file_sha256, len(canonical)):
                raise WriteCoordinatorError("SOURCE_UNSTABLE")
            return
        if staging.exists() or staging.is_symlink():
            if not _ordinary_file_with_hash(staging, result.derived_file_sha256, len(canonical)):
                raise WriteCoordinatorError("SOURCE_UNSTABLE")
        else:
            with staging.open("xb") as stream:
                stream.write(canonical)
                stream.flush()
            fsync_file_and_parent(staging)
        details = staging.stat(follow_symlinks=False)
        file_stat = FileStat(details.st_size, details.st_mtime_ns, None, str(details.st_dev))
        staged = StagedSource(
            staging,
            staging,
            result.derived_file_sha256,
            len(canonical),
            file_stat,
            file_stat,
        )
        outcome = promote_no_replace(staged, final)
        if outcome.state is PromotionState.RESUME_VERIFICATION:
            staging.unlink(missing_ok=True)
        elif outcome.state is not PromotionState.COMPLETED:
            raise WriteCoordinatorError("SOURCE_UNSTABLE")

    def _required_workspace_id(self, session: Session) -> UUID:
        workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
        if workspace_id is None:
            raise ValueError("WORKSPACE_METADATA_MISSING")
        return workspace_id

    def _required_running_operation(
        self, session: Session, operation_id: UUID
    ) -> BackgroundOperationModel:
        operation = session.get(BackgroundOperationModel, operation_id)
        if operation is None or operation.status != "running":
            raise ValueError("COMMAND_VALIDATION_FAILED")
        return operation

    @staticmethod
    def _system_event(
        *,
        event_type: str,
        workspace_id: UUID,
        operation_id: UUID,
        aggregate_type: str,
        aggregate_id: UUID,
        payload: dict[str, object],
        deduplication_key: str,
    ) -> DomainEventModel:
        now = datetime.now(timezone.utc)
        return DomainEventModel(
            id=uuid4(),
            schema_version="2.0",
            event_type=event_type,
            workspace_id=workspace_id,
            command_id=None,
            operation_id=operation_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=None,
            actor_type="system",
            payload_json=rfc8785.dumps(payload).decode("utf-8"),
            deduplication_key=deduplication_key,
            causation_id=None,
            correlation_id=operation_id,
            created_at=now,
            occurred_at=now,
            processed_at=None,
        )


def _plain_json(value: object) -> object:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


def _ordinary_file_with_hash(path: Path, expected_sha256: str, expected_size: int) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(details, "st_file_attributes", 0)
    return (
        stat.S_ISREG(details.st_mode)
        and not path.is_symlink()
        and not attributes & reparse_flag
        and details.st_size == expected_size
        and sha256_file(path) == expected_sha256
    )
