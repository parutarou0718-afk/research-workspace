import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "event_contract.schema.json"
VALID_V1_EVENT = {
    "schema_version": "1.0",
    "event_id": "123e4567-e89b-12d3-a456-426614174001",
    "event_type": "document.imported",
    "occurred_at": "2026-07-16T00:00:00Z",
    "actor": {"actor_type": "system", "actor_id": None},
    "aggregate": {"type": "SourceDocument", "id": "123e4567-e89b-12d3-a456-426614174003"},
    "payload": {},
    "deduplication_key": "document-imported-1",
    "causation_id": None,
    "correlation_id": None,
}
VALID_V2_EVENT = {
    "schema_version": "2.0",
    "event_id": "123e4567-e89b-12d3-a456-426614174011",
    "event_type": "source.snapshot_imported",
    "occurred_at": "2026-07-16T00:00:00Z",
    "workspace_id": "123e4567-e89b-12d3-a456-426614174012",
    "command_id": None,
    "operation_id": "123e4567-e89b-12d3-a456-426614174013",
    "aggregate_type": "SourceSnapshot",
    "aggregate_id": "123e4567-e89b-12d3-a456-426614174014",
    "aggregate_version": None,
    "actor_type": "system",
    "correlation_id": "123e4567-e89b-12d3-a456-426614174015",
    "causation_id": None,
    "payload": {
        "snapshot_id": "123e4567-e89b-12d3-a456-426614174014",
        "source_observation_id": "123e4567-e89b-12d3-a456-426614174016",
        "import_item_id": "123e4567-e89b-12d3-a456-426614174017",
        "sha256": "a" * 64,
        "size_bytes": 123,
    },
}


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_read_event(value: object) -> tuple[str, ...]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    return tuple(error.message for error in validator.iter_errors(value))


def validate_new_event(value: object) -> tuple[str, ...]:
    schema = _schema()
    write_schema = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/domainEventV2",
        "$defs": schema["$defs"],
    }
    validator = Draft202012Validator(write_schema, format_checker=FormatChecker())
    return tuple(error.message for error in validator.iter_errors(value))


def test_v1_event_is_readable_but_new_event_requires_v2_envelope() -> None:
    assert validate_read_event(VALID_V1_EVENT) == ()
    assert validate_new_event(VALID_V1_EVENT)
    assert validate_new_event(VALID_V2_EVENT) == ()


def test_v2_event_payload_is_closed() -> None:
    event = json.loads(json.dumps(VALID_V2_EVENT))
    event["payload"]["full_path"] = r"C:\\private\\paper.pdf"
    assert validate_new_event(event)


def test_v2_system_event_requires_operation_and_correlation_identity() -> None:
    event = {**VALID_V2_EVENT, "operation_id": None, "correlation_id": None}
    assert validate_new_event(event)


def test_v2_user_event_requires_command_id() -> None:
    event = {**VALID_V2_EVENT, "actor_type": "user", "command_id": None}
    assert validate_new_event(event)


def test_read_event_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate({**VALID_V2_EVENT, "schema_version": "3.0"})
