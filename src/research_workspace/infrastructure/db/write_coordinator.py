"""The sole Gate 1 SQLite transaction owner for approved database facts."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Callable
from uuid import uuid4

import rfc8785
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import ParseFailureDTO, ParseSuccessDTO
from research_workspace.infrastructure.db.models import DomainEventModel, WorkspaceMetadataModel
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

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO:
        try:
            with self._factory.begin() as session:
                repository = self._repository_factory(session)
                committed = repository.register_import(result)
                workspace_id = session.scalar(select(WorkspaceMetadataModel.workspace_id))
                if workspace_id is None:
                    raise WriteCoordinatorError("WORKSPACE_METADATA_MISSING")
                event_type = (
                    "source.snapshot_reused" if result.duplicate_content
                    else "source.snapshot_imported"
                )
                payload = {
                    "snapshot_id": str(result.snapshot_id),
                    "source_observation_id": str(result.source_observation_id),
                    "import_item_id": str(result.import_item_id),
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
                        aggregate_id=result.snapshot_id,
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

    def register_parse_success(self, result: ParseSuccessDTO) -> None:
        raise WriteCoordinatorError("PARSE_REGISTRATION_NOT_AVAILABLE")

    def register_parse_failure(self, result: ParseFailureDTO) -> None:
        raise WriteCoordinatorError("PARSE_REGISTRATION_NOT_AVAILABLE")
