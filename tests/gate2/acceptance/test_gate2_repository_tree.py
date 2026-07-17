import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PREFIXES = ("contracts", "migrations", "src")

GATE2_ADDITIONS = frozenset(
    """
migrations/versions/0003_gate2_monitoring.py
src/research_workspace/application/commands/manage_monitoring_root.py
src/research_workspace/application/dto/monitoring_dto.py
src/research_workspace/application/ports/file_observer.py
src/research_workspace/application/queries/get_monitoring.py
src/research_workspace/application/queries/get_version_candidates.py
src/research_workspace/application/services/candidate_detection.py
src/research_workspace/domain/monitoring.py
src/research_workspace/domain/versioning.py
src/research_workspace/infrastructure/monitoring/__init__.py
src/research_workspace/infrastructure/monitoring/reconciliation.py
src/research_workspace/infrastructure/monitoring/watchdog_observer.py
src/research_workspace/presentation/pages/monitoring_page.py
src/research_workspace/presentation/pages/version_candidates_page.py
src/research_workspace/presentation/view_models/monitoring.py
src/research_workspace/presentation/view_models/version_candidates.py
src/research_workspace/presentation/ui/monitoring_page.ui
src/research_workspace/presentation/ui/version_candidates_page.ui
""".split()
)

GATE3_AND_GATE4_PATHS = frozenset(
    """
contracts/application_command.schema.json
contracts/audit_change.schema.json
contracts/backup_manifest.schema.json
contracts/export_manifest.schema.json
migrations/versions/0004_gate3_protected_crud.py
migrations/versions/0005_gate4_transfer.py
src/research_workspace/application/commands/manage_paper.py
src/research_workspace/application/commands/manage_idea.py
src/research_workspace/application/commands/manage_submission.py
src/research_workspace/application/commands/review_relation.py
src/research_workspace/application/commands/undo_command.py
src/research_workspace/application/commands/create_backup.py
src/research_workspace/application/commands/prepare_restore.py
src/research_workspace/application/commands/create_export.py
src/research_workspace/infrastructure/recovery/sqlite_recovery.py
src/research_workspace/infrastructure/transfer/backup.py
src/research_workspace/infrastructure/transfer/export.py
src/research_workspace/infrastructure/transfer/restore.py
""".split()
)


def _gate1_module():
    path = ROOT / "tests" / "gate1" / "acceptance" / "test_gate1_repository_tree.py"
    spec = importlib.util.spec_from_file_location("gate1_repository_tree", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def production_files() -> frozenset[str]:
    return frozenset(
        path.relative_to(ROOT).as_posix()
        for prefix in PRODUCTION_PREFIXES
        for path in (ROOT / prefix).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def assert_gate2_checkpoint_tree_complete() -> None:
    gate1 = _gate1_module()
    actual = production_files()
    required = gate1.baseline_production_files() | gate1.GATE1_ADDITIONS | GATE2_ADDITIONS
    assert required <= actual


def test_gate2_checkpoint_paths_remain_present_after_forward_additions() -> None:
    gate1 = _gate1_module()
    required = gate1.baseline_production_files() | gate1.GATE1_ADDITIONS | GATE2_ADDITIONS
    assert required <= production_files()


def test_gate2_freeze_ledger_owns_later_gate_compatibility() -> None:
    assert (ROOT / "docs" / "GATE2_FREEZE.md").is_file()
