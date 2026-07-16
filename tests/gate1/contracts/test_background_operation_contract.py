import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "background_operation.schema.json"
VALID_CONTEXT = {
    "schema_version": "1.0",
    "actor_type": "user",
    "actor_id": "local-user",
    "workspace_id": "123e4567-e89b-12d3-a456-426614174000",
    "capabilities": ["source.snapshot_import.request"],
    "scope_refs": ["import-batch"],
    "path_scopes": [
        {
            "scope_type": "import_source",
            "normalized_path_hash": "a" * 64,
            "root_id": "123e4567-e89b-12d3-a456-426614174001",
            "access_mode": "copy",
            "recursive": False,
        }
    ],
    "network_allowed": False,
    "granted_at": "2026-07-16T00:00:00Z",
    "policy_version": "1.0",
    "authorization_decision_id": "123e4567-e89b-12d3-a456-426614174002",
}
VALID_OPERATION = {
    "schema_version": "1.0",
    "operation_id": "123e4567-e89b-12d3-a456-426614174010",
    "operation_type": "snapshot_import",
    "status": "planned",
    "work_plan_fingerprint": "b" * 64,
    "permission_context": VALID_CONTEXT,
    "result_summary": None,
    "error_code": None,
    "created_at": "2026-07-16T00:00:00Z",
    "started_at": None,
    "finished_at": None,
    "cancel_requested_at": None,
}


def validate(value: object) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def test_planned_gate1_background_operation_is_valid() -> None:
    validate(VALID_OPERATION)


@pytest.mark.parametrize("field", ["operation_id", "operation_type", "status", "permission_context"])
def test_background_operation_requires_identity_state_and_authorization(field: str) -> None:
    value = dict(VALID_OPERATION)
    del value[field]
    with pytest.raises(ValidationError):
        validate(value)


def test_background_operation_rejects_research_content_and_later_gate_types() -> None:
    with pytest.raises(ValidationError):
        validate({**VALID_OPERATION, "research_text": "secret draft"})
    with pytest.raises(ValidationError):
        validate({**VALID_OPERATION, "operation_type": "backup"})


def test_domain_model_declares_gate1_entities_without_claiming_implementation() -> None:
    domain_model = json.loads(
        (SCHEMA_PATH.parent / "domain_model.json").read_text(encoding="utf-8")
    )
    assert set(domain_model["gate1_entities"]) == {
        "SourceSnapshot",
        "SourceObservation",
        "SourceObservationEvent",
        "BackgroundOperation",
        "OperationAttempt",
        "ImportBatch",
        "ImportItem",
        "ParseArtifact",
        "ParseAttempt",
        "SourceDocument",
        "ParsedBlock",
        "DomainEvent",
    }
