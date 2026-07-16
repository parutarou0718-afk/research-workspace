from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from research_workspace.application.dto.import_dto import ImportRequest
from research_workspace.application.dto.parsing_dto import ParseRequest, ParseResult
from research_workspace.domain.capabilities import PathScope, PermissionContext


WORKSPACE_ID = UUID("10000000-0000-0000-0000-000000000001")
ROOT_ID = UUID("10000000-0000-0000-0000-000000000002")
DECISION_ID = UUID("10000000-0000-0000-0000-000000000003")


def permission_context() -> PermissionContext:
    return PermissionContext(
        schema_version="1.0",
        actor_type="user",
        actor_id="local-user",
        workspace_id=WORKSPACE_ID,
        capabilities=("source.snapshot_import.request",),
        scope_refs=("selection:1",),
        path_scopes=(PathScope("import_source", "a" * 64, ROOT_ID, "read", False),),
        network_allowed=False,
        granted_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        policy_version="1.0",
        authorization_decision_id=DECISION_ID,
    )


def test_permission_context_is_frozen_and_network_is_always_disabled() -> None:
    context = permission_context()
    with pytest.raises(FrozenInstanceError):
        context.actor_id = "changed"
    with pytest.raises(ValueError, match="network_allowed"):
        PermissionContext(**{**context.__dict__, "network_allowed": True})


@pytest.mark.parametrize("actor", ["agent", "task_executor", "other"])
def test_permission_context_never_accepts_disabled_or_unknown_actor(actor: str) -> None:
    context = permission_context()
    with pytest.raises(ValueError, match="actor_type"):
        PermissionContext(**{**context.__dict__, "actor_type": actor})


def test_parse_request_deeply_freezes_nested_parser_config() -> None:
    original = {"ocr_enabled": False, "options": {"languages": ["en", "zh"]}}
    request = ParseRequest(
        parse_artifact_id=UUID("20000000-0000-0000-0000-000000000001"),
        snapshot_id=UUID("20000000-0000-0000-0000-000000000002"),
        snapshot_path=Path("sources/sha256/aa/content.pdf"),
        snapshot_sha256="b" * 64,
        mime_type="application/pdf",
        parser_config=original,
    )
    original["options"]["languages"].append("ja")

    assert tuple(request.parser_config["options"]["languages"]) == ("en", "zh")
    with pytest.raises(TypeError):
        request.parser_config["ocr_enabled"] = True
    with pytest.raises(AttributeError):
        request.parser_config["options"]["languages"].append("fr")


def test_parse_result_deeply_freezes_parsed_document() -> None:
    original = {"schema_version": "2.0", "blocks": [{"text": "original"}]}
    result = ParseResult(parsed_document=original, warning_codes=("NOTICE",), error_code=None)
    original["blocks"][0]["text"] = "mutated"
    assert result.parsed_document["blocks"][0]["text"] == "original"
    with pytest.raises(TypeError):
        result.parsed_document["blocks"][0]["text"] = "changed"


def test_import_request_copies_source_path_sequence_to_tuple() -> None:
    paths = [Path("A.docx"), Path("B.pdf")]
    request = ImportRequest(source_paths=paths, permission_context=permission_context())
    paths.append(Path("C.pptx"))
    assert request.source_paths == (Path("A.docx"), Path("B.pdf"))


def test_path_scope_rejects_unregistered_values_and_invalid_hash() -> None:
    with pytest.raises(ValueError, match="scope_type"):
        PathScope("everything", "a" * 64, ROOT_ID, "read", False)
    with pytest.raises(ValueError, match="normalized_path_hash"):
        PathScope("import_source", "not-a-hash", ROOT_ID, "read", False)
