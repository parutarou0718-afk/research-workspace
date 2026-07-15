"""Application bootstrap boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys

from alembic import command
from alembic.config import Config
from PySide6.QtWidgets import QApplication
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.queries.get_overview import GetOverview
from research_workspace.application.services.change_data_directory import (
    ChangeDataDirectory,
    validate_data_directory,
)
from research_workspace.application.services.initialize_application import InitializeApplication
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore
from research_workspace.infrastructure.db.base import Base
import research_workspace.infrastructure.db.models  # noqa: F401
from research_workspace.infrastructure.db.repositories import SqlOverviewRepository
from research_workspace.infrastructure.db.seed import seed_foundation_data
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.logging.configure_logging import configure_logging
from research_workspace.presentation.main_window import MainWindow, create_main_window
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


_ROOT = Path(__file__).resolve().parents[2]
_DATA_SUBDIRECTORIES = ("logs", "derived", "exports", "backups")
_EXPECTED_WORKSPACE_TABLES = frozenset((*Base.metadata.tables, "alembic_version"))


@dataclass(slots=True)
class ApplicationServices:
    config: AppConfig
    config_store: JsonConfigStore
    change_data_directory: ChangeDataDirectory
    get_overview: GetOverview
    engine: Engine
    session: Session
    closed: bool = False

    def close(self) -> None:
        if not self.closed:
            self.session.close()
            self.engine.dispose()
            self.closed = True


@dataclass(frozen=True, slots=True)
class WorkspaceInspection:
    kind: str
    path: Path
    reason: str | None = None


class WorkspaceDataDirectoryService:
    """Validate the target database before delegating a configuration write."""

    def __init__(self, config_store: JsonConfigStore):
        self._change_directory = ChangeDataDirectory(config_store)

    def inspect(self, selected: Path) -> WorkspaceInspection:
        resolved = selected.expanduser().resolve()
        database_path = resolved / "research_workspace.db"
        if not database_path.exists():
            return WorkspaceInspection("new", resolved)
        try:
            with sqlite3.connect(
                f"{database_path.as_uri()}?mode=ro", uri=True
            ) as connection:
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                version = connection.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
                inventory = frozenset(
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                )
            if (
                integrity == ("ok",)
                and version == ("0001",)
                and inventory == _EXPECTED_WORKSPACE_TABLES
            ):
                return WorkspaceInspection("existing", resolved)
        except (OSError, sqlite3.Error, ValueError):
            pass
        return WorkspaceInspection(
            "invalid", resolved, "CONFIG_WORKSPACE_INVALID：数据库或迁移版本无效。"
        )

    def execute(self, selected: Path | None):
        if selected is None:
            return self._change_directory.execute(None)
        resolved = selected.expanduser().resolve()
        writable = validate_data_directory(resolved)
        if not writable.ok:
            return writable
        before = self.inspect(resolved)
        if before.kind == "invalid":
            return Result.failure(_invalid_workspace_error())
        try:
            _run_migrations(resolved / "research_workspace.db")
        except Exception as exc:
            return Result.failure(_invalid_workspace_error(type(exc).__name__))
        if self.inspect(resolved).kind != "existing":
            return Result.failure(_invalid_workspace_error())
        return self._change_directory.execute(resolved)


def _invalid_workspace_error(exception_type: str | None = None) -> AppError:
    details = {"exception_type": exception_type} if exception_type else {}
    return AppError(
        "CONFIG_WORKSPACE_INVALID",
        "The selected directory does not contain a valid Research Workspace database.",
        details=details,
    )


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    ok: bool
    window: MainWindow | None
    error: StartupErrorPage | None

    def __post_init__(self) -> None:
        if (self.window is None) == (self.error is None):
            raise ValueError("Exactly one of window or error must be present")
        if self.ok != (self.window is not None):
            raise ValueError("Bootstrap status must match its presentation")


def _qt_application() -> QApplication:
    existing = QApplication.instance()
    return existing if existing is not None else QApplication(sys.argv[:1])


def _run_migrations(database_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")


def bootstrap_application() -> BootstrapResult:
    _qt_application()
    config_store = JsonConfigStore()
    change_data_directory = WorkspaceDataDirectoryService(config_store)
    try:
        current = config_store.load()
    except Exception:
        current = None

    def validate_startup_directory(path: Path):
        writable = validate_data_directory(path)
        if not writable.ok:
            return writable
        if (
            current is not None
            and current.pending_data_directory is not None
            and path.expanduser().resolve() == current.pending_data_directory
        ):
            inspection = change_data_directory.inspect(path)
            if inspection.kind != "existing":
                return Result.failure(_invalid_workspace_error())
        return writable

    initialized = InitializeApplication(
        config_store, validate_directory=validate_startup_directory
    ).execute()
    if not initialized.ok:
        return _startup_failure(change_data_directory, initialized.error.message)
    state = initialized.value
    if state.recovery is not None:
        message = (
            f"待切换目录验证失败：{state.recovery.failed_pending_data_directory}。"
            f"当前目录保持为：{state.recovery.active_data_directory}。"
            f"原因：{state.recovery.error.code}，{state.recovery.error.message}"
        )
        return _startup_failure(change_data_directory, message)

    engine = None
    session = None
    try:
        data_directory = state.config.active_data_directory
        for name in _DATA_SUBDIRECTORIES:
            (data_directory / name).mkdir(parents=True, exist_ok=True)
        configure_logging(data_directory / "logs", state.config.log_level)
        database_path = data_directory / "research_workspace.db"
        _run_migrations(database_path)
        engine = create_engine_for_path(database_path)
        session = session_factory(engine)()
        seed_foundation_data(session)
        services = ApplicationServices(
            config=state.config,
            config_store=config_store,
            change_data_directory=change_data_directory,
            get_overview=GetOverview(SqlOverviewRepository(session)),
            engine=engine,
            session=session,
        )
        return BootstrapResult(True, create_main_window(services), None)
    except Exception as exc:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
        return _startup_failure(
            change_data_directory, f"应用初始化失败（{type(exc).__name__}）。"
        )


def _startup_failure(
    change_data_directory: WorkspaceDataDirectoryService, message: str
) -> BootstrapResult:
    services = type(
        "StartupServices", (), {"change_data_directory": change_data_directory}
    )()
    page = StartupErrorPage(services)
    page.show_error(message)
    return BootstrapResult(False, None, page)


def main() -> int:
    application = _qt_application()
    application.setProperty("researchWorkspaceRestartExitCode", None)
    result = bootstrap_application()
    if result.ok:
        result.window.show()
    else:
        result.error.widget.show()
    event_loop_code = application.exec()
    restart_code = application.property("researchWorkspaceRestartExitCode")
    return int(restart_code) if restart_code is not None else event_loop_code
