from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FREEZE = ROOT / "docs" / "GATE2_FREEZE.md"

EXPECTED_EXCLUSIVE_FILE_HASHES = {
    "contracts/event_contract.schema.json": "03bb82a8c2444c0a37a03c7e9c3818478e1dc36926c5be67195ee149370818fe",
    "contracts/background_operation.schema.json": "dfdd616ce8946ca5f53617f230e00428a7a68f973a27693128031852e0309208",
    "migrations/versions/0003_gate2_monitoring.py": "8a144eadff700c772d703d7f2ab28b9ba2124e663c481325c8dbf7ca855dfe47",
}
EXPECTED_DOMAIN_NODE_HASHES = {
    "entities": "20ae31f8998a1417fc77af92d7d2b59a7d698ed28e95daa5e6d42079753ec20b",
    "gate1_entities": "8d0971c2d12576ea3c3d23156b85c5ea8f0a200b4688381025f24fc45400fb1e",
    "gate2_entities": "b0160e245f74cd7f5d375adc273dc0fee35f766d1c0f84ab57a16ca3356901d5",
    "gate2_contracts": "35c2abf73648852b994cb3fb21285cb444aa67b670712051121670c3fb4b858f",
    "relation_types": "d26e2460078c81cd5b3bc3f414e022da165c690851ac83c122bff8c685e53c11",
    "confirmation_states": "b3aaac73fbce6871fad6ffe68f53da4e6090e4f88ca61e7d0e696362518c4338",
    "idea_statuses": "11245c820a8468fd734075e2263d221b8c8e3de5acc56d380fd7fae3edf1a8d9",
    "submission_statuses": "d4d9e45724af5e76d9c7ad220092bb00900ab63c6a749d42dad661c311757b02",
}
PROVIDER_PREFIX_LENGTH = 6589
PROVIDER_PREFIX_SHA256 = "7a8c1181912c6fd1f950c135c30161ad1f7f9081553021283de271f5301ad1c4"
EXPECTED_RULES = (
    "R1_SOURCE_CONTINUITY",
    "R2_REPLACE_CONTINUITY",
    "R3_PAPER_TITLE_TIME",
    "R4_NAME_TITLE_TEXT",
    "R5_ZERO_TEXT_LINEAGE",
)


def _freeze_text() -> str:
    assert FREEZE.is_file(), "docs/GATE2_FREEZE.md must record the approved baseline"
    return FREEZE.read_text(encoding="utf-8")


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def _semantic_sha256(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_freeze_ledger_names_the_exact_gate2_baseline() -> None:
    text = _freeze_text()
    assert "Status: `FROZEN`" in text
    assert "2a5f033aa721e4ad8ef75b0ecc3eac127cf3d477" in text
    assert "0003_gate2_monitoring" in text
    assert "DomainEvent 2.0" in text
    assert "Candidate detector 1.0" in text
    assert "REL-GATE-001" in text
    assert "BLOCKED_BY_ENVIRONMENT" in text


def test_freeze_ledger_binds_gate2_exclusive_files_byte_for_byte() -> None:
    text = _freeze_text()
    exclusive_section = text.split("## Gate 2 Semantic Node Digests", 1)[0]
    rows = {
        path: digest
        for path, digest in re.findall(
            r"\| `([^`]+)` \| `([0-9a-f]{64})` \|",
            exclusive_section,
        )
    }
    assert rows == EXPECTED_EXCLUSIVE_FILE_HASHES
    assert {
        path: _sha256(path)
        for path in EXPECTED_EXCLUSIVE_FILE_HASHES
    } == EXPECTED_EXCLUSIVE_FILE_HASHES


def test_domain_model_freezes_existing_semantic_nodes_not_the_shared_file() -> None:
    text = _freeze_text()
    domain_model = json.loads((ROOT / "contracts/domain_model.json").read_text("utf-8"))
    actual = {
        node: _semantic_sha256(domain_model[node])
        for node in EXPECTED_DOMAIN_NODE_HASHES
    }
    assert actual == EXPECTED_DOMAIN_NODE_HASHES
    for node, digest in EXPECTED_DOMAIN_NODE_HASHES.items():
        assert f"| `{node}` | `{digest}` |" in text
    assert domain_model["version"] in {"0.2-gate2", "0.2-gate3"}


def test_provider_ledger_preserves_gate2_bytes_as_an_exact_prefix() -> None:
    text = _freeze_text()
    provider = (ROOT / "contracts/provider_interfaces.md").read_bytes()
    assert len(provider) >= PROVIDER_PREFIX_LENGTH
    prefix = provider[:PROVIDER_PREFIX_LENGTH]
    assert hashlib.sha256(prefix).hexdigest() == PROVIDER_PREFIX_SHA256
    assert f"Prefix length: `{PROVIDER_PREFIX_LENGTH}` bytes" in text
    assert f"Prefix SHA-256: `{PROVIDER_PREFIX_SHA256}`" in text


def test_freeze_ledger_locks_candidate_and_monitoring_semantics() -> None:
    text = _freeze_text()
    for identity_field in (
        "earlier_snapshot_id",
        "later_snapshot_id",
        "detector_id",
        "detector_version",
        "rule_config_fingerprint",
    ):
        assert f"`{identity_field}`" in text
    for rule in EXPECTED_RULES:
        assert f"`{rule}`" in text
    assert "at most `12`" in text
    assert "10,000" in text and "120,000" in text
    assert "`RawFileEvent -> PendingPathCheck -> SourceObservation`" in text
    assert "no periodic full traversal" in text


def test_freeze_ledger_allows_only_reviewed_emergency_changes() -> None:
    text = _freeze_text()
    assert "Critical correctness defect" in text
    assert "Security defect" in text
    assert "Data-corruption defect" in text
    assert "forward addition" in text
    assert "Gate 2 Freeze Verification" in text
