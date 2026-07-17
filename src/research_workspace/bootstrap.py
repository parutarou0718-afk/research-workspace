"""Application bootstrap boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Callable
from uuid import uuid4

from alembic import command
from alembic.config import Config
from PySide6.QtWidgets import QApplication
import rfc8785
from sqlalchemy.engine import Engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_workspace.application.commands.manage_idea import (
    IdeaDependencies, create_idea, restore_idea, soft_delete_idea, update_idea)
from research_workspace.application.ports.config_store import AppConfig
from research_workspace.application.commands.manage_paper import (
    PaperDependencies, PaperVersionRef, create_paper, restore_paper,
    set_current_version, soft_delete_paper, update_paper)
from research_workspace.application.commands.review_relation import (
    RelationLifecycleRecord, confirm_candidate, reconsider_candidate,
    reject_candidate, retract_relation)
from research_workspace.application.commands.undo_command import plan_compensating_undo
from research_workspace.application.commands.manage_submission import (
    SubmissionVersionRef,
    create_submission,
    restore_submission,
    soft_delete_submission,
    transition_submission,
    update_submission,
)
from research_workspace.application.dto.import_dto import ImportRequest
from research_workspace.application.queries.get_imports import GetImports, ImportReadRecord
from research_workspace.application.queries.get_ideas import GetIdeasQuery
from research_workspace.application.queries.get_monitoring import GetMonitoringDashboard
from research_workspace.application.queries.get_papers import GetPapersQuery
from research_workspace.application.queries.get_submissions import GetSubmissionsQuery
from research_workspace.application.queries.get_version_candidates import (
    GetSafeUndoQuery, GetVersionCandidates, build_decision_review_bundle,
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
from research_workspace.application.services.command_dispatcher import (
    CommandDispatcher, RawCommandEnvelope)
from research_workspace.application.services.operation_dispatcher import (
    ImportParsePipeline,
    ProtectedCommandPipeline,
)
from research_workspace.application.services.recovery_points import RecoveryPointService
from research_workspace.application.services.relation_graph import (
    ParseContextRef, RetractionDependencies, VersionEdge,
    change_version_context, retract_version_membership)
from research_workspace.infrastructure.config.json_config_store import JsonConfigStore
from research_workspace.infrastructure.db.base import Base
import research_workspace.infrastructure.db.models  # noqa: F401
from research_workspace.infrastructure.db.models import (
    EntityRelationModel, ImportItemModel, PaperModel,
    PaperVersionModel, ParseArtifactModel, SourceDocumentModel,
    SourceObservationModel,
)
from research_workspace.infrastructure.db.repositories import (
    SqlIdeaReadRepository,
    SqlMonitoringRepository,
    SqlOverviewRepository,
    SqlPaperReadRepository,
    SqlSubmissionReadRepository,
    SqlUndoHistoryRepository,
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
from research_workspace.infrastructure.recovery.sqlite_recovery import (
    SQLiteRecoveryAdapter,
)
from research_workspace.infrastructure.workers.operation_worker import (
    OperationWorker,
    ThreadedOperationRunner,
)
from research_workspace.presentation.main_window import MainWindow, create_main_window
from research_workspace.presentation.pages.startup_error_page import StartupErrorPage
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result
from research_workspace.domain.capabilities import PathScope, PermissionContext
from research_workspace.domain.enums import PaperStatus
from research_workspace.domain.entities import Paper
from research_workspace.domain.versioning import PaperVersionRecord


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
    get_papers: GetPapersQuery
    get_ideas: GetIdeasQuery
    get_submissions: GetSubmissionsQuery
    crud_actions: object
    get_safe_undo: object
    decision_actions: object
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


class _CrudActions:
    """Composition-only adapter from UI values to approved protected commands."""

    def __init__(self, pipeline, workspace_id, session, papers, ideas, submissions):
        self._pipeline = pipeline
        self._workspace_id = workspace_id
        self._session = session
        self._queries = {"Paper": papers, "Idea": ideas, "Submission": submissions}

    def _start(
        self, command_type, entity_type, entity_id, version, payload, builder
    ):
        command_id = uuid4()
        envelope = RawCommandEnvelope(
            command_id, command_type, "1.0", str(command_id), "user",
            "local-user", self._workspace_id, datetime.now(timezone.utc),
            rfc8785.dumps(payload),
        )
        expected = ((entity_type, entity_id, version),) if version is not None else ()
        return self._pipeline.start(
            envelope, capability=f"{entity_type.casefold()}.write",
            entity_scopes=((entity_type, entity_id),),
            expected_versions=expected,
            build_mutations=lambda plan: (builder(plan),),
        )

    def _get(self, entity_type, entity_id):
        self._session.expire_all()
        getter = getattr(self._queries[entity_type], f"get_{entity_type.casefold()}")
        return getter(entity_id)

    def _version(self, version_id):
        if version_id is None:
            return None
        self._session.expire_all()
        row = self._session.get(PaperVersionModel, version_id)
        return None if row is None else SubmissionVersionRef(
            row.id, row.paper_id, row.lifecycle_state)

    def create_paper(self, title, status):
        identity = uuid4()
        return self._start(
            "paper.create", "Paper", identity, None,
            {"paper_id": str(identity), "title": title, "status": status},
            lambda plan: create_paper(
                plan.command_id, identity, title, status, _now()),
        )

    def update_paper(self, identity, title, status):
        before = self._get("Paper", identity)
        return self._start(
            "paper.update", "Paper", identity, before.row_version,
            {"paper_id": str(identity), "title": title, "status": status},
            lambda plan: update_paper(
                self._get("Paper", identity), plan.command_id,
                title=title, status=status, now=_now(),
            ),
        )

    def delete_paper(self, identity):
        before = self._get("Paper", identity)
        return self._start(
            "paper.soft_delete", "Paper", identity, before.row_version,
            {"paper_id": str(identity)},
            lambda plan: soft_delete_paper(
                self._get("Paper", identity), plan.command_id, _now(),
                PaperDependencies(),
            ),
        )

    def restore_paper(self, identity):
        before = self._get("Paper", identity)
        return self._start(
            "paper.restore", "Paper", identity, before.row_version,
            {"paper_id": str(identity)},
            lambda plan: restore_paper(
                self._get("Paper", identity), plan.command_id, _now()),
        )

    def create_idea(self, title, content, status):
        identity = uuid4()
        return self._start(
            "idea.create", "Idea", identity, None,
            {"idea_id": str(identity), "title": title,
             "content": content, "status": status},
            lambda plan: create_idea(
                plan.command_id, identity, title, content, status, _now()),
        )

    def update_idea(self, identity, title, content, status):
        before = self._get("Idea", identity)
        return self._start(
            "idea.update", "Idea", identity, before.row_version,
            {"idea_id": str(identity), "title": title,
             "content": content, "status": status},
            lambda plan: update_idea(
                self._get("Idea", identity), plan.command_id, title=title,
                content=content, status=status, now=_now(),
            ),
        )

    def delete_idea(self, identity):
        before = self._get("Idea", identity)
        return self._start(
            "idea.soft_delete", "Idea", identity, before.row_version,
            {"idea_id": str(identity)},
            lambda plan: soft_delete_idea(
                self._get("Idea", identity), plan.command_id, _now(),
                IdeaDependencies(),
            ),
        )

    def restore_idea(self, identity):
        before = self._get("Idea", identity)
        return self._start(
            "idea.restore", "Idea", identity, before.row_version,
            {"idea_id": str(identity)},
            lambda plan: restore_idea(
                self._get("Idea", identity), plan.command_id, _now()),
        )

    def create_submission(self, paper_id, venue, status):
        identity = uuid4()
        return self._start(
            "submission.create", "Submission", identity, None,
            {"submission_id": str(identity), "paper_id": str(paper_id),
             "venue": venue, "status": status},
            lambda plan: create_submission(
                plan.command_id, identity, paper_id, venue, status,
                None, None, None, _now(),
            ),
        )

    def update_submission(self, identity, venue):
        before = self._get("Submission", identity)
        return self._start(
            "submission.update", "Submission", identity, before.row_version,
            {"submission_id": str(identity), "venue": venue},
            lambda plan: self._update_submission(plan, identity, venue),
        )

    def _update_submission(self, plan, identity, venue):
        current = self._get("Submission", identity)
        return update_submission(
            current, plan.command_id, venue=venue,
            deadline_at=current.deadline_at,
            active_version=self._version(current.active_version_id), now=_now(),
        )

    def transition_submission(self, identity, status):
        before = self._get("Submission", identity)
        return self._start(
            "submission.transition", "Submission", identity, before.row_version,
            {"submission_id": str(identity), "status": status},
            lambda plan: self._transition_submission(
                plan, identity, status),
        )

    def _transition_submission(self, plan, identity, status):
        current, now = self._get("Submission", identity), _now()
        return transition_submission(
            current, plan.command_id, status,
            submitted_at=now if current.submitted_at is None else current.submitted_at,
            active_version=self._version(current.active_version_id), now=now,
        )

    def delete_submission(self, identity):
        before = self._get("Submission", identity)
        return self._start(
            "submission.soft_delete", "Submission", identity, before.row_version,
            {"submission_id": str(identity)},
            lambda plan: soft_delete_submission(
                self._get("Submission", identity), plan.command_id, _now()),
        )

    def restore_submission(self, identity):
        before = self._get("Submission", identity)
        return self._start(
            "submission.restore", "Submission", identity, before.row_version,
            {"submission_id": str(identity)},
            lambda plan: restore_submission(
                self._get("Submission", identity), plan.command_id, _now()),
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SafeUndoQuery:
    def __init__(self, factory) -> None:
        self._factory = factory

    def execute(self, *, as_of):
        with self._factory() as session:
            return GetSafeUndoQuery(
                SqlUndoHistoryRepository(session)).execute(as_of=as_of)


class _UndoDispatcher:
    def __init__(self, delegate, original_command_id) -> None:
        self._delegate, self._original_command_id = delegate, original_command_id

    def prepare(self, *args, **kwargs):
        return self._delegate.prepare(
            *args, **kwargs, undo_of_command_id=self._original_command_id)

    def commit_prepared(self, *args, **kwargs):
        return self._delegate.commit_prepared(*args, **kwargs)


class _DecisionActions:
    """Composition of approved decision/version/undo commands."""

    def __init__(
        self, pipeline, dispatcher, runner, next_generation,
        workspace_id, factory, candidates,
    ) -> None:
        self._pipeline, self._dispatcher, self._runner = pipeline, dispatcher, runner
        self._next_generation, self._workspace_id = next_generation, workspace_id
        self._factory, self._candidates = factory, candidates

    def _candidate(self, identity):
        return next(
            (item for item in self._candidates.execute()
             if item.candidate_id == identity),
            None,
        )

    def _start(
        self, pipeline, command_type, capability, scopes, expected, payload, builder
    ):
        command_id = uuid4()
        envelope = RawCommandEnvelope(
            command_id, command_type, "1.0", str(command_id), "user",
            "local-user", self._workspace_id, _now(), rfc8785.dumps(payload))
        return pipeline.start(
            envelope, capability=capability, entity_scopes=tuple(scopes),
            expected_versions=tuple(expected),
            build_mutations=lambda plan: tuple(builder(plan)),
        )

    def review(self, candidate_id):
        candidate = self._candidate(candidate_id)
        if candidate is None:
            raise LookupError("CANDIDATE_NOT_FOUND")
        with self._factory() as session:
            versions = session.scalars(select(PaperVersionModel).where(
                PaperVersionModel.source_snapshot_id.in_((
                    candidate.earlier_snapshot_id,
                    candidate.later_snapshot_id,
                ))
            )).all()
            version_ids = tuple(row.id for row in versions)
            relations = (
                session.scalars(select(EntityRelationModel).where(
                    EntityRelationModel.relation_type == "version_successor_of",
                    EntityRelationModel.source_id.in_(version_ids),
                    EntityRelationModel.target_id.in_(version_ids),
                )).all()
                if version_ids else ()
            )
        return build_decision_review_bundle(
            candidate, version_ids, tuple(row.id for row in relations))

    def reject_candidate(self, candidate_id):
        candidate = self._candidate(candidate_id)
        return self._candidate_action(
            candidate, "candidate.reject", reject_candidate)

    def reconsider_candidate(self, candidate_id):
        candidate = self._candidate(candidate_id)
        return self._candidate_action(
            candidate, "candidate.reconsider", reconsider_candidate)

    def _candidate_action(self, candidate, command_type, command):
        if candidate is None:
            raise LookupError("CANDIDATE_NOT_FOUND")
        return self._start(
            self._pipeline, command_type, "relation.review",
            (("PaperVersionCandidate", candidate.candidate_id),),
            (("PaperVersionCandidate", candidate.candidate_id,
              candidate.row_version),),
            {"candidate_id": str(candidate.candidate_id)},
            lambda plan: (command(
                self._candidate(candidate.candidate_id), plan.command_id, _now()),),
        )

    def confirm_candidate(
        self, candidate_id, paper_id, earlier_label, later_label
    ):
        candidate = self._candidate(candidate_id)
        if candidate is None:
            raise LookupError("CANDIDATE_NOT_FOUND")
        return self._start(
            self._pipeline, "candidate.confirm", "relation.review",
            (("PaperVersionCandidate", candidate_id), ("Paper", paper_id)),
            (("PaperVersionCandidate", candidate_id, candidate.row_version),),
            {"candidate_id": str(candidate_id), "paper_id": str(paper_id),
             "earlier_label": earlier_label, "later_label": later_label},
            lambda plan: self._confirm(
                plan, candidate_id, paper_id, earlier_label, later_label),
        )

    def _confirm(self, plan, candidate_id, paper_id, earlier_label, later_label):
        candidate = self._candidate(candidate_id)
        with self._factory() as session:
            versions = tuple(self._version(row) for row in session.scalars(
                select(PaperVersionModel)).all())
            rows = session.scalars(select(EntityRelationModel).where(
                EntityRelationModel.relation_type == "version_successor_of",
                EntityRelationModel.lifecycle_state == "active")).all()
            by_id = {version.id: version for version in versions}
            edges = tuple(
                VersionEdge(row.id, by_id[row.source_id].paper_id,
                            row.source_id, row.target_id)
                for row in rows
                if (
                    row.source_id in by_id
                    and row.target_id in by_id
                    and by_id[row.source_id].paper_id == paper_id
                )
            )
        return confirm_candidate(
            candidate, plan.command_id, paper_id, earlier_label, later_label,
            versions, edges, uuid4(), uuid4(), uuid4(), _now())

    @staticmethod
    def _version(row):
        return PaperVersionRecord(
            row.id, row.paper_id, row.source_snapshot_id,
            row.context_parse_artifact_id, row.version_label,
            row.normalized_version_label, row.lifecycle_state, row.row_version,
            row.created_at, row.confirmed_by_command_id, row.updated_at,
            row.updated_by_command_id, row.retracted_at,
            row.retracted_by_command_id)

    def _version_row(self, identity):
        with self._factory() as session:
            row = session.get(PaperVersionModel, identity)
            return None if row is None else self._version(row)

    def set_current_version(self, version_id):
        version = self._version_row(version_id)
        with self._factory() as session:
            row = session.get(PaperModel, version.paper_id)
            paper = Paper(
                row.id, row.title, PaperStatus(row.status), row.current_version_id,
                row.created_at, row.updated_at, row.deleted_at, row.row_version,
                row.created_by_command_id, row.updated_by_command_id,
                row.deleted_by_command_id)
        return self._start(
            self._pipeline, "paper.set_current_version", "paper.write",
            (("Paper", paper.id),), (("Paper", paper.id, paper.row_version),),
            {"paper_id": str(paper.id), "paper_version_id": str(version_id)},
            lambda plan: (set_current_version(
                paper, plan.command_id,
                PaperVersionRef(version.id, version.paper_id,
                                version.lifecycle_state), _now()),),
        )

    def change_version_context(self, version_id, context_id):
        version = self._version_row(version_id)
        context = None
        if context_id is not None:
            with self._factory() as session:
                row = session.get(ParseArtifactModel, context_id)
                if row is not None:
                    context = ParseContextRef(
                        row.id, row.source_snapshot_id, row.status)
        return self._version_action(
            version, "paper_version.change_context",
            lambda plan: change_version_context(
                self._version_row(version_id), plan.command_id, context, _now()),
            {"context_parse_artifact_id": (
                str(context_id) if context_id else None)},
        )

    def retract_version(self, version_id):
        version = self._version_row(version_id)
        return self._version_action(
            version, "paper_version.retract",
            lambda plan: retract_version_membership(
                self._version_row(version_id), plan.command_id, _now(),
                RetractionDependencies()),
            {},
        )

    def _version_action(self, version, command_type, builder, payload):
        return self._start(
            self._pipeline, command_type, "relation.review",
            (("PaperVersion", version.id),),
            (("PaperVersion", version.id, version.row_version),),
            {"paper_version_id": str(version.id), **payload},
            lambda plan: (builder(plan),),
        )

    def retract_relation(self, relation_id):
        with self._factory() as session:
            row = session.get(EntityRelationModel, relation_id)
            relation = RelationLifecycleRecord(
                row.id, row.relation_type, row.source_type, row.source_id,
                row.target_type, row.target_id, row.lifecycle_state,
                row.row_version)
        return self._start(
            self._pipeline, "relation.retract", "relation.review",
            (("EntityRelation", relation.id),),
            (("EntityRelation", relation.id, relation.row_version),),
            {"relation_id": str(relation.id)},
            lambda plan: (retract_relation(
                relation, plan.command_id, _now()),),
        )

    def undo(self, original_command_id):
        with self._factory() as session:
            record = next(
                (item for item in SqlUndoHistoryRepository(
                    session).list_undo_history()
                 if item.command_id == original_command_id),
                None,
            )
        if record is None:
            raise LookupError("UNDO_NOT_AVAILABLE")
        scopes = tuple(
            (change.entity_type, change.entity_id)
            for change in record.preflight.changes)
        expected = tuple(
            (change.entity_type, change.entity_id,
             json.loads(change.current_snapshot)["row_version"])
            for change in record.preflight.changes)
        pipeline = ProtectedCommandPipeline(
            _UndoDispatcher(self._dispatcher, original_command_id),
            self._runner, self._next_generation)
        return self._start(
            pipeline, "undo.compensate", "undo.execute", scopes, expected,
            {"original_command_id": str(original_command_id)},
            lambda plan: plan_compensating_undo(
                original_command_id, plan.command_id, _now(),
                record.preflight),
        )


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
        recovery_adapter = SQLiteRecoveryAdapter()
        operation_runner = ThreadedOperationRunner(
            OperationWorker.with_recovery(
                snapshot_store, parser_registry, recovery_adapter
            )
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
        paper_query = GetPapersQuery(SqlPaperReadRepository(session))
        idea_query = GetIdeasQuery(SqlIdeaReadRepository(session))
        submission_query = GetSubmissionsQuery(
            SqlSubmissionReadRepository(session)
        )
        command_dispatcher = CommandDispatcher(
            coordinator, RecoveryPointService(recovery_adapter, coordinator),
            database_path=database_path,
            recovery_root=data_directory / "recovery",
        )
        protected_pipeline = ProtectedCommandPipeline(
            command_dispatcher, operation_runner,
            coordinator.next_recovery_generation,
        )
        crud_actions = _CrudActions(
            protected_pipeline,
            coordinator.workspace_id(),
            session,
            paper_query,
            idea_query,
            submission_query,
        )
        candidate_query = GetVersionCandidates(factory)
        decision_actions = _DecisionActions(
            protected_pipeline, command_dispatcher, operation_runner,
            coordinator.next_recovery_generation, coordinator.workspace_id(),
            factory, candidate_query)
        services = ApplicationServices(
            config=state.config,
            config_store=config_store,
            change_data_directory=change_data_directory,
            get_overview=GetOverview(SqlOverviewRepository(session)),
            get_imports=GetImports(lambda: _read_import_records(factory)),
            get_monitoring=GetMonitoringDashboard(factory),
            get_version_candidates=candidate_query,
            get_papers=paper_query,
            get_ideas=idea_query,
            get_submissions=submission_query,
            crud_actions=crud_actions,
            get_safe_undo=_SafeUndoQuery(factory),
            decision_actions=decision_actions,
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
