"""Independent aggregation of the approved Gate 3 acceptance evidence."""

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
    "G3-AC01": (
        "tests/gate3/contracts/test_gate3_contracts.py",
        "tests/gate3/contracts/test_gate3_event_payloads.py",
        "tests/gate3/unit/test_gate3_authorization_retry.py",
    ),
    "G3-AC02": (
        "tests/gate3/integration/test_recovery_point_rotation.py",
        "tests/gate3/integration/test_recovery_startup_reconciliation.py",
    ),
    "G3-AC03": (
        "tests/gate3/performance/test_recovery_point_performance.py",
        "tests/gate3/ui/test_recovery_progress.py",
    ),
    "G3-AC04": ("tests/gate3/integration/test_0004_schema_contract.py",),
    "G3-AC05": (
        "tests/gate3/integration/test_concurrency_and_idempotency.py",
    ),
    "G3-AC06": ("tests/gate3/domain/test_paper_commands.py",),
    "G3-AC07": (
        "tests/gate3/domain/test_idea_commands_and_rendering.py",
        "tests/gate3/security/test_markdown_rendering.py",
    ),
    "G3-AC08": (
        "tests/gate3/domain/test_submission_state_machine.py",
    ),
    "G3-AC09": ("tests/gate3/domain/test_submission_reassignment.py",),
    "G3-AC10": (
        "tests/gate3/integration/test_command_audit_event_atomicity.py",
        "tests/gate3/integration/test_command_failure_path.py",
    ),
    "G3-AC11": ("tests/gate3/integration/test_field_level_undo.py",),
    "G3-AC12": ("tests/gate3/integration/test_undo_dependencies.py",),
    "G3-AC13": (
        "tests/gate3/integration/test_batch_command_atomicity.py",
    ),
    "G3-AC14": (
        "tests/gate3/integration/test_version_confirmation_and_dag.py",
        "tests/gate3/integration/test_candidate_decision_commands.py",
    ),
    "G3-AC15": ("tests/gate3/integration/test_relation_lifecycle.py",),
    "G3-AC16": (
        "tests/gate3/integration/test_0004_paper_version_migration.py",
        "tests/gate3/integration/test_0004_relation_migration.py",
        "tests/gate3/integration/test_0004_failure_rollback.py",
    ),
    "G3-AC17": (
        "tests/gate3/security/test_authorization_boundaries.py",
        "tests/gate3/architecture/test_gate3_ports.py",
        "tests/gate3/architecture/test_gate3_worker_boundaries.py",
        "tests/gate3/integration/test_gate3_no_network.py",
    ),
    "G3-AC18": (
        "tests/gate3/integration/test_retry_and_ambiguous_outcomes.py",
        "tests/gate3/integration/test_command_failure_path.py",
    ),
    "G3-AC19": (
        "tests/gate3/ui/test_gate3_crud_ui.py",
        "tests/gate3/ui/test_gate3_decision_undo_ui.py",
        "tests/gate3/ui/test_gate3_ui_actions.py",
        "tests/gate3/ui/test_gate3_threading_dpi.py",
    ),
    "G3-AC20": ("tests/gate3/acceptance/test_gate3_checkpoint.py",),
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


def _evidence_paths() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            path
            for paths in ACCEPTANCE_MAP.values()
            for path in paths
        )
    )


def test_g3_ac01_through_g3_ac20_have_literal_collectable_evidence() -> None:
    assert tuple(ACCEPTANCE_MAP) == tuple(
        f"G3-AC{number:02d}" for number in range(1, 21)
    )
    evidence = _evidence_paths()
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


def test_gate3_evidence_has_no_skip_or_xfail_escape_hatch() -> None:
    forbidden = {
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "pytest.skip",
        "pytest.xfail",
    }
    for relative_path in _evidence_paths():
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


def test_gate3_repository_tree_is_complete_and_gate4_is_absent() -> None:
    tree = _load(
        "tests/gate3/acceptance/test_gate3_repository_tree.py",
        "gate3_repository_tree_checkpoint",
    )
    tree.assert_gate3_checkpoint_tree_complete()
    assert tree.GATE4_PATHS.isdisjoint(tree.production_files())


def test_gate3_alembic_head_is_exactly_0004_gate3_protected_crud() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("0004")
    assert revision.revision == "0004"
    assert revision.down_revision == "0003"
    assert script.get_heads() == ["0004"]
    assert script.get_current_head() == "0004"
    assert Path(revision.path).name == "0004_gate3_protected_crud.py"


def test_gate2_freeze_ledger_and_semantic_boundaries_remain_exact() -> None:
    freeze = _load(
        "tests/gate3/acceptance/test_gate2_freeze.py",
        "gate2_freeze_checkpoint",
    )
    freeze.test_freeze_ledger_names_the_exact_gate2_baseline()
    freeze.test_freeze_ledger_binds_gate2_exclusive_files_byte_for_byte()
    freeze.test_domain_model_freezes_existing_semantic_nodes_not_the_shared_file()
    freeze.test_provider_ledger_preserves_gate2_bytes_as_an_exact_prefix()
    freeze.test_freeze_ledger_locks_candidate_and_monitoring_semantics()
    freeze.test_freeze_ledger_allows_only_reviewed_emergency_changes()


def test_locked_licenses_notices_and_supplied_hashes_remain_exact() -> None:
    gate1 = _load(
        "tests/gate1/acceptance/test_gate1_checkpoint.py",
        "gate1_checkpoint_for_gate3",
    )
    gate1.test_original_supplied_file_hashes_match_normative_baseline()

    gate2 = _load(
        "tests/gate2/acceptance/test_gate2_checkpoint.py",
        "gate2_checkpoint_for_gate3",
    )
    gate2.test_watchdog_lock_license_and_notices_evidence_remains_exact()


def test_release_gate_remains_environment_blocked_not_artificially_passed() -> None:
    text = SPECIFICATION.read_text(encoding="utf-8")
    assert "REL-GATE-001" in text
    assert "BLOCKED_BY_ENVIRONMENT" in text
