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


@pytest.fixture
def safe_source(tmp_path: Path) -> Path:
    source = tmp_path / "external" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes((b"research-workspace-source\n" * 512) + b"complete")
    return source


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
