from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = ROOT / "tests" / "gate1" / "fixtures"
PRODUCTION_PREFIXES = ("contracts", "migrations", "src")

ORIGINAL_BASELINE = {
    "assets/ui_reference.png": "0fcac091f9c937b86dfbd185d91d20f03174b8ac53c1cbee602368a3de066447",
    "docs/ARCHITECTURE.md": "922f549c1dee714ab644fd81f27f04ee2b057e2a61f9cef25b6b69522367c5b7",
    "docs/CODEX_INSTRUCTIONS.md": "71382baff36f57fe678f12dbd0e38f0972690f15d50311cd6b5c34892cd01d9f",
    "docs/PRD.docx": "f53987f664369f3d663bc0fcdfe6884c9db6f41aa3426c7595c311d2698a39a1",
    "docs/PRD.md": "5924de57c607196640000759bffeb4ff4b4d199db9666988e1ccf4b6242758d6",
    "docs/UI_SPEC.md": "7166ac6a8be411cf5e2c20a21dd8a6fd8eb92f8fa165a1dc9bb284a39333e257",
    "ui/design_tokens.json": "b99866f590cb3699ffde5f8e91ecff3fe8556d259b34eb0bfe87e01327a7ec3f",
    "ui/research_workspace_main.ui": "d502b62686815c1c5e03d25da9534f333595f1ad4b7e0cf36c5bba5eede00461",
}

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

LATER_GATE_PATHS = frozenset(
    """
contracts/application_command.schema.json
contracts/audit_change.schema.json
contracts/backup_manifest.schema.json
contracts/export_manifest.schema.json
migrations/versions/0004_gate3_protected_crud.py
migrations/versions/0005_gate4_transfer.py
src/research_workspace/application/commands/manage_monitoring_root.py
src/research_workspace/application/commands/manage_paper.py
src/research_workspace/application/commands/manage_idea.py
src/research_workspace/application/commands/manage_submission.py
src/research_workspace/application/commands/review_relation.py
src/research_workspace/application/commands/undo_command.py
src/research_workspace/application/commands/create_backup.py
src/research_workspace/application/commands/prepare_restore.py
src/research_workspace/application/commands/create_export.py
src/research_workspace/application/dto/monitoring_dto.py
src/research_workspace/application/dto/recovery_dto.py
src/research_workspace/application/dto/transfer_dto.py
src/research_workspace/application/ports/file_observer.py
src/research_workspace/application/ports/sqlite_backup.py
src/research_workspace/application/queries/get_monitoring.py
src/research_workspace/application/queries/get_version_candidates.py
src/research_workspace/application/queries/get_papers.py
src/research_workspace/application/queries/get_ideas.py
src/research_workspace/application/queries/get_submissions.py
src/research_workspace/application/queries/get_transfer_history.py
src/research_workspace/application/services/candidate_detection.py
src/research_workspace/application/services/command_dispatcher.py
src/research_workspace/application/services/recovery_points.py
src/research_workspace/application/services/relation_graph.py
src/research_workspace/domain/monitoring.py
src/research_workspace/domain/versioning.py
src/research_workspace/domain/audit.py
src/research_workspace/domain/transfer.py
src/research_workspace/infrastructure/monitoring/__init__.py
src/research_workspace/infrastructure/monitoring/reconciliation.py
src/research_workspace/infrastructure/monitoring/watchdog_observer.py
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

ACCEPTANCE_EVIDENCE = (
    "tests/gate1/acceptance/test_gate1_repository_tree.py",
    "tests/gate1/ui/test_import_ui_contract.py",
    "tests/gate1/acceptance/test_gate1_license_inventory.py",
    "tests/acceptance/test_license_policy.py",
    "tests/gate1/integration/test_snapshot_commit_protocol.py",
    "tests/gate1/integration/test_import_safe_failures.py",
    "tests/gate1/integration/test_snapshot_dedup_provenance.py",
    "tests/gate1/unit/test_import_path_safety.py",
    "tests/gate1/ui/test_import_disclosure.py",
    "tests/gate1/integration/test_import_batch_state.py",
    "tests/gate1/integration/test_parse_revision_and_attempts.py",
    "tests/gate1/contracts/test_parsed_document_v2.py",
    "tests/gate1/integration/test_parsed_output_commit.py",
    "tests/gate1/parsers/test_docx_adapter.py",
    "tests/gate1/parsers/test_pdf_adapter.py",
    "tests/gate1/parsers/test_pptx_adapter.py",
    "tests/gate1/ui/test_parse_status_vocabulary.py",
    "tests/gate1/integration/test_parse_preference_history.py",
    "tests/gate1/architecture/test_worker_boundaries.py",
    "tests/gate1/acceptance/test_no_network.py",
    "tests/gate1/integration/test_0002_legacy_source_migration.py",
    "tests/gate1/acceptance/test_source_integrity.py",
    "tests/unit/application/test_privacy_safe_logging.py",
    "tests/gate1/integration/test_gate1_domain_event_outbox.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_files() -> frozenset[str]:
    return frozenset(
        path.relative_to(ROOT).as_posix()
        for prefix in PRODUCTION_PREFIXES
        for path in (ROOT / prefix).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _foundation_production_files() -> frozenset[str]:
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


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return None


def test_original_supplied_file_hashes_match_normative_baseline() -> None:
    actual = {relative_path: _sha256(ROOT / relative_path) for relative_path in ORIGINAL_BASELINE}
    assert actual == ORIGINAL_BASELINE


def test_fixture_manifest_exactly_matches_committed_fixture_bytes() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["fixtures"]
    declared = {entry["relative_path"] for entry in entries}
    actual = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for suffix in ("*.docx", "*.pdf", "*.pptx")
        for path in FIXTURE_ROOT.rglob(suffix)
    }
    assert manifest["schema_version"] == "1.0"
    assert len(declared) == len(entries)
    assert declared == actual
    for entry in entries:
        fixture = FIXTURE_ROOT / entry["relative_path"]
        assert fixture.stat().st_size == entry["size_bytes"]
        assert _sha256(fixture) == entry["sha256"]


def test_complete_gate1_repository_tree_and_later_gate_absence() -> None:
    actual = _production_files()
    assert actual == (
        _foundation_production_files()
        | GATE1_ADDITIONS
        | {"migrations/versions/0003_gate2_monitoring.py"}
    )
    assert LATER_GATE_PATHS.isdisjoint(actual)


def test_alembic_retains_gate1_revision_in_gate2_chain() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_revision("0002").down_revision == "0001"
    assert script.get_heads() == ["0003"]
    assert script.get_current_head() == "0003"


def test_all_acceptance_evidence_modules_exist_collect_and_have_no_skip_or_xfail() -> None:
    for relative_path in ACCEPTANCE_EVIDENCE:
        assert (ROOT / relative_path).is_file(), relative_path

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *ACCEPTANCE_EVIDENCE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = (result.stdout + result.stderr).replace("\\", "/")
    for relative_path in ACCEPTANCE_EVIDENCE:
        assert relative_path in collected, relative_path

    forbidden = {
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "pytest.skip",
        "pytest.xfail",
    }
    for relative_path in ACCEPTANCE_EVIDENCE:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"), filename=relative_path)
        found = sorted(
            name
            for node in ast.walk(tree)
            if (name := _dotted_name(node)) in forbidden
        )
        assert not found, f"{relative_path}: {found}"


def test_mixed_dpi_release_gate_remains_environment_blocked_only() -> None:
    specification = (
        ROOT / "docs" / "superpowers" / "specs" / "2026-07-16-v0.2-deterministic-design.md"
    ).read_text(encoding="utf-8")
    assert "REL-GATE-001" in specification
    assert "BLOCKED_BY_ENVIRONMENT" in specification
    assert "Blocks public packaged release only; does not block internal v0.2 development." in specification
