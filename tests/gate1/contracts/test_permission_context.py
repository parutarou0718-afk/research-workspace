import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "permission_context.schema.json"
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


def validate(value: object) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def test_permission_context_is_closed_and_offline() -> None:
    validate(VALID_CONTEXT)
    for change in ({"network_allowed": True}, {"token": "secret"}):
        with pytest.raises(ValidationError):
            validate({**VALID_CONTEXT, **change})


@pytest.mark.parametrize("actor_type", ["agent", "task_executor"])
def test_disabled_actor_is_not_a_permission_context_actor(actor_type: str) -> None:
    with pytest.raises(ValidationError):
        validate({**VALID_CONTEXT, "actor_type": actor_type})


def test_path_scope_rejects_full_paths_and_unapproved_access() -> None:
    scope = {**VALID_CONTEXT["path_scopes"][0], "path": r"C:\\private\\paper.pdf"}
    with pytest.raises(ValidationError):
        validate({**VALID_CONTEXT, "path_scopes": [scope]})
