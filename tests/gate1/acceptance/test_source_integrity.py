from __future__ import annotations

import hashlib
import inspect
import re
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from research_workspace.application.services import import_orchestrator
from research_workspace.infrastructure.db.models import BackgroundOperationModel, SourceSnapshotModel
from research_workspace.infrastructure.db import repositories, write_coordinator
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure
from research_workspace.infrastructure.filesystem import snapshots


def test_success_failure_and_cancel_never_modify_original_sources(
    import_application, tmp_path: Path
) -> None:
    success = tmp_path / "success.pdf"
    cancelled = tmp_path / "cancelled.pdf"
    success.write_bytes(b"success-original")
    cancelled.write_bytes(b"cancel-original")
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (success, cancelled)
    }

    import_application.command.execute(import_application.request((success,)))
    from research_workspace.application.commands.import_documents import ImportDocumentsCommand

    cancelled_command = ImportDocumentsCommand(
        import_application.command.orchestrator, cancel_requested=lambda: True
    )
    cancelled_command.execute(import_application.request((cancelled,)))

    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (success, cancelled)
    } == before


def test_internal_path_and_unknown_partial_never_become_snapshot_facts(
    import_application
) -> None:
    internal = import_application.workspace / "staging" / "imports" / "unknown.partial"
    internal.write_bytes(b"not committed")

    result = import_application.command.execute(import_application.request((internal,)))

    assert result.item_results == ()
    assert len(result.failed_item_ids) == 1
    with import_application.factory() as session:
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 0
    assert internal.read_bytes() == b"not committed"


def test_task6_import_flow_has_no_parser_or_derived_output_authority() -> None:
    source = inspect.getsource(import_orchestrator)
    assert "DocumentParser" not in source
    assert "ParseArtifact" not in source
    assert "ParseAttempt" not in source
    assert "derived" not in source.lower()


def test_wrong_workspace_permission_is_rejected_before_staging_or_operation(
    import_application, tmp_path: Path
) -> None:
    source = tmp_path / "external.pdf"
    source.write_bytes(b"must not stage")
    request = import_application.request((source,))
    request = replace(
        request,
        permission_context=replace(request.permission_context, workspace_id=uuid4()),
    )

    with pytest.raises(SourceFailure, match="COMMAND_PERMISSION_DENIED"):
        import_application.command.execute(request)
    assert list((import_application.workspace / "staging" / "imports").iterdir()) == []
    with import_application.factory() as session:
        assert session.scalar(select(func.count(BackgroundOperationModel.id))) == 0


def test_snapshot_store_uses_only_approved_stable_error_codes() -> None:
    error_codes = set(re.findall(r'SourceFailure\("([A-Z_]+)"\)', inspect.getsource(snapshots)))
    assert error_codes <= {"SNAPSHOT_HASH_MISMATCH", "SOURCE_UNSTABLE"}


def test_task6_does_not_invent_import_error_categories() -> None:
    source = inspect.getsource(repositories) + inspect.getsource(write_coordinator)
    assert re.findall(r'"(IMPORT_[A-Z_]+)"', source) == []
