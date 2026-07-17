from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


UUID1 = "123e4567-e89b-12d3-a456-426614174021"
UUID2 = "123e4567-e89b-12d3-a456-426614174022"
ROOT = Path(__file__).resolve().parents[3]

_SPEC = importlib.util.spec_from_file_location(
    "gate3_domain_event_contract",
    ROOT / "tests" / "contracts" / "test_domain_event.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_EVENT_CONTRACT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EVENT_CONTRACT)
VALID_V1_EVENT = _EVENT_CONTRACT.VALID_V1_EVENT
VALID_V2_EVENT = _EVENT_CONTRACT.VALID_V2_EVENT
validate_new_event = _EVENT_CONTRACT.validate_new_event
validate_read_event = _EVENT_CONTRACT.validate_read_event


def _user_event(event_type: str, payload: dict) -> dict:
    return {
        **VALID_V2_EVENT,
        "event_id": UUID1,
        "event_type": event_type,
        "actor_type": "user",
        "command_id": UUID2,
        "operation_id": None,
        "aggregate_type": "Paper",
        "aggregate_id": UUID1,
        "aggregate_version": 2,
        "correlation_id": UUID2,
        "payload": payload,
    }


def test_v1_remains_readable_but_cannot_be_written_as_new() -> None:
    assert validate_read_event(VALID_V1_EVENT) == ()
    assert validate_new_event(VALID_V1_EVENT)


def test_gate3_entity_and_undo_payloads_are_closed() -> None:
    entity = _user_event(
        "paper.updated",
        {
            "entity_id": UUID1,
            "row_version": 2,
            "changed_fields": ["status", "title"],
        },
    )
    undo = _user_event(
        "command.undo_applied",
        {
            "undo_command_id": UUID1,
            "original_command_id": UUID2,
            "affected_entity_ids": [UUID1],
        },
    )
    assert validate_new_event(entity) == ()
    assert validate_new_event(undo) == ()
    leaked = copy.deepcopy(entity)
    leaked["payload"]["full_path"] = "C:/private/paper.docx"
    assert validate_new_event(leaked)


def test_gate3_version_and_relation_payloads_use_fixed_direction_and_ids() -> None:
    event = _user_event(
        "paper_version_relation.created",
        {
            "relation_id": UUID1,
            "later_paper_version_id": UUID1,
            "earlier_paper_version_id": UUID2,
            "row_version": 1,
        },
    )
    assert validate_new_event(event) == ()
    invalid = copy.deepcopy(event)
    invalid["payload"]["parent_version_id"] = UUID2
    assert validate_new_event(invalid)
