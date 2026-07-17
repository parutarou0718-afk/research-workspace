"""Immutable DTOs for verified pre-command SQLite recovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    recovery_point_id: UUID
    command_id: UUID
    command_type: str
    request_fingerprint: str
    workspace_id: UUID
    database_path: Path
    recovery_root: Path
    schema_revision: Literal["0004_gate3_protected_crud"]

    def __post_init__(self) -> None:
        if len(self.request_fingerprint) != 64 or any(
            value not in "0123456789abcdef" for value in self.request_fingerprint
        ):
            raise ValueError("request_fingerprint must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class RecoveryProgress:
    phase: Literal["copying", "verifying", "promoting"]
    bytes_done: int
    bytes_total: int


@dataclass(frozen=True, slots=True)
class VerifiedRecoveryPoint:
    recovery_point_id: UUID
    command_id: UUID
    generation: int
    database_sha256: str
    snapshot_count: int
    snapshot_manifest_hash: str
    manifest_bytes: bytes
    promoted_slot: Literal["current"]

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("generation must be positive")
        if not isinstance(self.manifest_bytes, bytes):
            raise TypeError("manifest_bytes must be immutable canonical bytes")
