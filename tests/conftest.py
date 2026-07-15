"""Shared pytest configuration and repository-contract fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import rfc8785
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


@pytest.fixture
def isolated_app_dirs(tmp_path, monkeypatch):
    """Keep application configuration and data out of real per-user locations."""
    config_home = tmp_path / "config-home"
    data_home = tmp_path / "data-home"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming-app-data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from research_workspace import bootstrap
    from research_workspace.application.services.initialize_application import (
        InitializeApplication,
    )
    from research_workspace.infrastructure.config.json_config_store import JsonConfigStore

    config_path = config_home / "config.json"
    default_data_path = data_home / "ResearchWorkspace"
    monkeypatch.setattr(
        bootstrap,
        "JsonConfigStore",
        lambda path=None: JsonConfigStore(path or config_path),
    )
    monkeypatch.setattr(
        bootstrap,
        "InitializeApplication",
        lambda store, **kwargs: InitializeApplication(
            store, default_data_directory=lambda: default_data_path, **kwargs
        ),
    )
    return {"config": config_home, "data": data_home, "root": tmp_path}


def validate_contract(schema_name: str, value: object) -> None:
    schema = json.loads((CONTRACTS / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def _block_id(source_sha256: str, kind: str, locator: dict[str, object], text: str) -> str:
    hash_locator = {key: value for key, value in locator.items() if key != "paragraph_id"}
    material = (
        source_sha256.encode()
        + b"\0"
        + kind.encode()
        + b"\0"
        + rfc8785.dumps(hash_locator)
        + b"\0"
        + text.replace("\r\n", "\n").encode()
    )
    return hashlib.sha256(material).hexdigest()


@pytest.fixture
def valid_task() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": "123e4567-e89b-12d3-a456-426614174000",
        "task_type": "import_document",
        "created_at": "2026-07-16T00:00:00Z",
        "requested_by": {"actor_type": "user", "actor_id": "local-user"},
        "idempotency_key": "import-1",
        "correlation_id": None,
        "target": None,
        "input_refs": [{"ref_type": "SourceDocument", "ref_id": "source-1"}],
        "options": {
            "local_only": True,
            "provider_id": None,
            "dry_run": False,
            "requires_confirmation": True,
            "max_attempts": 3,
            "extensions": {},
        },
    }


@pytest.fixture
def valid_result() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": "123e4567-e89b-12d3-a456-426614174000",
        "status": "succeeded",
        "attempt": 1,
        "started_at": "2026-07-16T00:00:00Z",
        "finished_at": "2026-07-16T00:00:01Z",
        "output_refs": [{"ref_type": "SourceDocument", "ref_id": "source-1"}],
        "result": {"imported": True},
        "error": None,
        "retry": None,
        "event_ids": ["123e4567-e89b-12d3-a456-426614174001"],
        "audit_log_ids": ["123e4567-e89b-12d3-a456-426614174002"],
    }


@pytest.fixture
def valid_event() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": "123e4567-e89b-12d3-a456-426614174001",
        "event_type": "document.imported",
        "occurred_at": "2026-07-16T00:00:00Z",
        "actor": {"actor_type": "system", "actor_id": None},
        "aggregate": {
            "type": "SourceDocument",
            "id": "123e4567-e89b-12d3-a456-426614174003",
        },
        "payload": {},
        "deduplication_key": "document-imported-1",
        "causation_id": None,
        "correlation_id": None,
    }


@pytest.fixture
def valid_document() -> dict[str, object]:
    source_hash = "a" * 64
    text = "Extracted text"
    locator: dict[str, object] = {
        "page": None,
        "slide": None,
        "paragraph_index": 0,
        "paragraph_id": None,
        "heading_path": ["Introduction", "Background"],
        "char_start": 0,
        "char_end": len(text),
        "source_offset_start": None,
        "source_offset_end": None,
        "bbox": None,
    }
    block_id = _block_id(source_hash, "paragraph", locator, text)
    locator["paragraph_id"] = block_id
    return {
        "schema_version": "1.0",
        "source": {
            "path": r"C:\research\paper.docx",
            "sha256": source_hash,
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size_bytes": 12345,
            "modified_at": "2026-07-16T00:00:00Z",
        },
        "parser": {"parser_id": "markitdown", "parser_version": "0.1.6"},
        "title": "Optional title",
        "metadata": {},
        "blocks": [{"block_id": block_id, "kind": "paragraph", "text": text, "locator": locator, "metadata": {}}],
        "warnings": [],
    }


@pytest.fixture
def clone():
    return copy.deepcopy
