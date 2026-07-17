from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[3]
UUID1 = "123e4567-e89b-12d3-a456-426614174001"
UUID2 = "123e4567-e89b-12d3-a456-426614174002"


def _schema(name: str) -> dict:
    path = ROOT / "contracts" / name
    assert path.is_file(), f"missing Gate 3 contract: {name}"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _validate(name: str, value: object) -> None:
    Draft202012Validator(
        _schema(name),
        format_checker=FormatChecker(),
    ).validate(value)


def _permission(capability: str = "paper.write") -> dict:
    return {
        "schema_version": "1.0",
        "actor_type": "user",
        "actor_id": "local-user",
        "workspace_id": UUID1,
        "capabilities": [capability],
        "scope_refs": ["Paper:" + UUID2],
        "path_scopes": [],
        "network_allowed": False,
        "granted_at": "2026-07-17T00:00:00Z",
        "policy_version": "1.0",
        "authorization_decision_id": UUID2,
    }


def _command() -> dict:
    return {
        "id": UUID1,
        "command_type": "paper.update",
        "contract_version": "1.0",
        "idempotency_key": "ui-paper-update-1",
        "request_fingerprint": "a" * 64,
        "actor_type": "user",
        "actor_id": "local-user",
        "permission_context": _permission(),
        "status": "committed",
        "requested_at": "2026-07-17T00:00:00Z",
        "started_at": "2026-07-17T00:00:01Z",
        "committed_at": "2026-07-17T00:00:02Z",
        "failed_at": None,
        "recovery_point_id": UUID2,
        "undo_of_command_id": None,
        "result_summary": {
            "affected_entity_ids": [UUID2],
            "affected_count": 1,
            "replayed": False,
        },
        "error_code": None,
        "migration_batch_id": None,
    }


def _audit() -> dict:
    return {
        "id": UUID1,
        "command_id": UUID2,
        "change_index": 0,
        "entity_type": "Paper",
        "entity_id": UUID1,
        "operation": "update",
        "before_schema_version": "1.0",
        "before": {
            "schema_version": "1.0",
            "entity_type": "Paper",
            "entity_id": UUID1,
            "row_version": 1,
            "fields": {"title": "Old", "status": "active"},
        },
        "after_schema_version": "1.0",
        "after": {
            "schema_version": "1.0",
            "entity_type": "Paper",
            "entity_id": UUID1,
            "row_version": 2,
            "fields": {"title": "New", "status": "active"},
        },
        "changed_fields": ["title"],
        "before_row_version": 1,
        "after_row_version": 2,
        "created_at": "2026-07-17T00:00:02Z",
    }


def test_application_command_and_audit_schemas_are_closed_draft_202012() -> None:
    _validate("application_command.schema.json", _command())
    _validate("audit_change.schema.json", _audit())
    for name, value in (
        ("application_command.schema.json", {**_command(), "full_path": "C:/private"}),
        ("audit_change.schema.json", {**_audit(), "orm_state": {}}),
    ):
        with pytest.raises(ValidationError):
            _validate(name, value)


def test_application_command_lifecycle_and_permission_snapshot_are_closed() -> None:
    failed = {
        **_command(),
        "status": "failed",
        "committed_at": None,
        "failed_at": "2026-07-17T00:00:02Z",
        "recovery_point_id": None,
        "result_summary": None,
        "error_code": "COMMAND_VALIDATION_FAILED",
    }
    _validate("application_command.schema.json", failed)
    with pytest.raises(ValidationError):
        _validate(
            "application_command.schema.json",
            {**_command(), "permission_context": _permission("backup.request")},
        )
    with pytest.raises(ValidationError):
        _validate(
            "application_command.schema.json",
            {
                **_command(),
                "permission_context": {
                    **_permission(),
                    "actor_type": "agent",
                },
            },
        )
    unsafe_scope = {
        "scope_type": "snapshot_read",
        "normalized_path_hash": "b" * 64,
        "root_id": UUID1,
        "access_mode": "read",
        "recursive": False,
        "full_path": "C:/private/paper.pdf",
    }
    with pytest.raises(ValidationError):
        _validate(
            "application_command.schema.json",
            {
                **_command(),
                "permission_context": {
                    **_permission(),
                    "path_scopes": [unsafe_scope],
                },
            },
        )


def test_migration_adoption_is_system_only_and_uses_migration_backup_proof() -> None:
    system_command = {
        **_command(),
        "command_type": "system.migration_adopt_v01",
        "actor_type": "system",
        "actor_id": None,
        "permission_context": {
            **_permission("maintenance.verify.request"),
            "actor_type": "system",
            "actor_id": None,
        },
        "recovery_point_id": None,
        "migration_batch_id": UUID2,
        "result_summary": {
            "affected_entity_ids": [],
            "affected_count": 1_000,
            "replayed": False,
        },
    }
    _validate("application_command.schema.json", system_command)
    with pytest.raises(ValidationError):
        _validate(
            "application_command.schema.json",
            {
                **system_command,
                "actor_type": "user",
                "permission_context": _permission(),
            },
        )


def test_audit_snapshots_are_versioned_per_entity_not_orm_dumps() -> None:
    audit = _audit()
    assert audit["changed_fields"] == sorted(set(audit["changed_fields"]))
    with pytest.raises(ValidationError):
        _validate(
            "audit_change.schema.json",
            {
                **audit,
                "changed_fields": ["title", "title"],
            },
        )
    with pytest.raises(ValidationError):
        _validate(
            "audit_change.schema.json",
            {
                **audit,
                "before": {
                    **audit["before"],
                    "_sa_instance_state": "secret",
                },
            },
        )


def test_domain_model_adds_gate3_nodes_without_changing_frozen_nodes() -> None:
    model = json.loads((ROOT / "contracts" / "domain_model.json").read_text("utf-8"))
    assert model["version"] == "0.2-gate3"
    gate3 = model["gate3_entities"]
    assert set(gate3) == {
        "ApplicationCommand",
        "AuditChange",
        "RecoveryPoint",
        "RecoverySlot",
        "Paper",
        "PaperVersion",
        "Idea",
        "Submission",
        "EntityRelation",
    }
    contracts = model["gate3_contracts"]
    assert contracts["command_statuses"] == [
        "pending",
        "running",
        "committed",
        "failed",
        "cancelled",
    ]
    assert contracts["paper_version_lifecycle"] == ["active", "retracted"]
    assert contracts["relation_lifecycle"] == ["active", "retracted", "superseded"]
    assert contracts["maximum_batch_targets"] == 100
    assert contracts["submission_transitions"]["withdrawn"] == []
    assert contracts["version_successor_direction"] == {
        "source": "later_paper_version",
        "target": "earlier_paper_version",
    }


def test_permission_context_accepts_only_approved_gate3_capabilities() -> None:
    schema = "permission_context.schema.json"
    for capability in (
        "paper.write",
        "idea.write",
        "submission.write",
        "relation.review",
        "undo.execute",
    ):
        _validate(schema, _permission(capability))
    with pytest.raises(ValidationError):
        _validate(schema, _permission("agent.execute"))
