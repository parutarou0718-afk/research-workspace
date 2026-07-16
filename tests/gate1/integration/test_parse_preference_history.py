from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy import select

from research_workspace.infrastructure.db.models import (
    BackgroundOperationModel,
    EvidenceRefModel,
    ParseArtifactModel,
    ParsedBlockModel,
    SnapshotParsePreferenceModel,
    SourceDocumentModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator

from research_workspace.application.dto.parsing_dto import ParseAttemptSeed
from research_workspace.domain.parsing import DEFAULT_PARSER_CONFIG


def _operation(operation_id, operation_type="document_parse"):
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


def _seed(snapshot_id, operation_id, artifact_id, attempt_id, **changes):
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


def _plain(value):
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _succeed(coordinator, factory, workspace, snapshot_id, minimal_parsed_document, language, title):
    operation_id, artifact_id, attempt_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        session.add(_operation(operation_id))
    prepared = coordinator.start_parse_attempt(
        _seed(
            snapshot_id,
            operation_id,
            artifact_id,
            attempt_id,
            parser_config={**DEFAULT_PARSER_CONFIG, "language": language},
        )
    )
    success = minimal_parsed_document.success_dto(
        workspace,
        operation_id,
        prepared.parse_artifact_id,
        prepared.parse_attempt_id,
        snapshot_id,
        title=title,
    )
    success_document = _plain(success.parsed_document)
    parser = dict(success_document["parser"])
    parser["config_fingerprint"] = prepared.config_fingerprint
    success_document["parser"] = parser
    import hashlib
    import rfc8785
    from research_workspace.application.dto.parsing_dto import ParseSuccessDTO

    exact_hash = hashlib.sha256(rfc8785.dumps(success_document)).hexdigest()
    coordinator.register_parse_success(
        ParseSuccessDTO(
            success.operation_id,
            success.parse_artifact_id,
            success.parse_attempt_id,
            success_document,
            success.output_sha256,
            exact_hash,
            success.derived_relative_path,
        )
    )
    return operation_id, prepared


def test_preference_change_preserves_prior_artifact_document_block_and_evidence(
    parse_database, minimal_parsed_document
) -> None:
    workspace, factory, snapshot_id = parse_database
    coordinator = SqlWriteCoordinator(factory, data_directory=workspace)
    _, first = _succeed(
        coordinator, factory, workspace, snapshot_id, minimal_parsed_document, None, "First"
    )
    _, second = _succeed(
        coordinator, factory, workspace, snapshot_id, minimal_parsed_document, "en", "Second"
    )
    first_preference_operation, second_preference_operation = uuid4(), uuid4()
    with factory.begin() as session:
        session.add_all(
            [
                _operation(first_preference_operation, "parse_preference"),
                _operation(second_preference_operation, "parse_preference"),
            ]
        )
        first_document = session.scalar(
            select(SourceDocumentModel).where(
                SourceDocumentModel.parse_artifact_id == first.parse_artifact_id
            )
        )
        first_block = session.scalar(
            select(ParsedBlockModel).where(
                ParsedBlockModel.parse_artifact_id == first.parse_artifact_id
            )
        )
        session.add(
            EvidenceRefModel(
                id=uuid4(),
                entity_type="SourceSnapshot",
                entity_id=snapshot_id,
                parse_artifact_id=first.parse_artifact_id,
                parsed_block_id=first_block.id,
                locator_json=first_block.locator_json,
                quote_hash="c" * 64,
                saved_excerpt=None,
                created_at=datetime.now(timezone.utc),
                created_by_operation_id=first_preference_operation,
            )
        )
        original_document_id = first_document.id
        original_block_id = first_block.id

    assert coordinator.set_parse_preference(
        snapshot_id, first.parse_artifact_id, first_preference_operation
    ) == 1
    assert coordinator.set_parse_preference(
        snapshot_id, second.parse_artifact_id, second_preference_operation
    ) == 2

    with factory() as session:
        preference = session.get(SnapshotParsePreferenceModel, snapshot_id)
        evidence = session.scalar(select(EvidenceRefModel))
        first_artifact = session.get(ParseArtifactModel, first.parse_artifact_id)
        first_document = session.get(SourceDocumentModel, original_document_id)
        first_block = session.get(ParsedBlockModel, original_block_id)
        first_operation = session.get(BackgroundOperationModel, first_preference_operation)
        second_operation = session.get(BackgroundOperationModel, second_preference_operation)
        assert (preference.parse_artifact_id, preference.row_version) == (
            second.parse_artifact_id,
            2,
        )
        assert preference.updated_by_operation_id == second_preference_operation
        assert first_artifact.status == "succeeded"
        assert first_document.parse_artifact_id == first.parse_artifact_id
        assert first_block.parse_artifact_id == first.parse_artifact_id
        assert evidence.parse_artifact_id == first.parse_artifact_id
        assert json.loads(first_operation.result_summary_json)["new_parse_artifact_id"] == str(
            first.parse_artifact_id
        )
        assert json.loads(second_operation.result_summary_json) == {
            "new_parse_artifact_id": str(second.parse_artifact_id),
            "old_parse_artifact_id": str(first.parse_artifact_id),
            "source_snapshot_id": str(snapshot_id),
        }
