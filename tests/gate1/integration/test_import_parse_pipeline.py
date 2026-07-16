from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

from sqlalchemy import select

from research_workspace.application.services.import_orchestrator import ImportOrchestrator
from research_workspace.application.services.operation_dispatcher import ImportParsePipeline
from research_workspace.infrastructure.db.models import (
    DomainEventModel,
    ImportBatchModel,
    ImportItemModel,
    ParseArtifactModel,
    ParseAttemptModel,
    ParsedBlockModel,
    SourceDocumentModel,
    SourceSnapshotModel,
)
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.snapshots import SnapshotStore
from research_workspace.infrastructure.parsers.docx_parser import DocxParser
from research_workspace.infrastructure.parsers.pdf_parser import PdfParser
from research_workspace.infrastructure.parsers.pptx_parser import PptxParser
from research_workspace.infrastructure.workers.operation_worker import (
    OperationWorker,
    ThreadedOperationRunner,
)


def _pipeline(import_application):
    coordinator = SqlWriteCoordinator(
        import_application.factory, data_directory=import_application.workspace
    )
    snapshot_port = SnapshotStore(import_application.workspace)
    parsers = {parser.parser_id: parser for parser in (DocxParser(), PdfParser(), PptxParser())}
    runner = ThreadedOperationRunner(OperationWorker(snapshot_port, parsers))
    orchestrator = ImportOrchestrator(import_application.workspace, snapshot_port, coordinator)
    return (
        ImportParsePipeline(
            import_application.workspace,
            orchestrator,
            coordinator,
            runner,
            tuple(parsers.values()),
        ),
        runner,
    )


def _parse_enabled_request(import_application, source: Path):
    request = import_application.request((source,))
    context = replace(
        request.permission_context,
        capabilities=("source.snapshot_import.request", "document.parse.request"),
    )
    return replace(request, permission_context=context)


def test_complete_import_parse_pipeline_persists_only_on_main_thread(
    qtbot, import_application, tmp_path: Path, socket_disabled
) -> None:
    source = tmp_path / "external" / "paper.pdf"
    source.parent.mkdir()
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "pdf" / "normal_text.pdf"
    source.write_bytes(fixture.read_bytes())
    before = source.read_bytes()
    pipeline, runner = _pipeline(import_application)
    main_thread = threading.get_ident()

    handle = pipeline.start(_parse_enabled_request(import_application, source))
    qtbot.waitUntil(lambda: handle.done, timeout=10000)

    assert handle.status == "completed"
    assert handle.persistence_thread_ids
    assert set(handle.persistence_thread_ids) == {main_thread}
    assert source.read_bytes() == before
    with import_application.factory() as session:
        snapshot = session.scalar(select(SourceSnapshotModel))
        batch = session.scalar(select(ImportBatchModel))
        item = session.scalar(select(ImportItemModel))
        artifact = session.scalar(select(ParseArtifactModel))
        attempt = session.scalar(select(ParseAttemptModel))
        document = session.scalar(select(SourceDocumentModel))
        blocks = session.scalars(select(ParsedBlockModel).order_by(ParsedBlockModel.block_index)).all()
        events = session.scalars(select(DomainEventModel).order_by(DomainEventModel.created_at)).all()
        assert snapshot is not None
        assert batch.status == "completed"
        assert item.state == "imported"
        assert item.parse_status == "succeeded"
        assert item.parse_artifact_id == artifact.id
        assert artifact.status == attempt.status == "succeeded"
        assert document.block_count == len(blocks) == 2
        assert [block.text for block in blocks] == ["Page one text", "Page two text"]
        assert [event.event_type for event in events] == [
            "source.snapshot_imported",
            "document.parse_succeeded",
        ]
    assert runner.shutdown(timeout=2)


def test_pipeline_cancellation_never_reports_completed_or_parse_success(
    qtbot, import_application, tmp_path: Path
) -> None:
    source = tmp_path / "external" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"not parsed after cancellation")
    pipeline, runner = _pipeline(import_application)
    handle = pipeline.start(_parse_enabled_request(import_application, source))
    handle.cancel()

    qtbot.waitUntil(lambda: handle.done, timeout=10000)

    assert handle.status == "cancelled"
    assert handle.completed_count == 0
    with import_application.factory() as session:
        assert session.scalar(select(ImportBatchModel)).status == "cancelled"
        assert session.scalar(select(ParseArtifactModel)) is None
        assert session.scalar(
            select(DomainEventModel).where(
                DomainEventModel.event_type == "document.parse_succeeded"
            )
        ) is None
    assert runner.shutdown(timeout=2)
