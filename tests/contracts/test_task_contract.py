import pytest
from jsonschema import ValidationError

from conftest import validate_contract


def test_complete_task_contract_is_valid(valid_task):
    validate_contract("task_contract.schema.json", valid_task)


@pytest.mark.parametrize("field", ["schema_version", "task_id", "task_type", "created_at", "requested_by", "idempotency_key", "input_refs", "options"])
def test_required_task_fields(field, valid_task):
    del valid_task[field]
    with pytest.raises(ValidationError):
        validate_contract("task_contract.schema.json", valid_task)


@pytest.mark.parametrize(
    "path,value",
    [
        ("task_id", "123E4567-E89B-12D3-A456-426614174000"),
        ("task_id", "not-a-uuid"),
        ("created_at", "2026-07-16T09:00:00+09:00"),
        ("task_type", "unknown"),
    ],
)
def test_task_rejects_invalid_closed_values(path, value, valid_task):
    valid_task[path] = value
    with pytest.raises(ValidationError):
        validate_contract("task_contract.schema.json", valid_task)


def test_task_rejects_extra_properties(valid_task):
    valid_task["extra"] = True
    with pytest.raises(ValidationError):
        validate_contract("task_contract.schema.json", valid_task)


def test_task_rejects_max_attempts_out_of_range(valid_task):
    valid_task["options"]["max_attempts"] = 11
    with pytest.raises(ValidationError):
        validate_contract("task_contract.schema.json", valid_task)
