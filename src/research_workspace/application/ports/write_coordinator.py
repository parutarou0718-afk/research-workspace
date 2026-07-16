"""Framework-free persistent-write boundary."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from research_workspace.application.dto.import_dto import ImportCommitDTO, SnapshotRegistrationDTO
from research_workspace.application.dto.parsing_dto import ParseFailureDTO, ParseSuccessDTO


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


class WriteCoordinator(Protocol):
    def workspace_id(self) -> UUID: ...

    def begin_import(self, seed: ImportBatchSeed) -> tuple[PreparedImportItem, ...]: ...

    def register_import(self, result: SnapshotRegistrationDTO) -> ImportCommitDTO: ...

    def mark_import_item(self, item_id: UUID, state: str, error_code: str | None) -> None: ...

    def finalize_import(
        self, operation_id: UUID, batch_id: UUID, batch_status: str, result_summary_json: str
    ) -> None: ...

    def register_parse_success(self, result: ParseSuccessDTO) -> None: ...

    def register_parse_failure(self, result: ParseFailureDTO) -> None: ...
