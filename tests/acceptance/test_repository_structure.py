from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPROVED_IMPLEMENTATION_PLANS = frozenset(
    {
        "docs/superpowers/plans/2026-07-16-v0.1-foundation.md",
        "docs/superpowers/plans/2026-07-16-v0.2-gate1.md",
        "docs/superpowers/plans/2026-07-17-v0.2-gate2.md",
        "docs/superpowers/plans/2026-07-17-v0.2-gate3.md",
    }
)
LOCKED_ROOT_FILES = {
    ".gitignore",
    ".python-version",
    "app.py",
    "pyproject.toml",
    "uv.lock",
    "alembic.ini",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
}
LOCKED_TREE_FILES = frozenset(
    """
assets/ui_reference.png
ui/design_tokens.json
ui/research_workspace_main.ui
contracts/domain_model.json
contracts/background_operation.schema.json
contracts/task_contract.schema.json
contracts/task_result.schema.json
contracts/event_contract.schema.json
contracts/parser_config.schema.json
contracts/parsed_document.schema.json
contracts/permission_context.schema.json
contracts/provider_interfaces.md
migrations/env.py
migrations/script.py.mako
migrations/versions/0001_foundation_schema.py
src/research_workspace/__init__.py
src/research_workspace/bootstrap.py
src/research_workspace/presentation/__init__.py
src/research_workspace/presentation/main_window.py
src/research_workspace/presentation/pages/__init__.py
src/research_workspace/presentation/pages/overview_page.py
src/research_workspace/presentation/pages/papers_page.py
src/research_workspace/presentation/pages/ideas_page.py
src/research_workspace/presentation/pages/submissions_page.py
src/research_workspace/presentation/pages/conferences_page.py
src/research_workspace/presentation/pages/grants_page.py
src/research_workspace/presentation/pages/settings_page.py
src/research_workspace/presentation/pages/startup_error_page.py
src/research_workspace/presentation/view_models/__init__.py
src/research_workspace/presentation/view_models/overview.py
src/research_workspace/presentation/ui/main_window.ui
src/research_workspace/presentation/ui/overview_page.ui
src/research_workspace/presentation/ui/papers_page.ui
src/research_workspace/presentation/ui/ideas_page.ui
src/research_workspace/presentation/ui/submissions_page.ui
src/research_workspace/presentation/ui/conferences_page.ui
src/research_workspace/presentation/ui/grants_page.ui
src/research_workspace/presentation/ui/settings_page.ui
src/research_workspace/presentation/ui/startup_error_page.ui
src/research_workspace/presentation/ui/design_tokens.json
src/research_workspace/application/__init__.py
src/research_workspace/application/ports/__init__.py
src/research_workspace/application/ports/repositories.py
src/research_workspace/application/ports/config_store.py
src/research_workspace/application/ports/document_parser.py
src/research_workspace/application/ports/event_bus.py
src/research_workspace/application/ports/task_executor.py
src/research_workspace/application/queries/__init__.py
src/research_workspace/application/queries/get_overview.py
src/research_workspace/application/services/__init__.py
src/research_workspace/application/services/initialize_application.py
src/research_workspace/application/services/change_data_directory.py
src/research_workspace/domain/__init__.py
src/research_workspace/domain/entities.py
src/research_workspace/domain/enums.py
src/research_workspace/domain/relations.py
src/research_workspace/domain/tasks.py
src/research_workspace/domain/events.py
src/research_workspace/infrastructure/__init__.py
src/research_workspace/infrastructure/config/__init__.py
src/research_workspace/infrastructure/config/json_config_store.py
src/research_workspace/infrastructure/db/__init__.py
src/research_workspace/infrastructure/db/base.py
src/research_workspace/infrastructure/db/models.py
src/research_workspace/infrastructure/db/session.py
src/research_workspace/infrastructure/db/repositories.py
src/research_workspace/infrastructure/db/seed.py
src/research_workspace/infrastructure/logging/__init__.py
src/research_workspace/infrastructure/logging/configure_logging.py
src/research_workspace/shared/__init__.py
src/research_workspace/shared/errors.py
src/research_workspace/shared/ids.py
src/research_workspace/shared/result.py
src/research_workspace/shared/time.py
""".split()
)


def test_foundation_structure_remains_present_during_gate1() -> None:
    actual_root = {path.name for path in ROOT.iterdir() if path.is_file()}
    assert actual_root == LOCKED_ROOT_FILES
    actual_tree = {
        path.relative_to(ROOT).as_posix()
        for prefix in ("assets", "ui", "contracts", "migrations", "src")
        for path in (ROOT / prefix).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert LOCKED_TREE_FILES <= actual_tree


def test_approved_implementation_plans_are_present() -> None:
    assert all((ROOT / path).is_file() for path in APPROVED_IMPLEMENTATION_PLANS)
