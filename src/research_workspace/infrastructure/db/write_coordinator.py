"""The sole Gate 1 SQLite transaction owner for approved database facts."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Callable
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.ports.write_coordinator import (
    ImportBatchSeed,
    PreparedImportItem,
)
from research_workspace.application.dto.parsing_dto import ParseFailureDTO, ParseSuccessDTO
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    ImportBatchModel,
    ImportItemModel,
    SourceObservationModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.repositories import SqlGate1WriteRepository


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
    ) -> None:
        self._factory = factory
        self._repository_factory = repository_factory

    def workspace_id(self) -> UUID:
        with self._factory() as session:
            workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
        if workspace_id is None:
            raise WriteCoordinatorError("WORKSPACE_METADATA_MISSING")
        return workspace_id

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

    def register_parse_success(self, result: ParseSuccessDTO) -> None:
        raise WriteCoordinatorError("PARSE_REGISTRATION_NOT_AVAILABLE")

    def register_parse_failure(self, result: ParseFailureDTO) -> None:
        raise WriteCoordinatorError("PARSE_REGISTRATION_NOT_AVAILABLE")
