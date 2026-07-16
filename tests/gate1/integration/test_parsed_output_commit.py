from __future__ import annotations

import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from research_workspace.application.dto.parsing_dto import ParseAttemptSeed
from research_workspace.domain.parsing import DEFAULT_PARSER_CONFIG, ParseContractError
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    ParseArtifactModel,
    ParseAttemptModel,
    ParsedBlockModel,
    SourceDocumentModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.db.write_coordinator import WriteCoordinatorError

def _operation(operation_id: UUID) -> BackgroundOperationModel:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return BackgroundOperationModel(
        id=operation_id,
        operation_type="document_parse",
        status="running",
        work_plan_fingerprint="f" * 64,
        permission_context_json="{}",
        result_summary_json=None,
        error_code=None,
        created_at=now,
        started_at=now,
        finished_at=None,
        cancel_requested_at=None,
    )


def _seed(snapshot_id: UUID, operation_id: UUID, artifact_id: UUID, attempt_id: UUID):
    return ParseAttemptSeed(
        operation_id,
        artifact_id,
        attempt_id,
        snapshot_id,
        "pypdf",
        "6.14.2",
        DEFAULT_PARSER_CONFIG,
        "2.0",
        "gate1-test",
    )


def _start(coordinator, factory, snapshot_id: UUID):
    operation_id, artifact_id, attempt_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add(_operation(operation_id))
    prepared = coordinator.start_parse_attempt(
        _seed(snapshot_id, operation_id, artifact_id, attempt_id)
    )
    return operation_id, prepared


def test_invalid_block_rolls_back_success_and_creates_no_derived_file(
    parse_database, minimal_parsed_document
) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, prepared = _start(coordinator, factory, snapshot_id)
    invalid = minimal_parsed_document.success_dto(
        workspace,
        operation_id,
        prepared.parse_artifact_id,
        prepared.parse_attempt_id,
        snapshot_id,
        change=lambda document: document["blocks"][0].pop("text"),
    )

    with pytest.raises(ParseContractError):
        coordinator.register_parse_success(invalid)

    final = workspace / invalid.derived_relative_path
    assert not final.exists()
    with factory() as session:
        artifact = session.get(ParseArtifactModel, prepared.parse_artifact_id)
        attempt = session.get(ParseAttemptModel, prepared.parse_attempt_id)
        assert (artifact.status, attempt.status) == ("running", "running")
        assert session.scalar(select(SourceDocumentModel)) is None
        assert session.scalar(select(ParsedBlockModel)) is None
        assert session.scalar(
            select(DomainEventModel).where(DomainEventModel.event_type == "document.parse_succeeded")
        ) is None


def test_success_registers_file_document_blocks_and_event_together(
    parse_database, minimal_parsed_document
) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, prepared = _start(coordinator, factory, snapshot_id)
    success = minimal_parsed_document.success_dto(
        workspace, operation_id, prepared.parse_artifact_id, prepared.parse_attempt_id, snapshot_id
    )

    coordinator.register_parse_success(success)

    final = workspace / success.derived_relative_path
    assert final.is_file()
    assert json.loads(final.read_text(encoding="utf-8"))["parse_artifact_id"] == str(
        prepared.parse_artifact_id
    )
    with factory() as session:
        artifact = session.get(ParseArtifactModel, prepared.parse_artifact_id)
        attempt = session.get(ParseAttemptModel, prepared.parse_attempt_id)
        document = session.scalar(select(SourceDocumentModel))
        blocks = session.scalars(select(ParsedBlockModel)).all()
        event_row = session.scalar(
            select(DomainEventModel).where(DomainEventModel.event_type == "document.parse_succeeded")
        )
        assert artifact.status == attempt.status == "succeeded"
        assert artifact.successful_attempt_id == attempt.id
        assert document.block_count == len(blocks) == 1
        assert event_row is not None
        assert set(json.loads(event_row.payload_json)) == {
            "parse_artifact_id",
            "source_snapshot_id",
            "parse_attempt_id",
            "block_count",
            "warning_codes",
        }


def test_promoted_file_is_unreachable_after_database_failure_and_restart_can_reconcile(
    parse_database, minimal_parsed_document
) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, prepared = _start(coordinator, factory, snapshot_id)
    success = minimal_parsed_document.success_dto(
        workspace, operation_id, prepared.parse_artifact_id, prepared.parse_attempt_id, snapshot_id
    )

    def fail_event(_mapper, _connection, target):
        if target.event_type == "document.parse_succeeded":
            raise RuntimeError("injected parse event failure")

    event.listen(DomainEventModel, "before_insert", fail_event)
    try:
        with pytest.raises(RuntimeError, match="injected parse event failure"):
            coordinator.register_parse_success(success)
    finally:
        event.remove(DomainEventModel, "before_insert", fail_event)

    final = workspace / success.derived_relative_path
    assert final.is_file()
    with factory() as session:
        artifact = session.get(ParseArtifactModel, prepared.parse_artifact_id)
        attempt = session.get(ParseAttemptModel, prepared.parse_attempt_id)
        assert (artifact.status, attempt.status) == ("running", "running")
        assert artifact.derived_relative_path is None
        assert session.scalar(select(SourceDocumentModel)) is None
        assert session.scalar(select(ParsedBlockModel)) is None
        assert session.scalar(select(DomainEventModel).where(DomainEventModel.event_type == "document.parse_succeeded")) is None

    restarted = SqlWriteCoordinator(factory, data_directory=workspace)
    restarted.register_parse_success(success)
    assert len(tuple((workspace / "derived" / "parse").rglob("parsed_document.json"))) == 1
    with factory() as session:
        assert session.get(ParseArtifactModel, prepared.parse_artifact_id).status == "succeeded"
        assert session.scalar(select(SourceDocumentModel)) is not None


def test_different_operation_cannot_close_attempt_or_promote_output(
    parse_database, minimal_parsed_document
) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, prepared = _start(coordinator, factory, snapshot_id)
    other_operation_id = uuid4()
    with factory.begin() as session:
        session.add(_operation(other_operation_id))
    success = minimal_parsed_document.success_dto(
        workspace, operation_id, prepared.parse_artifact_id, prepared.parse_attempt_id, snapshot_id
    )
    wrong_operation = replace(success, operation_id=other_operation_id)

    with pytest.raises(WriteCoordinatorError, match="COMMAND_VALIDATION_FAILED"):
        coordinator.register_parse_success(wrong_operation)

    assert not (workspace / success.derived_relative_path).exists()
    with factory() as session:
        assert session.get(ParseAttemptModel, prepared.parse_attempt_id).status == "running"
        assert session.get(ParseArtifactModel, prepared.parse_artifact_id).status == "running"


def test_failed_event_insert_failure_rolls_back_attempt_artifact_and_operation(
    parse_database,
) -> None:
    from research_workspace.application.dto.parsing_dto import ParseFailureDTO

    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, prepared = _start(coordinator, factory, snapshot_id)

    def fail_event(_mapper, _connection, target):
        if target.event_type == "document.parse_failed":
            raise RuntimeError("injected failed-event failure")

    event.listen(DomainEventModel, "before_insert", fail_event)
    try:
        with pytest.raises(RuntimeError, match="injected failed-event failure"):
            coordinator.register_parse_failure(
                ParseFailureDTO(
                    operation_id,
                    prepared.parse_artifact_id,
                    prepared.parse_attempt_id,
                    "PDF_READ_ERROR",
                    (),
                )
            )
    finally:
        event.remove(DomainEventModel, "before_insert", fail_event)

    with factory() as session:
        artifact = session.get(ParseArtifactModel, prepared.parse_artifact_id)
        attempt = session.get(ParseAttemptModel, prepared.parse_attempt_id)
        operation = session.get(BackgroundOperationModel, operation_id)
        assert (artifact.status, attempt.status, operation.status) == (
            "running",
            "running",
            "running",
        )
        assert session.scalar(
            select(DomainEventModel).where(DomainEventModel.event_type == "document.parse_failed")
        ) is None
