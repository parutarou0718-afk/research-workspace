import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOMAIN_MODEL = ROOT / "contracts" / "domain_model.json"

RULES = [
    "R1_SOURCE_CONTINUITY",
    "R2_REPLACE_CONTINUITY",
    "R3_PAPER_TITLE_TIME",
    "R4_NAME_TITLE_TEXT",
    "R5_ZERO_TEXT_LINEAGE",
]


def test_candidate_identity_and_closed_rule_registry_are_normative() -> None:
    model = json.loads(DOMAIN_MODEL.read_text(encoding="utf-8"))
    contract = model["gate2_contracts"]["paper_version_candidate"]

    assert contract["identity"] == [
        "earlier_snapshot_id",
        "later_snapshot_id",
        "detector_id",
        "detector_version",
        "rule_config_fingerprint",
    ]
    assert contract["detector_version"] == "1.0"
    assert contract["rule_ids"] == RULES
    assert contract["statuses"] == ["pending", "confirmed", "rejected", "superseded"]
    assert contract["same_hash_excluded"] is True
    assert contract["modified_time_alone_is_direction"] is False
    assert contract["maximum_neighbors_per_snapshot"] == 12


def test_provider_contract_documents_gate2_boundaries_without_decision_ports() -> None:
    text = (ROOT / "contracts" / "provider_interfaces.md").read_text(encoding="utf-8")

    assert "class FileObserver(Protocol)" in text
    assert "RawFileEventDTO" in text
    assert "ReconciliationPlan" in text
    assert "CandidateDetectionResult" in text
    assert "def confirm_candidate(" not in text
    assert "def reject_candidate(" not in text
