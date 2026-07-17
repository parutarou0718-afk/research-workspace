import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PREFIXES = ("contracts", "migrations", "src")

GATE1_ADDITIONS = frozenset(
    """
contracts/background_operation.schema.json
contracts/parser_config.schema.json
contracts/permission_context.schema.json
migrations/versions/0002_gate1_import_parse.py
src/research_workspace/application/commands/__init__.py
src/research_workspace/application/commands/import_documents.py
src/research_workspace/application/dto/__init__.py
src/research_workspace/application/dto/import_dto.py
src/research_workspace/application/dto/parsing_dto.py
src/research_workspace/application/ports/filesystem.py
src/research_workspace/application/ports/operation_runner.py
src/research_workspace/application/ports/write_coordinator.py
src/research_workspace/application/queries/get_imports.py
src/research_workspace/application/services/authorization.py
src/research_workspace/application/services/import_orchestrator.py
src/research_workspace/application/services/operation_dispatcher.py
src/research_workspace/application/services/retry_policy.py
src/research_workspace/domain/capabilities.py
src/research_workspace/domain/import_model.py
src/research_workspace/domain/operations.py
src/research_workspace/domain/parsing.py
src/research_workspace/infrastructure/db/write_coordinator.py
src/research_workspace/infrastructure/filesystem/__init__.py
src/research_workspace/infrastructure/filesystem/atomic_files.py
src/research_workspace/infrastructure/filesystem/path_safety.py
src/research_workspace/infrastructure/filesystem/snapshots.py
src/research_workspace/infrastructure/filesystem/stability.py
src/research_workspace/infrastructure/parsers/__init__.py
src/research_workspace/infrastructure/parsers/docx_parser.py
src/research_workspace/infrastructure/parsers/pdf_parser.py
src/research_workspace/infrastructure/parsers/pptx_parser.py
src/research_workspace/infrastructure/parsers/table_text.py
src/research_workspace/infrastructure/workers/__init__.py
src/research_workspace/infrastructure/workers/operation_worker.py
src/research_workspace/infrastructure/workers/worker_signals.py
src/research_workspace/presentation/dialogs/__init__.py
src/research_workspace/presentation/dialogs/import_batch_dialog.py
src/research_workspace/presentation/pages/imports_page.py
src/research_workspace/presentation/view_models/imports.py
src/research_workspace/presentation/ui/imports_page.ui
src/research_workspace/presentation/ui/import_batch_dialog.ui
""".split()
)

CURRENT_GATE2_PATHS = frozenset(
    {
        "migrations/versions/0003_gate2_monitoring.py",
        "src/research_workspace/application/commands/manage_monitoring_root.py",
        "src/research_workspace/application/dto/monitoring_dto.py",
        "src/research_workspace/application/ports/file_observer.py",
        "src/research_workspace/application/queries/get_monitoring.py",
        "src/research_workspace/domain/monitoring.py",
        "src/research_workspace/domain/versioning.py",
        "src/research_workspace/infrastructure/monitoring/__init__.py",
        "src/research_workspace/infrastructure/monitoring/watchdog_observer.py",
    }
)

TASK2_CONTRACTS = frozenset(
    {
        "contracts/background_operation.schema.json",
        "contracts/parser_config.schema.json",
        "contracts/permission_context.schema.json",
    }
)

LATER_GATE_PATHS = frozenset(
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
src/research_workspace/application/dto/recovery_dto.py
src/research_workspace/application/dto/transfer_dto.py
src/research_workspace/application/ports/sqlite_backup.py
src/research_workspace/application/queries/get_version_candidates.py
src/research_workspace/application/queries/get_papers.py
src/research_workspace/application/queries/get_ideas.py
src/research_workspace/application/queries/get_submissions.py
src/research_workspace/application/queries/get_transfer_history.py
src/research_workspace/application/services/candidate_detection.py
src/research_workspace/application/services/command_dispatcher.py
src/research_workspace/application/services/recovery_points.py
src/research_workspace/application/services/relation_graph.py
src/research_workspace/domain/audit.py
src/research_workspace/domain/transfer.py
src/research_workspace/infrastructure/monitoring/reconciliation.py
src/research_workspace/infrastructure/recovery/__init__.py
src/research_workspace/infrastructure/recovery/sqlite_recovery.py
src/research_workspace/infrastructure/transfer/__init__.py
src/research_workspace/infrastructure/transfer/backup.py
src/research_workspace/infrastructure/transfer/export.py
src/research_workspace/infrastructure/transfer/restore.py
src/research_workspace/presentation/dialogs/paper_editor_dialog.py
src/research_workspace/presentation/dialogs/idea_editor_dialog.py
src/research_workspace/presentation/dialogs/submission_editor_dialog.py
src/research_workspace/presentation/dialogs/relation_review_dialog.py
src/research_workspace/presentation/dialogs/backup_dialog.py
src/research_workspace/presentation/dialogs/restore_dialog.py
src/research_workspace/presentation/dialogs/export_dialog.py
src/research_workspace/presentation/pages/monitoring_page.py
src/research_workspace/presentation/pages/version_candidates_page.py
src/research_workspace/presentation/pages/data_transfer_page.py
src/research_workspace/presentation/ui/monitoring_page.ui
src/research_workspace/presentation/ui/version_candidates_page.ui
src/research_workspace/presentation/ui/data_transfer_page.ui
src/research_workspace/presentation/ui/paper_editor_dialog.ui
src/research_workspace/presentation/ui/idea_editor_dialog.ui
src/research_workspace/presentation/ui/submission_editor_dialog.ui
src/research_workspace/presentation/ui/relation_review_dialog.ui
src/research_workspace/presentation/ui/backup_dialog.ui
src/research_workspace/presentation/ui/restore_dialog.ui
src/research_workspace/presentation/ui/export_dialog.ui
src/research_workspace/presentation/view_models/monitoring.py
src/research_workspace/presentation/view_models/version_candidates.py
src/research_workspace/presentation/view_models/papers.py
src/research_workspace/presentation/view_models/ideas.py
src/research_workspace/presentation/view_models/submissions.py
src/research_workspace/presentation/view_models/transfer.py
""".split()
)


def production_files() -> frozenset[str]:
    return frozenset(
        path.relative_to(ROOT).as_posix()
        for prefix in PRODUCTION_PREFIXES
        for path in (ROOT / prefix).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def baseline_production_files() -> frozenset[str]:
    structure_test = ROOT / "tests" / "acceptance" / "test_repository_structure.py"
    spec = importlib.util.spec_from_file_location("foundation_repository_structure", structure_test)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return frozenset(
        path
        for path in module.LOCKED_TREE_FILES
        if path.split("/", 1)[0] in PRODUCTION_PREFIXES
    )


def assert_gate1_checkpoint_tree_complete() -> None:
    actual = production_files()
    assert GATE1_ADDITIONS <= actual
    assert actual == baseline_production_files() | GATE1_ADDITIONS | CURRENT_GATE2_PATHS


def test_task2_contracts_exist_without_requiring_future_gate1_files() -> None:
    actual = production_files()
    assert TASK2_CONTRACTS <= actual
    assert actual <= (
        baseline_production_files()
        | GATE1_ADDITIONS
        | CURRENT_GATE2_PATHS
    )


def test_later_gate_production_paths_are_absent() -> None:
    assert LATER_GATE_PATHS.isdisjoint(production_files())
