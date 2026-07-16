"""Deterministic synchronous import orchestration; parsing is intentionally absent."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import mimetypes
from pathlib import Path
from typing import Literal
from uuid import uuid4

import rfc8785

from research_workspace.application.dto.import_dto import (
    ImportBatchResult,
    ImportCommitDTO,
    ImportRequest,
    SnapshotRegistrationDTO,
)
from research_workspace.application.ports.write_coordinator import (
    ImportBatchSeed,
    ImportItemSeed,
    WriteCoordinator,
)
from research_workspace.infrastructure.filesystem.path_safety import (
    SourceFailure,
    normalize_path_text,
    normalized_path_hash,
    resolve_safe_external_source,
)
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore


def public_import_outcome(
    state: str,
) -> Literal["imported", "failed"] | None:
    if state in {"imported", "duplicate_content"}:
        return "imported"
    if state == "failed":
        return "failed"
    return None


def _permission_json(request: ImportRequest) -> str:
    context = request.permission_context
    data = {
        "schema_version": context.schema_version,
        "actor_type": context.actor_type,
        "actor_id": context.actor_id,
        "workspace_id": str(context.workspace_id),
        "capabilities": list(context.capabilities),
        "scope_refs": list(context.scope_refs),
        "path_scopes": [
            {
                "scope_type": scope.scope_type,
                "normalized_path_hash": scope.normalized_path_hash,
                "root_id": str(scope.root_id),
                "access_mode": scope.access_mode,
                "recursive": scope.recursive,
            }
            for scope in context.path_scopes
        ],
        "network_allowed": False,
        "granted_at": context.granted_at.isoformat().replace("+00:00", "Z"),
        "policy_version": context.policy_version,
        "authorization_decision_id": str(context.authorization_decision_id),
    }
    return rfc8785.dumps(data).decode("utf-8")


def _work_plan_fingerprint(request: ImportRequest) -> str:
    path_hashes = [normalized_path_hash(path) for path in request.source_paths]
    canonical = rfc8785.dumps({"operation_type": "snapshot_import", "path_hashes": path_hashes})
    return hashlib.sha256(canonical).hexdigest()


def _item_seed(path: Path) -> ImportItemSeed:
    absolute = path.expanduser().resolve(strict=False)
    try:
        details = path.stat()
    except OSError:
        details = None
    return ImportItemSeed(
        uuid4(),
        uuid4(),
        absolute,
        normalize_path_text(absolute),
        normalized_path_hash(absolute),
        absolute.name,
        details.st_size if details is not None else None,
        details.st_mtime_ns if details is not None else None,
        str(details.st_ino) if details is not None and details.st_ino else None,
        str(details.st_dev) if details is not None else None,
    )


def _mime_type(path: Path) -> str:
    known = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return known.get(path.suffix.casefold(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")


class ImportOrchestrator:
    def __init__(self, workspace_root: Path, snapshots: SnapshotStore, coordinator: WriteCoordinator) -> None:
        self._workspace_root = workspace_root
        self._snapshots = snapshots
        self._coordinator = coordinator

    def execute(
        self,
        request: ImportRequest,
        *,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> ImportBatchResult:
        if "source.snapshot_import.request" not in request.permission_context.capabilities:
            raise SourceFailure("COMMAND_PERMISSION_DENIED")
        if request.permission_context.network_allowed is not False:
            raise SourceFailure("COMMAND_PERMISSION_DENIED")
        if request.permission_context.workspace_id != self._coordinator.workspace_id():
            raise SourceFailure("COMMAND_PERMISSION_DENIED")

        operation_id = uuid4()
        batch_id = uuid4()
        seeds = tuple(_item_seed(path) for path in request.source_paths)
        prepared = self._coordinator.begin_import(
            ImportBatchSeed(
                operation_id,
                batch_id,
                _work_plan_fingerprint(request),
                _permission_json(request),
                seeds,
                sum(seed.size_bytes or 0 for seed in seeds),
            )
        )
        successes: list[ImportCommitDTO] = []
        failed: list = []
        cancelled: list = []

        for index, item in enumerate(prepared):
            if cancel_requested():
                for remaining in prepared[index:]:
                    self._coordinator.mark_import_item(remaining.item_id, "cancelled", None)
                    cancelled.append(remaining.item_id)
                break
            try:
                source = self._resolve_authorized(item.source_path, request)
                materialized = self._snapshots.materialize(source, item.item_id)
                registration = SnapshotRegistrationDTO(
                    operation_id,
                    batch_id,
                    item.item_id,
                    item.observation_id,
                    uuid4(),
                    source,
                    source.name,
                    materialized.sha256,
                    materialized.size_bytes,
                    _mime_type(source),
                    materialized.storage_relative_path,
                    materialized.physical_file_reused,
                )
                successes.append(self._coordinator.register_import(registration))
            except SourceFailure as exc:
                self._coordinator.mark_import_item(item.item_id, "failed", exc.error_code)
                failed.append(item.item_id)
            except Exception:
                self._coordinator.mark_import_item(item.item_id, "failed", "DATABASE_OPERATION_FAILED")
                failed.append(item.item_id)

        if cancelled:
            batch_status = "cancelled"
        elif successes and failed:
            batch_status = "completed_with_failures"
        elif failed:
            batch_status = "failed"
        else:
            batch_status = "completed"
        summary = rfc8785.dumps(
            {
                "selected_count": len(prepared),
                "imported_count": len(successes),
                "failed_count": len(failed),
                "cancelled_count": len(cancelled),
            }
        ).decode("utf-8")
        self._coordinator.finalize_import(operation_id, batch_id, batch_status, summary)
        return ImportBatchResult(batch_id, operation_id, tuple(successes), tuple(failed), tuple(cancelled))

    def _resolve_authorized(self, path: Path, request: ImportRequest) -> Path:
        last_failure: SourceFailure | None = None
        for scope in request.permission_context.path_scopes:
            try:
                return resolve_safe_external_source(path, scope, self._workspace_root)
            except SourceFailure as exc:
                last_failure = exc
                if exc.error_code == "SOURCE_REPARSE_POINT":
                    raise
        raise last_failure or SourceFailure("SOURCE_PATH_UNSAFE")
