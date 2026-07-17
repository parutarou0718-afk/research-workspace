"""SQLite Online Backup and deterministic two-slot physical rotation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from uuid import UUID, uuid4

import rfc8785

from research_workspace.application.dto.recovery_dto import (
    RecoveryPlan,
    RecoveryProgress,
    VerifiedRecoveryPoint,
)
from research_workspace.application.ports.operation_runner import CancellationToken
from research_workspace.application.services.recovery_points import RecoveryPointError
from research_workspace.infrastructure.filesystem.atomic_files import fsync_parent_directory


class PhysicalRecoveryState(str, Enum):
    EMPTY = "empty"
    CURRENT_VERIFIED = "current_verified"
    CURRENT_AND_PREVIOUS_VERIFIED = "current_and_previous_verified"
    MANUAL_ATTENTION_REQUIRED = "manual_attention_required"


@dataclass(frozen=True, slots=True)
class RecoveryReconciliation:
    state: PhysicalRecoveryState
    current_generation: int | None
    previous_generation: int | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _flush_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _verified_manifest(directory: Path) -> dict[str, object] | None:
    manifest_path = directory / "manifest.json"
    digest_path = directory / "manifest.sha256"
    database_path = directory / "workspace.db"
    if not all(path.is_file() for path in (manifest_path, digest_path, database_path)):
        return None
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest_path.read_text("ascii").strip():
        return None
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("generation"), int)
        or manifest.get("database_sha256") != _sha256(database_path)
    ):
        return None
    return manifest


def reconcile_recovery_directories(recovery_directory: Path) -> RecoveryReconciliation:
    current = _verified_manifest(recovery_directory / "current")
    previous = _verified_manifest(recovery_directory / "previous")
    if current is None:
        staging = sorted(
            (
                (manifest, path)
                for path in recovery_directory.glob("staging-*")
                if (manifest := _verified_manifest(path)) is not None
            ),
            key=lambda item: int(item[0]["generation"]),
            reverse=True,
        )
        if staging and (
            previous is None
            or int(staging[0][0]["generation"]) > int(previous["generation"])
        ):
            selected, path = staging[0]
            os.rename(path, recovery_directory / "current")
            fsync_parent_directory(recovery_directory)
            return RecoveryReconciliation(
                (
                    PhysicalRecoveryState.CURRENT_AND_PREVIOUS_VERIFIED
                    if previous is not None
                    else PhysicalRecoveryState.CURRENT_VERIFIED
                ),
                int(selected["generation"]),
                int(previous["generation"]) if previous is not None else None,
            )
        if previous is not None and not (recovery_directory / "current").exists():
            os.rename(recovery_directory / "previous", recovery_directory / "current")
            fsync_parent_directory(recovery_directory)
            return RecoveryReconciliation(
                PhysicalRecoveryState.CURRENT_VERIFIED,
                int(previous["generation"]),
                None,
            )
        state = PhysicalRecoveryState.EMPTY if not recovery_directory.exists() else PhysicalRecoveryState.MANUAL_ATTENTION_REQUIRED
        return RecoveryReconciliation(state, None, None)
    current_generation = int(current["generation"])
    previous_generation = int(previous["generation"]) if previous is not None else None
    state = (
        PhysicalRecoveryState.CURRENT_AND_PREVIOUS_VERIFIED
        if previous_generation is not None
        else PhysicalRecoveryState.CURRENT_VERIFIED
    )
    return RecoveryReconciliation(state, current_generation, previous_generation)


class SQLiteRecoveryAdapter:
    """Performs bounded file/SQLite work; it owns no ORM Session or Qt object."""

    def create_verified_recovery(
        self,
        plan: RecoveryPlan,
        generation: int,
        report_progress,
        cancellation: CancellationToken,
    ) -> VerifiedRecoveryPoint:
        database_path = plan.database_path.resolve()
        data_directory = database_path.parent
        recovery_directory = plan.recovery_root.resolve()
        if recovery_directory.parent != data_directory:
            raise RecoveryPointError()
        self._database_path = database_path
        self._data_directory = data_directory
        self._recovery_directory = recovery_directory
        existing = _verified_manifest(self._recovery_directory / "current")
        if existing is not None and int(existing["generation"]) >= generation:
            if (
                existing.get("command_id") == str(plan.command_id)
                and existing.get("request_fingerprint") == plan.request_fingerprint
            ):
                return self._point_from_manifest(existing)
            raise RecoveryPointError()
        point_id = plan.recovery_point_id
        # Rotation candidates are direct siblings so every rename remains a
        # same-parent, same-volume metadata operation.
        staging = self._recovery_directory / f"staging-{point_id}"
        staging.mkdir(parents=True, exist_ok=False)
        database_copy = staging / "workspace.db"
        try:
            report_progress(RecoveryProgress("copying", 0, self._database_path.stat().st_size))
            with closing(sqlite3.connect(self._database_path)) as source:
                with closing(sqlite3.connect(database_copy)) as target:
                    source.backup(target)
                    target.commit()
            _flush_file(database_copy)
            report_progress(RecoveryProgress("verifying", database_copy.stat().st_size, database_copy.stat().st_size))
            manifest = self._build_manifest(database_copy, plan, point_id, generation)
            manifest_bytes = rfc8785.dumps(manifest)
            manifest_path = staging / "manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            _flush_file(manifest_path)
            manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
            digest_path = staging / "manifest.sha256"
            digest_path.write_text(manifest_digest, "ascii")
            _flush_file(digest_path)
            fsync_parent_directory(staging)
            if _verified_manifest(staging) is None:
                raise RecoveryPointError()
            if cancellation.cancelled:
                raise RecoveryPointError("RECOVERY_POINT_CANCELLED")
            report_progress(RecoveryProgress("promoting", database_copy.stat().st_size, database_copy.stat().st_size))
            self._rotate(staging)
        except Exception as exc:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, RecoveryPointError):
                raise
            raise RecoveryPointError() from exc
        return VerifiedRecoveryPoint(
            point_id,
            plan.command_id,
            generation,
            str(manifest["database_sha256"]),
            int(manifest["snapshot_count"]),
            str(manifest["snapshot_manifest_hash"]),
            manifest_bytes,
            "current",
        )

    def _point_from_manifest(self, manifest: dict[str, object]) -> VerifiedRecoveryPoint:
        return VerifiedRecoveryPoint(
            UUID(str(manifest["recovery_point_id"])),
            UUID(str(manifest["command_id"])),
            int(manifest["generation"]),
            str(manifest["database_sha256"]),
            int(manifest["snapshot_count"]),
            str(manifest["snapshot_manifest_hash"]),
            rfc8785.dumps(manifest),
            "current",
        )

    def _build_manifest(
        self,
        database_copy: Path,
        plan: RecoveryPlan,
        point_id: UUID,
        generation: int,
    ) -> dict[str, object]:
        with closing(sqlite3.connect(database_copy)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if (
                integrity != ("ok",)
                or revision != (plan.schema_revision.split("_", 1)[0],)
            ):
                raise RecoveryPointError()
            required = {"application_commands", "recovery_points", "source_snapshots"}
            if not required <= tables:
                raise RecoveryPointError()
            rows = connection.execute(
                "SELECT id,sha256,size_bytes,storage_relative_path "
                "FROM source_snapshots ORDER BY id"
            ).fetchall()
        inventory: list[dict[str, object]] = []
        for snapshot_id, sha256, size_bytes, relative_path in rows:
            pure = PurePosixPath(relative_path)
            if pure.is_absolute() or ".." in pure.parts:
                raise RecoveryPointError()
            path = self._data_directory.joinpath(*pure.parts)
            if not path.is_file() or path.stat().st_size != size_bytes:
                raise RecoveryPointError()
            inventory.append(
                {
                    "id": snapshot_id,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "storage_relative_path": relative_path,
                }
            )
        inventory_bytes = rfc8785.dumps(inventory)
        return {
            "schema_version": "1.0",
            "recovery_point_id": str(point_id),
            "command_id": str(plan.command_id),
            "command_type": plan.command_type,
            "request_fingerprint": plan.request_fingerprint,
            "generation": generation,
            "schema_revision": plan.schema_revision,
            "database_sha256": _sha256(database_copy),
            "snapshot_count": len(inventory),
            "snapshot_manifest_hash": hashlib.sha256(inventory_bytes).hexdigest(),
            "snapshot_inventory": inventory,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _rotate(self, staging: Path) -> None:
        self._recovery_directory.mkdir(parents=True, exist_ok=True)
        current = self._recovery_directory / "current"
        previous = self._recovery_directory / "previous"
        retired = self._recovery_directory / f"retired-{uuid4()}"
        if previous.exists():
            os.rename(previous, retired)
        if current.exists():
            os.rename(current, previous)
        os.rename(staging, current)
        fsync_parent_directory(self._recovery_directory)
        if retired.exists():
            shutil.rmtree(retired)
