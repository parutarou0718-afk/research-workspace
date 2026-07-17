"""Application bootstrap boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
from typing import Callable
from uuid import uuid4

from alembic import command
from alembic.config import Config
from PySide6.QtWidgets import QApplication
from sqlalchemy.engine import Engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.dto.import_dto import ImportRequest
from research_workspace.application.queries.get_imports import GetImports, ImportReadRecord
from research_workspace.application.queries.get_monitoring import GetMonitoringDashboard
from research_workspace.application.queries.get_version_candidates import (
    GetVersionCandidates,
)
from research_workspace.application.commands.manage_monitoring_root import (
    ManageMonitoringRoot,
    MonitoringRootError,
)
from research_workspace.application.queries.get_overview import GetOverview
from research_workspace.application.services.change_data_directory import (
    ChangeDataDirectory,
    validate_data_directory,
)
from research_workspace.application.services.initialize_application import InitializeApplication
from research_workspace.application.services.import_orchestrator import ImportOrchestrator
from research_workspace.application.services.operation_dispatcher import ImportParsePipeline
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore
from research_workspace.infrastructure.db.base import Base
import research_workspace.infrastructure.db.models  # noqa: F401
from research_workspace.infrastructure.db.models import (
    ImportItemModel,
    SourceDocumentModel,
    SourceObservationModel,
)
from research_workspace.infrastructure.db.repositories import (
    SqlMonitoringRepository,
    SqlOverviewRepository,
)
from research_workspace.infrastructure.db.seed import seed_foundation_data
from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore
from research_workspace.infrastructure.filesystem.path_safety import normalized_path_hash
from research_workspace.infrastructure.logging.configure_logging import configure_logging
from research_workspace.infrastructure.parsers.docx_parser import DocxParser
from research_workspace.infrastructure.parsers.pdf_parser import PdfParser
from research_workspace.infrastructure.parsers.pptx_parser import PptxParser
from research_workspace.infrastructure.workers.operation_worker import (
    OperationWorker,
    ThreadedOperationRunner,
)
from research_workspace.presentation.main_window import MainWindow, create_main_window
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result
from research_workspace.domain.capabilities import PathScope, PermissionContext


_ROOT = Path(__file__).resolve().parents[2]
_DATA_SUBDIRECTORIES = (
    "sources/sha256",
    "derived/parse",
    "staging/imports",
    "staging/parse",
    "staging/backup",
    "staging/export",
    "staging/restore",
    "recovery/current",
    "recovery/previous",
    "exports",
    "backups",
    "logs",
)
SUPPORTED_SCHEMA_REVISION = "0004"
_EXPECTED_WORKSPACE_TABLES = frozenset((*Base.metadata.tables, "alembic_version"))


@dataclass(slots=True)
class ApplicationServices:
    config: AppConfig
    config_store: JsonConfigStore
    change_data_directory: ChangeDataDirectory
    get_overview: GetOverview
    get_imports: GetImports
    get_monitoring: GetMonitoringDashboard
    get_version_candidates: GetVersionCandidates
    monitoring_actions: object
    create_import_request: Callable[[tuple[Path, ...]], ImportRequest]
    engine: Engine
    session: Session
    import_parse_pipeline: ImportParsePipeline
    operation_runner: ThreadedOperationRunner
    write_coordinator: SqlWriteCoordinator
    closed: bool = False

    def close(self) -> None:
        if not self.closed:
            workers_stopped = self.operation_runner.shutdown(timeout=10)
            if workers_stopped:
                self.write_coordinator.complete_monitoring_session(
                    datetime.now(timezone.utc)
                )
            self.session.close()
            self.engine.dispose()
            self.closed = True


class _MonitoringActions:
    """Local UI composition adapter around the approved application command."""

    def __init__(self, manager, repository, workspace_id) -> None:
        self._manager = manager
        self._repository = repository
        self._workspace_id = workspace_id

    def _context(self, path: Path, root_id) -> PermissionContext:
        path_hash = normalized_path_hash(path)
        return PermissionContext(
            "1.0",
            "user",
            "local-user",
            self._workspace_id,
            ("source.observe.request",),
            (path_hash,),
            (PathScope("monitoring_root", path_hash, root_id, "list", True),),
            False,
            datetime.now(timezone.utc),
            "gate2-local-ui-1.0",
            uuid4(),
        )

    def add(self, path: Path) -> None:
        self._manager.add(path, self._context(path, uuid4()))

    def _existing(self, root_id):
        root = self._repository.get_root(root_id)
        if root is None:
            raise MonitoringRootError("MONITOR_ROOT_NOT_FOUND")
        return root

    def pause(self, root_id) -> None:
        root = self._existing(root_id)
        self._manager.pause(root_id, self._context(root.original_path, root_id))

    def resume(self, root_id) -> None:
        root = self._existing(root_id)
        self._manager.resume(root_id, self._context(root.original_path, root_id))

    def remove(self, root_id) -> None:
        root = self._existing(root_id)
        self._manager.remove(root_id, self._context(root.original_path, root_id))


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
                and version == (SUPPORTED_SCHEMA_REVISION,)
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


def _ensure_data_layout(data_directory: Path) -> None:
    for relative_path in _DATA_SUBDIRECTORIES:
        (data_directory / relative_path).mkdir(parents=True, exist_ok=True)


def _read_import_records(factory) -> tuple[ImportReadRecord, ...]:
    with factory() as read_session:
        records = read_session.execute(
            select(
                SourceObservationModel.original_filename,
                ImportItemModel.parse_status,
                ImportItemModel.error_code,
                SourceDocumentModel.block_count,
            )
            .join(
                SourceObservationModel,
                SourceObservationModel.id == ImportItemModel.source_observation_id,
            )
            .outerjoin(
                SourceDocumentModel,
                SourceDocumentModel.parse_artifact_id == ImportItemModel.parse_artifact_id,
            )
            .where(
                ImportItemModel.state.in_(("imported", "duplicate_content")),
                ImportItemModel.parse_status.in_(("succeeded", "failed")),
            )
            .order_by(ImportItemModel.created_at.desc(), ImportItemModel.id)
            .limit(100)
        ).all()
    return tuple(ImportReadRecord(*record) for record in records)


def _create_import_request(paths: tuple[Path, ...], workspace_id) -> ImportRequest:
    normalized_paths = tuple(Path(path) for path in paths)
    hashes = tuple(normalized_path_hash(path) for path in normalized_paths)
    context = PermissionContext(
        schema_version="1.0",
        actor_type="user",
        actor_id="local-user",
        workspace_id=workspace_id,
        capabilities=("source.snapshot_import.request", "document.parse.request"),
        scope_refs=hashes,
        path_scopes=tuple(
            PathScope("import_source", path_hash, uuid4(), "copy", False)
            for path_hash in hashes
        ),
        network_allowed=False,
        granted_at=datetime.now(timezone.utc),
        policy_version="gate1-local-ui-1.0",
        authorization_decision_id=uuid4(),
    )
    return ImportRequest(normalized_paths, context)


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
        _ensure_data_layout(data_directory)
        configure_logging(data_directory / "logs", state.config.log_level)
        database_path = data_directory / "research_workspace.db"
        _run_migrations(database_path)
        engine = create_engine_for_path(database_path)
        factory = session_factory(engine)
        session = factory()
        seed_foundation_data(session)
        coordinator = SqlWriteCoordinator(factory, data_directory=data_directory)
        coordinator.begin_monitoring_session(datetime.now(timezone.utc))
        snapshot_store = SnapshotStore(data_directory)
        parsers = (DocxParser(), PdfParser(), PptxParser())
        parser_registry = {parser.parser_id: parser for parser in parsers}
        operation_runner = ThreadedOperationRunner(
            OperationWorker(snapshot_store, parser_registry)
        )
        import_parse_pipeline = ImportParsePipeline(
            data_directory,
            ImportOrchestrator(data_directory, snapshot_store, coordinator),
            coordinator,
            operation_runner,
            parsers,
        )
        monitoring_repository = SqlMonitoringRepository(session)
        monitoring_actions = _MonitoringActions(
            ManageMonitoringRoot(
                data_directory, coordinator, monitoring_repository
            ),
            monitoring_repository,
            coordinator.workspace_id(),
        )
        services = ApplicationServices(
            config=state.config,
            config_store=config_store,
            change_data_directory=change_data_directory,
            get_overview=GetOverview(SqlOverviewRepository(session)),
            get_imports=GetImports(lambda: _read_import_records(factory)),
            get_monitoring=GetMonitoringDashboard(factory),
            get_version_candidates=GetVersionCandidates(factory),
            monitoring_actions=monitoring_actions,
            create_import_request=lambda paths: _create_import_request(
                tuple(paths), coordinator.workspace_id()
            ),
            engine=engine,
            session=session,
            import_parse_pipeline=import_parse_pipeline,
            operation_runner=operation_runner,
            write_coordinator=coordinator,
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
