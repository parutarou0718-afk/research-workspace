import pytest
from jsonschema import ValidationError

from conftest import validate_contract


def test_complete_domain_event_is_valid(valid_event):
    validate_contract("event_contract.schema.json", valid_event)


@pytest.mark.parametrize("field", ["schema_version", "event_id", "event_type", "occurred_at", "actor", "aggregate", "payload", "deduplication_key"])
def test_required_event_fields(field, valid_event):
    del valid_event[field]
    with pytest.raises(ValidationError):
        validate_contract("event_contract.schema.json", valid_event)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_id", "123E4567-E89B-12D3-A456-426614174001"),
        ("event_id", "not-a-uuid"),
        ("occurred_at", "2026-07-16T09:00:00+09:00"),
        ("event_type", "unknown"),
    ],
)
def test_event_rejects_invalid_values(field, value, valid_event):
    valid_event[field] = value
    with pytest.raises(ValidationError):
        validate_contract("event_contract.schema.json", valid_event)


def test_event_rejects_extra_properties(valid_event):
    valid_event["extra"] = True
    with pytest.raises(ValidationError):
        validate_contract("event_contract.schema.json", valid_event)
