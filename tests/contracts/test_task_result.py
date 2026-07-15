import pytest
from jsonschema import ValidationError

from conftest import validate_contract


def test_complete_task_result_is_valid(valid_result):
    validate_contract("task_result.schema.json", valid_result)


@pytest.mark.parametrize("field", ["schema_version", "task_id", "status", "attempt", "started_at", "finished_at", "output_refs", "result", "error", "retry", "event_ids", "audit_log_ids"])
def test_required_result_fields(field, valid_result):
    del valid_result[field]
    with pytest.raises(ValidationError):
        validate_contract("task_result.schema.json", valid_result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "123E4567-E89B-12D3-A456-426614174000"),
        ("task_id", "not-a-uuid"),
        ("finished_at", "2026-07-16T09:00:01+09:00"),
        ("status", "pending"),
        ("attempt", 0),
    ],
)
def test_result_rejects_invalid_values(field, value, valid_result):
    valid_result[field] = value
    with pytest.raises(ValidationError):
        validate_contract("task_result.schema.json", valid_result)


def test_result_rejects_extra_properties(valid_result):
    valid_result["extra"] = True
    with pytest.raises(ValidationError):
        validate_contract("task_result.schema.json", valid_result)


def test_retry_scheduled_requires_retryable_error_and_retry(valid_result):
    valid_result.update(status="retry_scheduled", result=None, error={"code": "TEMP", "message": "retry", "retryable": False, "details": {}}, retry=None)
    with pytest.raises(ValidationError):
        validate_contract("task_result.schema.json", valid_result)


def test_cancelled_requires_normative_error(valid_result):
    valid_result.update(status="cancelled", result=None, error={"code": "OTHER", "message": "cancelled", "retryable": False, "details": {}}, retry=None)
    with pytest.raises(ValidationError):
        validate_contract("task_result.schema.json", valid_result)
