from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text


@dataclass(frozen=True)
class V01Database:
    path: Path
    source_rows: tuple[dict[str, object], ...]
    evidence_rows: tuple[dict[str, object], ...]
    event_rows: tuple[dict[str, object], ...]


@dataclass
class ImportApplication:
    workspace: Path
    factory: object
    command: object
    workspace_id: object

    def request(self, paths: tuple[Path, ...]):
        from datetime import datetime, timezone
        from uuid import uuid4

        from research_workspace.application.dto.import_dto import ImportRequest
        from research_workspace.domain.capabilities import PathScope, PermissionContext
        from research_workspace.infrastructure.filesystem.path_safety import normalized_path_hash

        scopes = tuple(
            PathScope("import_source", normalized_path_hash(path), uuid4(), "copy", False)
            for path in paths
        )
        return ImportRequest(
            paths,
            PermissionContext(
                "1.0",
                "user",
                "local-test-user",
                self.workspace_id,
                ("source.snapshot_import.request",),
                (),
                scopes,
                False,
                datetime.now(timezone.utc),
                "test-policy-1.0",
                uuid4(),
            ),
        )


@pytest.fixture
def import_application(tmp_path: Path) -> ImportApplication:
    from research_workspace import bootstrap
    from research_workspace.application.commands.import_documents import ImportDocumentsCommand
    from research_workspace.application.services.import_orchestrator import ImportOrchestrator
    from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory
    from research_workspace.infrastructure.db.models import WorkspaceMetadataModel
    from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
    from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore

    workspace = tmp_path / "workspace"
    bootstrap._ensure_data_layout(workspace)
    database = workspace / "research_workspace.db"
    bootstrap._run_migrations(database)
    engine = create_engine_for_path(database)
    factory = session_factory(engine)
    with factory() as session:
        workspace_id = session.query(WorkspaceMetadataModel.workspace_id).scalar()
    coordinator = SqlWriteCoordinator(factory)
    orchestrator = ImportOrchestrator(workspace, SnapshotStore(workspace), coordinator)
    application = ImportApplication(
        workspace, factory, ImportDocumentsCommand(orchestrator), workspace_id
    )
    yield application
    engine.dispose()


@pytest.fixture
def safe_source(tmp_path: Path) -> Path:
    source = tmp_path / "external" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes((b"research-workspace-source\n" * 512) + b"complete")
    return source


@pytest.fixture
def parse_database(tmp_path: Path):
    from datetime import datetime, timezone
    from uuid import uuid4

    from research_workspace import bootstrap
    from research_workspace.infrastructure.db.models import (
        BackgroundOperationModel,
        SourceSnapshotModel,
    )
    from research_workspace.infrastructure.db.session import create_engine_for_path, session_factory

    workspace = tmp_path / "workspace"
    bootstrap._ensure_data_layout(workspace)
    database = workspace / "research_workspace.db"
    bootstrap._run_migrations(database)
    engine = create_engine_for_path(database)
    factory = session_factory(engine)
    import_operation_id = uuid4()
    snapshot_id = uuid4()
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add(
            BackgroundOperationModel(
                id=import_operation_id,
                operation_type="snapshot_import",
                status="completed",
                work_plan_fingerprint="f" * 64,
                permission_context_json="{}",
                result_summary_json="{}",
                error_code=None,
                created_at=now,
                started_at=now,
                finished_at=now,
                cancel_requested_at=None,
            )
        )
        session.add(
            SourceSnapshotModel(
                id=snapshot_id,
                sha256="1" * 64,
                size_bytes=123,
                mime_type="application/pdf",
                storage_relative_path=f"sources/sha256/11/{'1' * 64}/content",
                created_at=now,
                created_by_operation_id=import_operation_id,
            )
        )
    yield workspace, factory, snapshot_id
    engine.dispose()


@pytest.fixture
def minimal_parsed_document():
    import hashlib
    from copy import deepcopy
    from uuid import UUID

    import rfc8785

    from research_workspace.application.dto.parsing_dto import ParseSuccessDTO
    from research_workspace.domain.parsing import DEFAULT_PARSER_CONFIG, build_parse_artifact_identity

    class Builder:
        def success_dto(
            self,
            workspace: Path,
            operation_id: UUID,
            artifact_id: UUID,
            attempt_id: UUID,
            snapshot_id: UUID,
            change=None,
            *,
            title: str = "Parsed title",
        ) -> ParseSuccessDTO:
            block_id = hashlib.sha256(str(artifact_id).encode("utf-8")).hexdigest()
            locator = {
                "page": 1,
                "slide": None,
                "block_index": 0,
                "paragraph_index": 0,
                "paragraph_id": block_id,
                "heading_path": [],
                "char_start": 0,
                "char_end": 4,
                "source_offset_start": None,
                "source_offset_end": None,
                "bbox": None,
                "native_locator": {"type": "pdf", "page": 1, "extraction_index": 0},
            }
            document = {
                "schema_version": "2.0",
                "parse_artifact_id": str(artifact_id),
                "source": {
                    "source_snapshot_id": str(snapshot_id),
                    "sha256": "1" * 64,
                    "mime_type": "application/pdf",
                    "size_bytes": 123,
                    "storage_relative_path": f"sources/sha256/11/{'1' * 64}/content",
                },
                "parser": {
                    "parser_id": "pypdf",
                    "parser_version": "6.14.2",
                    "config_fingerprint": build_parse_artifact_identity(
                        snapshot_id, "pypdf", "6.14.2", DEFAULT_PARSER_CONFIG, "2.0"
                    ).config_fingerprint,
                    "contract_version": "2.0",
                },
                "title": title,
                "metadata": {"language": None, "page_count": 1, "slide_count": None},
                "blocks": [
                    {
                        "block_id": block_id,
                        "block_index": 0,
                        "kind": "paragraph",
                        "text": "text",
                        "locator": locator,
                        "metadata": {},
                    }
                ],
                "warnings": [],
            }
            if change is not None:
                change(document)
            canonical = rfc8785.dumps(document)
            return ParseSuccessDTO(
                operation_id,
                artifact_id,
                attempt_id,
                deepcopy(document),
                "b" * 64,
                hashlib.sha256(canonical).hexdigest(),
                f"derived/parse/{artifact_id}/parsed_document.json",
            )

    return Builder()


@pytest.fixture
def mutate_after_first_chunk():
    def build(source: Path):
        called = False

        def mutate() -> None:
            nonlocal called
            if not called:
                called = True
                with source.open("ab") as stream:
                    stream.write(b"changed-during-copy")

        return mutate

    return build


def alembic_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    return workspace / "research_workspace.db"


def rows(database_path: Path, sql: str) -> tuple[dict[str, object], ...]:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            return tuple(dict(row) for row in connection.execute(text(sql)).mappings())
    finally:
        engine.dispose()


@pytest.fixture
def v01_database(tmp_path: Path) -> V01Database:
    database_path = tmp_path / "workspace" / "research_workspace.db"
    database_path.parent.mkdir(parents=True)
    command.upgrade(alembic_config(database_path), "0001")

    source_rows = (
        {
            "id": "10000000-0000-0000-0000-000000000001",
            "path": r"C:\\Research\\Draft One.pdf",
            "sha256": "1" * 64,
            "mime_type": "application/pdf",
            "size_bytes": 101,
            "modified_at": "2026-07-01T01:02:03Z",
            "imported_at": "2026-07-02T01:02:03Z",
            "read_only": 1,
            "missing_at": None,
        },
        {
            "id": "10000000-0000-0000-0000-000000000002",
            "path": r"D:\\Archive\\Slides.pptx",
            "sha256": "2" * 64,
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size_bytes": 202,
            "modified_at": "2026-07-03T01:02:03Z",
            "imported_at": "2026-07-04T01:02:03Z",
            "read_only": 1,
            "missing_at": "2026-07-05T01:02:03Z",
        },
    )
    evidence_rows = (
        {
            "id": "20000000-0000-0000-0000-000000000001",
            "entity_type": "SourceDocument",
            "entity_id": source_rows[0]["id"],
            "document_id": source_rows[0]["id"],
            "version_id": None,
            "section": "Intro",
            "page": 1,
            "slide": None,
            "paragraph_id": "a" * 64,
            "char_start": 0,
            "char_end": 8,
            "locator_json": '{"page":1, "note":"keep spacing"}',
            "quote_hash": "b" * 64,
            "created_at": "2026-07-06T01:02:03Z",
        },
    )
    event_rows = (
        {
            "id": "30000000-0000-0000-0000-000000000001",
            "event_type": "document.imported",
            "aggregate_type": "SourceDocument",
            "aggregate_id": source_rows[0]["id"],
            "payload_json": '{ "z": 1, "a": [3, 2, 1] }',
            "deduplication_key": "legacy-event-1",
            "causation_id": None,
            "correlation_id": "30000000-0000-0000-0000-000000000002",
            "created_at": "2026-07-07T01:02:03Z",
            "processed_at": None,
        },
    )

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            for row in source_rows:
                connection.execute(
                    text("""INSERT INTO source_documents
                    (id,path,sha256,mime_type,size_bytes,modified_at,imported_at,read_only,missing_at)
                    VALUES (:id,:path,:sha256,:mime_type,:size_bytes,:modified_at,:imported_at,:read_only,:missing_at)"""),
                    row,
                )
            for row in evidence_rows:
                connection.execute(
                    text("""INSERT INTO evidence_refs
                    (id,entity_type,entity_id,document_id,version_id,section,page,slide,paragraph_id,char_start,char_end,locator_json,quote_hash,created_at)
                    VALUES (:id,:entity_type,:entity_id,:document_id,:version_id,:section,:page,:slide,:paragraph_id,:char_start,:char_end,:locator_json,:quote_hash,:created_at)"""),
                    row,
                )
            for row in event_rows:
                connection.execute(
                    text("""INSERT INTO domain_events
                    (id,event_type,aggregate_type,aggregate_id,payload_json,deduplication_key,causation_id,correlation_id,created_at,processed_at)
                    VALUES (:id,:event_type,:aggregate_type,:aggregate_id,:payload_json,:deduplication_key,:causation_id,:correlation_id,:created_at,:processed_at)"""),
                    row,
                )
    finally:
        engine.dispose()

    return V01Database(database_path, source_rows, evidence_rows, event_rows)
