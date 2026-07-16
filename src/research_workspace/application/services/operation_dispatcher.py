"""Small outer dispatch boundary that authorizes before invoking a handler."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import threading
from typing import Callable, Generic, TypeVar
from uuid import UUID, uuid4

import rfc8785

from research_workspace.application.dto.import_dto import ImportCommitDTO, ImportRequest
from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
    ParseRequest,
    ParseSuccessDTO,
)
from research_workspace.application.ports.document_parser import DocumentParser
from research_workspace.application.ports.operation_runner import (
    DocumentParseWorkPlan,
    OperationRunner,
    SnapshotImportWorkPlan,
)
from research_workspace.application.ports.write_coordinator import (
    ParseOperationSeed,
    PreparedImportItem,
    PreparedParseAttempt,
    WriteCoordinator,
)
from research_workspace.application.services.import_orchestrator import (
    ImportOrchestrator,
    PreparedImportBatch,
    _mime_type,
    _permission_json,
)
from research_workspace.domain.parsing import (
    DEFAULT_PARSER_CONFIG,
    derived_file_sha256,
    semantic_output_sha256,
    validate_parsed_document_v2,
)
from research_workspace.infrastructure.workers.worker_signals import (
    ParseWorkerResult,
    SnapshotWorkerResult,
    WorkerCompleted,
)

from research_workspace.application.services.authorization import (
    AuthorizationFailure,
    AuthorizationRequest,
    authorize_request,
)
from research_workspace.domain.capabilities import PermissionContext

T = TypeVar("T")


@dataclass(frozen=True)
class DispatchResult(Generic[T]):
    value: T | None
    permission_context: PermissionContext | None
    error_code: str | None


class OperationDispatcher:
    def dispatch(
        self,
        request: AuthorizationRequest,
        handler: Callable[[PermissionContext], T],
    ) -> DispatchResult[T]:
        try:
            permission_context = authorize_request(request)
        except AuthorizationFailure as failure:
            return DispatchResult(None, None, failure.error_code)
        return DispatchResult(handler(permission_context), permission_context, None)

    def dispatch_context(
        self,
        context: PermissionContext,
        handler: Callable[[PermissionContext], T],
    ) -> DispatchResult[T]:
        raise ValueError("PermissionContext is not a reusable credential")


class ImportParseHandle:
    """Main-thread observable state for one bounded import/parse pipeline."""

    def __init__(self, owner_thread_id: int) -> None:
        self._owner_thread_id = owner_thread_id
        self._active = None
        self._cancel_requested = False
        self.done = False
        self.status = "running"
        self.completed_count = 0
        self.persistence_thread_ids: list[int] = []

    def bind(self, handle) -> None:
        self._active = handle
        if self._cancel_requested:
            handle.cancel()

    def record_persistence(self) -> None:
        current = threading.get_ident()
        if current != self._owner_thread_id:
            raise RuntimeError("PERSISTENCE_OUTSIDE_OWNER_THREAD")
        self.persistence_thread_ids.append(current)

    @property
    def cancelled(self) -> bool:
        return self._cancel_requested

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._active is not None:
            self._active.cancel()

    def finish(self, status: str) -> None:
        if self.done:
            return
        self.status = status
        self.done = True
        if status == "completed":
            self.completed_count += 1

    def shutdown(self, timeout: float | None = None) -> bool:
        self.cancel()
        return True if self._active is None else self._active.shutdown(timeout)


@dataclass(slots=True)
class _PipelineState:
    batch: PreparedImportBatch
    handle: ImportParseHandle
    import_index: int = 0
    parse_index: int = 0
    successes: list[ImportCommitDTO] = field(default_factory=list)
    materialized: list[tuple[PreparedImportItem, ImportCommitDTO, object]] = field(default_factory=list)
    failed: list[UUID] = field(default_factory=list)
    cancelled: list[UUID] = field(default_factory=list)
    parse_failed: list[UUID] = field(default_factory=list)
    active_parse: PreparedParseAttempt | None = None
    active_parse_item: PreparedImportItem | None = None

class ImportParsePipeline:
    """Application-owned sequencing; workers only compute immutable results."""

    def __init__(
        self,
        workspace_root: Path,
        imports: ImportOrchestrator,
        coordinator: WriteCoordinator,
        runner: OperationRunner,
        parsers: tuple[DocumentParser, ...],
    ) -> None:
        self._workspace_root = workspace_root
        self._imports = imports
        self._coordinator = coordinator
        self._runner = runner
        self._parsers = tuple(parsers)

    def start(self, request: ImportRequest) -> ImportParseHandle:
        if (
            "document.parse.request" not in request.permission_context.capabilities
            or request.permission_context.network_allowed is not False
        ):
            raise ValueError("COMMAND_PERMISSION_DENIED")
        owner = threading.get_ident()
        batch = self._imports.prepare(request)
        state = _PipelineState(batch, ImportParseHandle(owner))
        self._start_next_import(state)
        return state.handle

    def _start_next_import(self, state: _PipelineState) -> None:
        if state.handle.cancelled:
            self._cancel_remaining_imports(state)
            return
        if state.import_index >= len(state.batch.items):
            state.handle.record_persistence()
            self._coordinator.mark_import_batch_parsing(
                state.batch.operation_id, state.batch.batch_id
            )
            self._start_next_parse(state)
            return
        item = state.batch.items[state.import_index]
        state.import_index += 1
        try:
            source = self._imports.resolve_authorized(item.source_path, state.batch.request)
        except Exception:
            state.handle.record_persistence()
            self._coordinator.mark_import_item(item.item_id, "failed", "SOURCE_PATH_UNSAFE")
            state.failed.append(item.item_id)
            self._start_next_import(state)
            return
        worker_handle = self._runner.start(
            SnapshotImportWorkPlan(state.batch.operation_id, item.item_id, source)
        )
        state.handle.bind(worker_handle)
        worker_handle.on_completed(lambda terminal: self._import_completed(state, item, terminal))
        worker_handle.on_failed(lambda terminal: self._import_failed(state, item, terminal.error_code))
        worker_handle.on_cancelled(lambda _terminal: self._import_cancelled(state, item))

    def _import_completed(
        self, state: _PipelineState, item: PreparedImportItem, terminal: WorkerCompleted
    ) -> None:
        if state.handle.cancelled:
            self._import_cancelled(state, item)
            return
        result = terminal.result
        if not isinstance(result, SnapshotWorkerResult):
            self._import_failed(state, item, "COMMAND_VALIDATION_FAILED")
            return
        try:
            state.handle.record_persistence()
            committed = self._imports.register_materialized(state.batch, item, result.materialized)
        except Exception:
            self._import_failed(state, item, "DATABASE_OPERATION_FAILED")
            return
        state.successes.append(committed)
        state.materialized.append((item, committed, result.materialized))
        self._start_next_import(state)

    def _import_failed(self, state: _PipelineState, item: PreparedImportItem, error_code: str) -> None:
        state.handle.record_persistence()
        self._coordinator.mark_import_item(item.item_id, "failed", error_code)
        state.failed.append(item.item_id)
        self._start_next_import(state)

    def _import_cancelled(self, state: _PipelineState, item: PreparedImportItem) -> None:
        state.handle.record_persistence()
        self._coordinator.mark_import_item(item.item_id, "cancelled", None)
        state.cancelled.append(item.item_id)
        self._cancel_remaining_imports(state)

    def _cancel_remaining_imports(self, state: _PipelineState) -> None:
        for item in state.batch.items[state.import_index:]:
            state.handle.record_persistence()
            self._coordinator.mark_import_item(item.item_id, "cancelled", None)
            state.cancelled.append(item.item_id)
        state.import_index = len(state.batch.items)
        state.handle.record_persistence()
        self._imports.finalize(state.batch, state.successes, state.failed, state.cancelled)
        state.handle.finish("cancelled")

    def _start_next_parse(self, state: _PipelineState) -> None:
        if state.handle.cancelled:
            state.handle.finish("cancelled")
            return
        if state.parse_index >= len(state.materialized):
            state.handle.record_persistence()
            self._imports.finalize(
                state.batch,
                state.successes,
                state.failed,
                state.cancelled,
                state.parse_failed,
            )
            state.handle.finish(
                "completed_with_failures" if state.failed or state.parse_failed else "completed"
            )
            return
        item, committed, materialized = state.materialized[state.parse_index]
        state.parse_index += 1
        mime_type = _mime_type(item.source_path)
        parser = next((candidate for candidate in self._parsers if mime_type in candidate.supported_mime_types), None)
        if parser is None:
            state.handle.record_persistence()
            self._coordinator.mark_import_parse_result(
                item.item_id, None, "failed", "UNSUPPORTED_CONFIGURATION"
            )
            state.parse_failed.append(item.item_id)
            self._start_next_parse(state)
            return
        operation_id, proposed_artifact_id, attempt_id = uuid4(), uuid4(), uuid4()
        seed = ParseAttemptSeed(
            operation_id,
            proposed_artifact_id,
            attempt_id,
            committed.snapshot_id,
            parser.parser_id,
            parser.parser_version,
            DEFAULT_PARSER_CONFIG,
            "2.0",
            "gate1-worker-1.0",
        )
        fingerprint = hashlib.sha256(
            rfc8785.dumps(
                {
                    "operation_type": "document_parse",
                    "source_snapshot_id": str(committed.snapshot_id),
                    "parser_id": parser.parser_id,
                    "parser_version": parser.parser_version,
                }
            )
        ).hexdigest()
        state.handle.record_persistence()
        prepared = self._coordinator.begin_parse_operation(
            ParseOperationSeed(seed, fingerprint, _permission_json(state.batch.request))
        )
        state.active_parse = prepared
        state.active_parse_item = item
        self._coordinator.mark_import_parse_result(
            item.item_id, prepared.parse_artifact_id, "pending", None
        )
        request = ParseRequest(
            prepared.parse_artifact_id,
            committed.snapshot_id,
            self._workspace_root / materialized.storage_relative_path,
            materialized.sha256,
            mime_type,
            DEFAULT_PARSER_CONFIG,
        )
        worker_handle = self._runner.start(
            DocumentParseWorkPlan(operation_id, parser.parser_id, request)
        )
        state.handle.bind(worker_handle)
        worker_handle.on_completed(lambda terminal: self._parse_completed(state, terminal))
        worker_handle.on_failed(lambda terminal: self._parse_failed(state, terminal.error_code))
        worker_handle.on_cancelled(lambda _terminal: self._parse_cancelled(state))

    def _parse_completed(self, state: _PipelineState, terminal: WorkerCompleted) -> None:
        if state.handle.cancelled:
            self._parse_cancelled(state)
            return
        payload = terminal.result
        if not isinstance(payload, ParseWorkerResult):
            self._parse_failed(state, "COMMAND_VALIDATION_FAILED")
            return
        result = payload.parse_result
        prepared, item = state.active_parse, state.active_parse_item
        if prepared is None or item is None:
            self._parse_failed(state, "COMMAND_VALIDATION_FAILED")
            return
        state.handle.record_persistence()
        if result.error_code is not None or result.parsed_document is None:
            error_code = result.error_code or "PARSED_DOCUMENT_CONTRACT_INVALID"
            self._coordinator.register_parse_failure(
                ParseFailureDTO(
                    prepared.operation_id,
                    prepared.parse_artifact_id,
                    prepared.parse_attempt_id,
                    error_code,
                    result.warning_codes,
                )
            )
            self._coordinator.mark_import_parse_result(
                item.item_id, prepared.parse_artifact_id, "failed", error_code
            )
            state.parse_failed.append(item.item_id)
        else:
            validate_parsed_document_v2(result.parsed_document)
            success = ParseSuccessDTO(
                prepared.operation_id,
                prepared.parse_artifact_id,
                prepared.parse_attempt_id,
                result.parsed_document,
                semantic_output_sha256(result.parsed_document),
                derived_file_sha256(result.parsed_document),
                f"derived/parse/{prepared.parse_artifact_id}/parsed_document.json",
            )
            self._coordinator.register_parse_success(success)
            self._coordinator.mark_import_parse_result(
                item.item_id, prepared.parse_artifact_id, "succeeded", None
            )
        state.active_parse = None
        state.active_parse_item = None
        self._start_next_parse(state)

    def _parse_failed(self, state: _PipelineState, error_code: str) -> None:
        prepared, item = state.active_parse, state.active_parse_item
        if prepared is None or item is None:
            state.handle.finish("failed")
            return
        state.handle.record_persistence()
        self._coordinator.register_parse_failure(
            ParseFailureDTO(
                prepared.operation_id,
                prepared.parse_artifact_id,
                prepared.parse_attempt_id,
                error_code,
                (),
            )
        )
        self._coordinator.mark_import_parse_result(
            item.item_id, prepared.parse_artifact_id, "failed", error_code
        )
        state.parse_failed.append(item.item_id)
        state.active_parse = None
        state.active_parse_item = None
        self._start_next_parse(state)

    def _parse_cancelled(self, state: _PipelineState) -> None:
        prepared, item = state.active_parse, state.active_parse_item
        if prepared is not None and item is not None:
            state.handle.record_persistence()
            self._coordinator.cancel_parse_attempt(
                prepared.operation_id, prepared.parse_artifact_id, prepared.parse_attempt_id
            )
            self._coordinator.mark_import_parse_result(
                item.item_id, prepared.parse_artifact_id, "cancelled", None
            )
            state.cancelled.append(item.item_id)
            state.handle.record_persistence()
            self._imports.finalize(
                state.batch,
                state.successes,
                state.failed,
                state.cancelled,
                state.parse_failed,
            )
        state.handle.finish("cancelled")
