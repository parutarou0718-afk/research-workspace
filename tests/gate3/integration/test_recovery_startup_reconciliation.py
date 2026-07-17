from __future__ import annotations

import json
from pathlib import Path

from research_workspace.infrastructure.recovery.sqlite_recovery import (
    PhysicalRecoveryState,
    reconcile_recovery_directories,
)


def test_reconciliation_rejects_tampered_manifest_and_keeps_verified_current(tmp_path) -> None:
    recovery = tmp_path / "recovery"
    current = recovery / "current"
    staging = recovery / "staging"
    current.mkdir(parents=True)
    staging.mkdir()
    (current / "workspace.db").write_bytes(b"current")
    manifest = {
        "recovery_point_id": "00000000-0000-0000-0000-000000000001",
        "generation": 1,
        "database_sha256": __import__("hashlib").sha256(b"current").hexdigest(),
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (current / "manifest.json").write_bytes(encoded)
    (current / "manifest.sha256").write_text(__import__("hashlib").sha256(encoded).hexdigest(), "ascii")

    bad = staging / "00000000-0000-0000-0000-000000000002"
    bad.mkdir()
    (bad / "workspace.db").write_bytes(b"bad")
    (bad / "manifest.json").write_text('{"generation":2}', "utf-8")
    (bad / "manifest.sha256").write_text("0" * 64, "ascii")

    result = reconcile_recovery_directories(recovery)
    assert result.state is PhysicalRecoveryState.CURRENT_VERIFIED
    assert result.current_generation == 1
    assert current.is_dir()
    assert bad.is_dir()


def test_restore_reset_marks_history_unavailable_and_clears_slots() -> None:
    from research_workspace.application.services.recovery_points import RestoreResetPlan

    plan = RestoreResetPlan.for_workspace(
        __import__("uuid").UUID("00000000-0000-0000-0000-000000000001")
    )
    assert plan.physical_state == "historical_unavailable_after_restore"
    assert plan.clear_slots is True


def test_reconciliation_promotes_verified_staging_after_interrupted_rotation(tmp_path) -> None:
    import hashlib
    import os

    recovery = tmp_path / "recovery"
    previous = recovery / "previous"
    staging = recovery / "staging-point"
    for directory, generation, content in (
        (previous, 1, b"previous"),
        (staging, 2, b"staging"),
    ):
        directory.mkdir(parents=True)
        (directory / "workspace.db").write_bytes(content)
        manifest = {
            "recovery_point_id": f"00000000-0000-0000-0000-{generation:012d}",
            "generation": generation,
            "database_sha256": hashlib.sha256(content).hexdigest(),
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        (directory / "manifest.json").write_bytes(encoded)
        (directory / "manifest.sha256").write_text(hashlib.sha256(encoded).hexdigest(), "ascii")

    result = reconcile_recovery_directories(recovery)
    assert result.state is PhysicalRecoveryState.CURRENT_AND_PREVIOUS_VERIFIED
    assert result.current_generation == 2
    assert result.previous_generation == 1
    assert (recovery / "current").is_dir()
    assert not staging.exists()
