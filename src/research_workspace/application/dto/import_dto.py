"""Immutable import DTOs fixed by the Gate 1 Interface Ledger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from research_workspace.domain.capabilities import PermissionContext


@dataclass(frozen=True)
class ImportRequest:
    source_paths: tuple[Path, ...]
    permission_context: PermissionContext

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_paths", tuple(self.source_paths))


@dataclass(frozen=True)
class SnapshotRegistrationDTO:
    operation_id: UUID
    batch_id: UUID
    import_item_id: UUID
    source_observation_id: UUID
    snapshot_id: UUID
    source_path: Path
    original_filename: str
    sha256: str
    size_bytes: int
    mime_type: str
    storage_relative_path: str
    duplicate_content: bool


@dataclass(frozen=True)
class ImportCommitDTO:
    snapshot_id: UUID
    source_observation_id: UUID
    import_item_id: UUID
    state: Literal["imported", "duplicate_content"]


@dataclass(frozen=True)
class ImportBatchResult:
    batch_id: UUID
    operation_id: UUID
    item_results: tuple[ImportCommitDTO, ...]
    failed_item_ids: tuple[UUID, ...]
    cancelled_item_ids: tuple[UUID, ...]
