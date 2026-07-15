"""Application bootstrap boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from PySide6.QtWidgets import QApplication
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.queries.get_overview import GetOverview
from research_workspace.application.services.change_data_directory import ChangeDataDirectory
from research_workspace.application.services.initialize_application import InitializeApplication
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore
from research_workspace.infrastructure.db.repositories import SqlOverviewRepository
from research_workspace.infrastructure.db.seed import seed_foundation_data
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.logging.configure_logging import configure_logging
from research_workspace.presentation.main_window import MainWindow, create_main_window
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage


_ROOT = Path(__file__).resolve().parents[2]
_DATA_SUBDIRECTORIES = ("logs", "derived", "exports", "backups")


@dataclass(slots=True)
class ApplicationServices:
    config: AppConfig
    config_store: JsonConfigStore
    change_data_directory: ChangeDataDirectory
    get_overview: GetOverview
    engine: Engine
    session: Session


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
    change_data_directory = ChangeDataDirectory(config_store)
    initialized = InitializeApplication(config_store).execute()
    if not initialized.ok:
        return _startup_failure(change_data_directory, initialized.error.message)
    state = initialized.value
    if state.recovery is not None:
        message = (
            f"待切换目录验证失败：{state.recovery.failed_pending_data_directory}。"
            f"当前目录保持为：{state.recovery.active_data_directory}。"
        )
        return _startup_failure(change_data_directory, message)

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
        return _startup_failure(
            change_data_directory, f"应用初始化失败（{type(exc).__name__}）。"
        )


def _startup_failure(
    change_data_directory: ChangeDataDirectory, message: str
) -> BootstrapResult:
    services = type(
        "StartupServices", (), {"change_data_directory": change_data_directory}
    )()
    page = StartupErrorPage(services)
    page.show_error(message)
    return BootstrapResult(False, None, page)


def main() -> int:
    application = _qt_application()
    result = bootstrap_application()
    if result.ok:
        result.window.show()
    else:
        result.error.widget.show()
    return application.exec()
