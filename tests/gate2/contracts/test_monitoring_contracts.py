import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[3]
BACKGROUND_SCHEMA = ROOT / "contracts" / "background_operation.schema.json"
DOMAIN_MODEL = ROOT / "contracts" / "domain_model.json"

ROOT_STATES = {
    "active",
    "paused",
    "disconnected",
    "degraded",
    "overflow_reconciling",
    "error",
}
PENDING_STATES = {
    "detected",
    "debouncing",
    "waiting_for_stability",
    "importing",
    "imported",
    "duplicate_content",
    "safe_failure",
    "unstable_source",
}


def _operation(operation_type: str) -> dict:
    return {
        "schema_version": "1.0",
        "operation_id": "123e4567-e89b-12d3-a456-426614174010",
        "operation_type": operation_type,
        "status": "planned",
        "work_plan_fingerprint": "b" * 64,
        "permission_context": {
            "schema_version": "1.0",
            "actor_type": "system",
            "actor_id": None,
            "workspace_id": "123e4567-e89b-12d3-a456-426614174000",
            "capabilities": ["source.observe.request"],
            "scope_refs": ["monitoring-root"],
            "path_scopes": [
                {
                    "scope_type": "monitoring_root",
                    "normalized_path_hash": "a" * 64,
                    "root_id": "123e4567-e89b-12d3-a456-426614174001",
                    "access_mode": "list",
                    "recursive": True,
                }
            ],
            "network_allowed": False,
            "granted_at": "2026-07-17T00:00:00Z",
            "policy_version": "1.0",
            "authorization_decision_id": "123e4567-e89b-12d3-a456-426614174002",
        },
        "result_summary": None,
        "error_code": None,
        "created_at": "2026-07-17T00:00:00Z",
        "started_at": None,
        "finished_at": None,
        "cancel_requested_at": None,
    }


def _validate_operation(value: dict) -> None:
    schema = json.loads(BACKGROUND_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


@pytest.mark.parametrize(
    "operation_type",
    ["source_observe", "monitor_reconcile", "version_candidate_detect"],
)
def test_gate2_background_operation_types_are_closed_and_valid(operation_type: str) -> None:
    _validate_operation(_operation(operation_type))


def test_background_operation_rejects_unknown_gate2_type() -> None:
    with pytest.raises(ValidationError):
        _validate_operation(_operation("monitor_everything"))


def test_domain_model_locks_gate2_entities_states_and_semantic_defaults() -> None:
    model = json.loads(DOMAIN_MODEL.read_text(encoding="utf-8"))

    assert model["version"] in {"0.2-gate2", "0.2-gate3"}
    assert set(model["gate2_entities"]) == {
        "MonitoringRoot",
        "RawFileEvent",
        "RawEventPendingLink",
        "PendingPathCheck",
        "ReconciliationRun",
        "PaperVersionCandidate",
    }
    contracts = model["gate2_contracts"]
    assert set(contracts["root_statuses"]) == ROOT_STATES
    assert set(contracts["pending_path_states"]) == PENDING_STATES
    assert contracts["monitoring_semantic_defaults"] == {
        "stable_stat_observations": 2,
        "quiet_window_seconds": 2,
        "maximum_stability_attempts": 5,
        "backoff_seconds": [2, 5, 15, 30, 60],
        "maximum_candidate_neighbors": 12,
    }
