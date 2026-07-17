import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "event_contract.schema.json"
UUIDS = [f"123e4567-e89b-12d3-a456-4266141740{i:02d}" for i in range(20)]


def _event(event_type: str, payload: dict) -> dict:
    return {
        "schema_version": "2.0",
        "event_id": UUIDS[1],
        "event_type": event_type,
        "occurred_at": "2026-07-17T00:00:00Z",
        "workspace_id": UUIDS[2],
        "command_id": None,
        "operation_id": UUIDS[3],
        "aggregate_type": "MonitoringRoot",
        "aggregate_id": UUIDS[4],
        "aggregate_version": 1,
        "actor_type": "system",
        "correlation_id": UUIDS[5],
        "causation_id": None,
        "payload": payload,
    }


def _errors(value: dict) -> tuple[str, ...]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    write_schema = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/domainEventV2",
        "$defs": schema["$defs"],
    }
    validator = Draft202012Validator(write_schema, format_checker=FormatChecker())
    return tuple(error.message for error in validator.iter_errors(value))


def test_monitoring_root_event_uses_closed_statuses() -> None:
    event = _event(
        "monitoring.root_status_changed",
        {"monitoring_root_id": UUIDS[4], "old_status": "active", "new_status": "degraded"},
    )
    assert _errors(event) == ()

    invalid = copy.deepcopy(event)
    invalid["payload"]["new_status"] = "maybe"
    assert _errors(invalid)


def test_reconciliation_event_uses_closed_reason() -> None:
    event = _event(
        "monitoring.reconciliation_completed",
        {
            "reconciliation_run_id": UUIDS[6],
            "monitoring_root_id": UUIDS[4],
            "reason": "overflow",
            "items_seen": 10,
            "items_suspected_changed": 2,
        },
    )
    assert _errors(event) == ()

    invalid = copy.deepcopy(event)
    invalid["payload"]["reason"] = "periodic_full_scan"
    assert _errors(invalid)


def test_candidate_detected_event_uses_closed_rule_id_and_payload() -> None:
    event = _event(
        "paper_version_candidate.detected",
        {
            "candidate_id": UUIDS[7],
            "earlier_snapshot_id": UUIDS[8],
            "later_snapshot_id": UUIDS[9],
            "rule_id": "R1_SOURCE_CONTINUITY",
            "detector_version": "1.0",
        },
    )
    assert _errors(event) == ()

    invalid_rule = copy.deepcopy(event)
    invalid_rule["payload"]["rule_id"] = "WEIGHTED_SCORE"
    assert _errors(invalid_rule)
    with_path = copy.deepcopy(event)
    with_path["payload"]["source_path"] = r"C:\private\paper.pdf"
    assert _errors(with_path)

