from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from research_workspace.application.dto.parsing_dto import (
    ParseAttemptSeed,
    ParseFailureDTO,
)
from research_workspace.domain.parsing import (
    DEFAULT_PARSER_CONFIG,
    ParseContractError,
    build_parse_artifact_identity,
)
from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    DomainEventModel,
    ParseArtifactModel,
    ParseAttemptModel,
    SourceDocumentModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator, WriteCoordinatorError


def _operation(operation_id: UUID, operation_type: str = "document_parse") -> BackgroundOperationModel:
    now = datetime.now(timezone.utc)
    return BackgroundOperationModel(
        id=operation_id,
        operation_type=operation_type,
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


def _seed(snapshot_id: UUID, operation_id: UUID, artifact_id: UUID, attempt_id: UUID, **changes):
    values = {
        "operation_id": operation_id,
        "parse_artifact_id": artifact_id,
        "parse_attempt_id": attempt_id,
        "source_snapshot_id": snapshot_id,
        "parser_id": "pypdf",
        "parser_version": "6.14.2",
        "parser_config": DEFAULT_PARSER_CONFIG,
        "contract_version": "2.0",
        "executor_version": "gate1-test",
    }
    values.update(changes)
    return ParseAttemptSeed(**values)


def test_artifact_identity_uses_default_expanded_canonical_config() -> None:
    snapshot_id = uuid4()
    explicit = build_parse_artifact_identity(
        snapshot_id, "pypdf", "6.14.2", DEFAULT_PARSER_CONFIG, "2.0"
    )
    reordered = build_parse_artifact_identity(
        snapshot_id,
        "pypdf",
        "6.14.2",
        dict(reversed(tuple(DEFAULT_PARSER_CONFIG.items()))),
        "2.0",
    )
    defaulted = build_parse_artifact_identity(snapshot_id, "pypdf", "6.14.2", {}, "2.0")
    changed = build_parse_artifact_identity(
        snapshot_id,
        "pypdf",
        "6.14.2",
        {**DEFAULT_PARSER_CONFIG, "language": "en"},
        "2.0",
    )

    assert explicit == reordered == defaulted
    assert changed != explicit
    assert build_parse_artifact_identity(
        uuid4(), "pypdf", "6.14.2", DEFAULT_PARSER_CONFIG, "2.0"
    ) != explicit
    assert build_parse_artifact_identity(
        snapshot_id, "python-pptx", "6.14.2", DEFAULT_PARSER_CONFIG, "2.0"
    ) != explicit
    assert build_parse_artifact_identity(
        snapshot_id, "pypdf", "6.14.3", DEFAULT_PARSER_CONFIG, "2.0"
    ) != explicit
    assert len(explicit.config_fingerprint) == 64
    with pytest.raises(ParseContractError, match="UNSUPPORTED_CONFIGURATION"):
        build_parse_artifact_identity(
            snapshot_id,
            "pypdf",
            "6.14.2",
            {**DEFAULT_PARSER_CONFIG, "ocr_enabled": True},
            "2.0",
        )


def test_default_parser_config_is_deeply_immutable() -> None:
    with pytest.raises(TypeError):
        DEFAULT_PARSER_CONFIG["ocr_enabled"] = True
    with pytest.raises(TypeError):
        DEFAULT_PARSER_CONFIG["extensions"]["pdf"] = {}


def test_failed_attempt_is_immutable_and_retry_increments_number(parse_database) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    first_operation, second_operation = uuid4(), uuid4()
    artifact_id, first_attempt, second_attempt = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add_all([_operation(first_operation), _operation(second_operation)])

    first = coordinator.start_parse_attempt(
        _seed(snapshot_id, first_operation, artifact_id, first_attempt)
    )
    coordinator.register_parse_failure(
        ParseFailureDTO(first_operation, first.parse_artifact_id, first.parse_attempt_id, "PDF_READ_ERROR", ())
    )
    second = coordinator.start_parse_attempt(
        _seed(snapshot_id, second_operation, uuid4(), second_attempt)
    )

    assert (first.attempt_number, second.attempt_number) == (1, 2)
    assert second.parse_artifact_id == artifact_id
    with factory() as session:
        stored_first = session.get(ParseAttemptModel, first_attempt)
        artifact = session.get(ParseArtifactModel, artifact_id)
        assert (stored_first.status, stored_first.error_code) == ("failed", "PDF_READ_ERROR")
        assert stored_first.finished_at is not None
        assert artifact.status == "running"
        assert session.scalar(select(SourceDocumentModel)) is None
        event = session.scalar(
            select(DomainEventModel).where(DomainEventModel.event_type == "document.parse_failed")
        )
        assert event is not None
        import json

        payload = json.loads(event.payload_json)
        assert set(payload) == {
            "parse_artifact_id",
            "source_snapshot_id",
            "parse_attempt_id",
            "error_code",
        }
        assert payload["error_code"] == "PDF_READ_ERROR"


def test_successful_artifact_rejects_any_later_attempt(parse_database, minimal_parsed_document) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    operation_id, artifact_id, attempt_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add(_operation(operation_id))
    prepared = coordinator.start_parse_attempt(_seed(snapshot_id, operation_id, artifact_id, attempt_id))
    success = minimal_parsed_document.success_dto(
        workspace, operation_id, prepared.parse_artifact_id, prepared.parse_attempt_id, snapshot_id
    )
    coordinator.register_parse_success(success)

    later_operation = uuid4()
    with factory.begin() as session:
        session.add(_operation(later_operation))
    with pytest.raises(WriteCoordinatorError, match="PARSE_ALREADY_SUCCEEDED"):
        coordinator.start_parse_attempt(
            _seed(snapshot_id, later_operation, uuid4(), uuid4())
        )
    with factory() as session:
        attempts = session.scalars(
            select(ParseAttemptModel).where(ParseAttemptModel.parse_artifact_id == artifact_id)
        ).all()
        assert [attempt.status for attempt in attempts] == ["succeeded"]
