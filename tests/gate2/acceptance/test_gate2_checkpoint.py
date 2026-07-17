"""Independent aggregation of the approved Gate 2 evidence map."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[3]
SPECIFICATION = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-16-v0.2-deterministic-design.md"
)

ACCEPTANCE_MAP = {
    "G2-AC01": (
        "tests/gate2/architecture/test_monitoring_layers.py",
        "tests/gate2/architecture/test_watchdog_callback_boundary.py",
    ),
    "G2-AC02": ("tests/gate2/integration/test_observation_baseline.py",),
    "G2-AC03": ("tests/gate2/integration/test_event_idempotency.py",),
    "G2-AC04": (
        "tests/gate2/integration/test_monitor_stability_reactivation.py",
    ),
    "G2-AC05": ("tests/gate2/integration/test_move_provenance.py",),
    "G2-AC06": ("tests/gate2/integration/test_root_health_states.py",),
    "G2-AC07": ("tests/gate2/integration/test_bounded_reconciliation.py",),
    "G2-AC08": ("tests/gate2/architecture/test_no_periodic_full_scan.py",),
    "G2-AC09": (
        "tests/gate2/integration/test_monitor_restart_recovery.py",
    ),
    "G2-AC10": ("tests/gate2/unit/test_monitor_root_safety.py",),
    "G2-AC11": ("tests/gate2/integration/test_raw_event_capacity.py",),
    "G2-AC12": (
        "tests/gate2/integration/test_candidate_revision_identity.py",
    ),
    "G2-AC13": ("tests/gate2/unit/test_candidate_rules.py",),
    "G2-AC14": ("tests/gate2/unit/test_zero_text_candidates.py",),
    "G2-AC15": (
        "tests/gate2/performance/test_candidate_bounded_scale.py",
    ),
    "G2-AC16": (
        "tests/gate2/ui/test_monitoring_ui.py",
        "tests/gate2/ui/test_candidate_read_only_ui.py",
    ),
    "G2-AC17": (
        "tests/gate2/architecture/test_gate2_worker_boundaries.py",
    ),
    "G2-AC18": (
        "tests/gate2/acceptance/test_watchdog_license_inventory.py",
    ),
    "G2-AC19": (
        "tests/gate2/integration/test_0003_monitoring_migration.py",
    ),
    "G2-AC20": (
        "tests/gate2/integration/test_gate2_domain_event_outbox.py",
    ),
    "G2-AC21": ("tests/gate2/acceptance/test_gate2_checkpoint.py",),
}


def _load(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return None


def test_g2_ac01_through_g2_ac21_have_literal_collectable_evidence() -> None:
    assert tuple(ACCEPTANCE_MAP) == tuple(
        f"G2-AC{number:02d}" for number in range(1, 22)
    )
    evidence = tuple(
        dict.fromkeys(
            path
            for paths in ACCEPTANCE_MAP.values()
            for path in paths
        )
    )
    assert all((ROOT / path).is_file() for path in evidence)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *evidence],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = (result.stdout + result.stderr).replace("\\", "/")
    assert all(path in collected for path in evidence)


def test_gate2_evidence_has_no_skip_or_xfail_escape_hatch() -> None:
    forbidden = {
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "pytest.skip",
        "pytest.xfail",
    }
    for paths in ACCEPTANCE_MAP.values():
        for relative_path in paths:
            tree = ast.parse(
                (ROOT / relative_path).read_text(encoding="utf-8"),
                filename=relative_path,
            )
            found = {
                name
                for node in ast.walk(tree)
                if (name := _dotted_name(node)) in forbidden
            }
            assert not found, f"{relative_path}: {sorted(found)}"


def test_gate2_repository_tree_is_complete_and_gate3_remains_absent() -> None:
    tree = _load(
        "tests/gate2/acceptance/test_gate2_repository_tree.py",
        "gate2_repository_tree",
    )
    tree.assert_gate2_checkpoint_tree_complete()
    tree.test_gate3_and_gate4_paths_remain_absent()


def test_gate2_alembic_head_is_exactly_0003_gate2_monitoring() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("0003")
    assert revision.revision == "0003"
    assert revision.down_revision == "0002"
    assert script.get_heads() == ["0003"]
    assert script.get_current_head() == "0003"


def test_watchdog_lock_license_and_notices_evidence_remains_exact() -> None:
    license_evidence = _load(
        "tests/gate2/acceptance/test_watchdog_license_inventory.py",
        "gate2_watchdog_license",
    )
    license_evidence.test_watchdog_is_a_runtime_dependency_with_an_exact_locked_closure()
    license_evidence.test_watchdog_approval_is_bound_to_lock_version_source_and_license_hash()
    license_evidence.test_watchdog_closure_is_complete_in_notices()


def test_supplied_hashes_and_release_blocker_remain_truthful() -> None:
    gate1 = _load(
        "tests/gate1/acceptance/test_gate1_checkpoint.py",
        "gate1_checkpoint",
    )
    gate1.test_original_supplied_file_hashes_match_normative_baseline()
    text = SPECIFICATION.read_text(encoding="utf-8")
    assert "REL-GATE-001" in text
    assert "BLOCKED_BY_ENVIRONMENT" in text
