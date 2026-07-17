from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from research_workspace.application.commands.manage_monitoring_root import ManageMonitoringRoot
from research_workspace.domain.capabilities import PathScope, PermissionContext
from research_workspace.infrastructure.db.models import (
    PaperVersionCandidateModel,
    PendingPathCheckModel,
    ParseArtifactModel,
    RawFileEventModel,
    SourceObservationModel,
    SourceObservationEventModel,
    SourceSnapshotModel,
    WorkspaceMetadataModel,
)
from research_workspace.infrastructure.db.repositories import SqlMonitoringRepository
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import normalized_path_hash


def _permission(root: Path, workspace_id: UUID) -> PermissionContext:
    return PermissionContext(
        "1.0",
        "user",
        "local-user",
        workspace_id,
        ("source.observe.request",),
        (),
        (
            PathScope(
                "monitoring_root",
                normalized_path_hash(root),
                UUID("43000000-0000-0000-0000-000000000001"),
                "list",
                True,
            ),
        ),
        False,
        datetime(2026, 7, 17, tzinfo=timezone.utc),
        "1.0",
        UUID("43000000-0000-0000-0000-000000000002"),
    )


def test_baseline_records_metadata_without_content_assets(
    monitoring_database, monkeypatch
) -> None:
    root = monitoring_database.workspace.parent / "external"
    (root / "nested").mkdir(parents=True)
    (root / "paper.pdf").write_bytes(b"paper-content-must-not-be-read")
    (root / "nested" / "draft.docx").write_bytes(b"docx-content-must-not-be-read")
    (root / "ignored.txt").write_text("not a supported research file", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: (_ for _ in ()).throw(AssertionError(f"baseline read content: {self}")),
    )
    with monitoring_database.factory() as read_session:
        workspace_id = read_session.scalar(select(WorkspaceMetadataModel.workspace_id))
        command = ManageMonitoringRoot(
            monitoring_database.workspace,
            SqlWriteCoordinator(monitoring_database.factory),
            SqlMonitoringRepository(read_session),
        )
        root_id = command.add(root, _permission(root, workspace_id))

    with monitoring_database.factory() as session:
        observations = session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.monitoring_root_id == root_id)
            .order_by(SourceObservationModel.normalized_path)
        ).all()
        assert [row.original_filename for row in observations] == ["draft.docx", "paper.pdf"]
        assert all(row.baseline_only for row in observations)
        assert all(row.current_snapshot_id is None for row in observations)
        assert all(row.size_bytes is not None and row.modified_at is not None for row in observations)
        events = session.scalars(
            select(SourceObservationEventModel)
            .where(SourceObservationEventModel.event_type == "baseline")
            .order_by(SourceObservationEventModel.observed_at)
        ).all()
        assert len(events) == 2
        assert {json.loads(event.facts_json)["entry_type"] for event in events} == {"file"}
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 0
        assert session.scalar(select(func.count(ParseArtifactModel.id))) == 0
        assert session.scalar(select(func.count(PaperVersionCandidateModel.id))) == 0
        assert session.scalar(select(func.count(RawFileEventModel.id))) == 0
        assert session.scalar(select(func.count(PendingPathCheckModel.id))) == 0
