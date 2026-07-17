from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PREFIXES = ("contracts", "migrations", "src")

GATE3_ADDITIONS = frozenset(
    """
contracts/application_command.schema.json
contracts/audit_change.schema.json
migrations/versions/0004_gate3_protected_crud.py
src/research_workspace/application/commands/manage_paper.py
src/research_workspace/application/commands/manage_idea.py
src/research_workspace/application/commands/manage_submission.py
src/research_workspace/application/commands/review_relation.py
src/research_workspace/application/commands/undo_command.py
src/research_workspace/application/dto/recovery_dto.py
src/research_workspace/application/ports/sqlite_backup.py
src/research_workspace/application/ports/ai_provider.py
src/research_workspace/application/queries/get_papers.py
src/research_workspace/application/queries/get_ideas.py
src/research_workspace/application/queries/get_submissions.py
src/research_workspace/application/services/command_dispatcher.py
src/research_workspace/application/services/recovery_points.py
src/research_workspace/application/services/relation_graph.py
src/research_workspace/application/services/paper_ai_analysis.py
src/research_workspace/domain/audit.py
src/research_workspace/infrastructure/ai/__init__.py
src/research_workspace/infrastructure/ai/openai_compatible.py
src/research_workspace/infrastructure/config/ai_settings_store.py
src/research_workspace/infrastructure/recovery/__init__.py
src/research_workspace/infrastructure/recovery/sqlite_recovery.py
src/research_workspace/presentation/localization.py
src/research_workspace/presentation/dialogs/paper_editor_dialog.py
src/research_workspace/presentation/dialogs/idea_editor_dialog.py
src/research_workspace/presentation/dialogs/submission_editor_dialog.py
src/research_workspace/presentation/dialogs/relation_review_dialog.py
src/research_workspace/presentation/pages/relations_page.py
src/research_workspace/presentation/ui/paper_editor_dialog.ui
src/research_workspace/presentation/ui/idea_editor_dialog.ui
src/research_workspace/presentation/ui/submission_editor_dialog.ui
src/research_workspace/presentation/ui/relation_review_dialog.ui
src/research_workspace/presentation/ui/relations_page.ui
src/research_workspace/presentation/view_models/papers.py
src/research_workspace/presentation/view_models/ideas.py
src/research_workspace/presentation/view_models/submissions.py
""".split()
)

GATE4_PATHS = frozenset(
    """
contracts/backup_manifest.schema.json
contracts/export_manifest.schema.json
migrations/versions/0005_gate4_transfer.py
src/research_workspace/application/commands/create_backup.py
src/research_workspace/application/commands/prepare_restore.py
src/research_workspace/application/commands/create_export.py
src/research_workspace/application/dto/transfer_dto.py
src/research_workspace/application/queries/get_transfer_history.py
src/research_workspace/domain/transfer.py
src/research_workspace/infrastructure/transfer/backup.py
src/research_workspace/infrastructure/transfer/export.py
src/research_workspace/infrastructure/transfer/restore.py
src/research_workspace/presentation/pages/data_transfer_page.py
src/research_workspace/presentation/ui/data_transfer_page.ui
src/research_workspace/presentation/view_models/transfer.py
""".split()
)


def _gate2_module():
    path = ROOT / "tests" / "gate2" / "acceptance" / "test_gate2_repository_tree.py"
    spec = importlib.util.spec_from_file_location("gate2_repository_tree", path)
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


def gate3_allowed_production_files() -> frozenset[str]:
    gate2 = _gate2_module()
    gate1 = gate2._gate1_module()
    return (
        gate1.baseline_production_files()
        | gate1.GATE1_ADDITIONS
        | gate2.GATE2_ADDITIONS
        | GATE3_ADDITIONS
    )


def assert_gate3_checkpoint_tree_complete() -> None:
    assert production_files() == gate3_allowed_production_files()


def test_existing_production_paths_are_baseline_or_allowed_gate3_paths() -> None:
    assert production_files() <= gate3_allowed_production_files()


def test_gate4_paths_remain_absent() -> None:
    assert GATE4_PATHS.isdisjoint(production_files())
