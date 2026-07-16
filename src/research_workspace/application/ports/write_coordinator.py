"""Framework-free persistent-write boundary."""

from dataclasses import dataclass
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
