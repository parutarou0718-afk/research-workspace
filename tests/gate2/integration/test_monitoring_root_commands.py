from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from research_workspace.application.commands.manage_monitoring_root import (
    ManageMonitoringRoot,
    MonitoringRootError,
)
from research_workspace.application.queries.get_monitoring import GetMonitoring
from research_workspace.domain.capabilities import PathScope, PermissionContext
from research_workspace.domain.monitoring import MonitoringRootStatus
from research_workspace.infrastructure.db.models import (
    MonitoringRootModel,
    SourceObservationModel,
)
from research_workspace.infrastructure.db.repositories import SqlMonitoringRepository
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import normalized_path_hash


def _context(root: Path, workspace_id: UUID) -> PermissionContext:
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
                UUID("44000000-0000-0000-0000-000000000001"),
                "list",
                True,
            ),
        ),
        False,
        datetime(2026, 7, 17, tzinfo=timezone.utc),
        "1.0",
        UUID("44000000-0000-0000-0000-000000000002"),
    )


def test_add_pause_resume_remove_preserves_root_and_observation_history(
    monitoring_database,
) -> None:
    root = monitoring_database.workspace.parent / "external"
    root.mkdir()
    (root / "paper.pdf").write_bytes(b"baseline")
    with monitoring_database.factory() as read_session:
        from research_workspace.infrastructure.db.models import WorkspaceMetadataModel

        workspace_id = read_session.scalar(select(WorkspaceMetadataModel.workspace_id))
        repository = SqlMonitoringRepository(read_session)
        command = ManageMonitoringRoot(
            monitoring_database.workspace,
            SqlWriteCoordinator(monitoring_database.factory),
            repository,
        )
        root_id = command.add(root, _context(root, workspace_id))
        assert GetMonitoring(repository).execute()[0].status is MonitoringRootStatus.ACTIVE
        command.pause(root_id, _context(root, workspace_id))
        assert GetMonitoring(repository).execute()[0].status is MonitoringRootStatus.PAUSED
        command.resume(root_id, _context(root, workspace_id))
        assert GetMonitoring(repository).execute()[0].status is MonitoringRootStatus.ACTIVE
        command.remove(root_id, _context(root, workspace_id))

    with monitoring_database.factory() as session:
        stored = session.get(MonitoringRootModel, root_id)
        assert stored.removed_at is not None
        assert stored.status == "paused"
        assert session.scalar(select(func.count(SourceObservationModel.id))) == 1


def test_duplicate_and_nested_roots_fail_without_partial_registration(
    monitoring_database,
) -> None:
    root = monitoring_database.workspace.parent / "external"
    child = root / "child"
    child.mkdir(parents=True)
    with monitoring_database.factory() as read_session:
        from research_workspace.infrastructure.db.models import WorkspaceMetadataModel

        workspace_id = read_session.scalar(select(WorkspaceMetadataModel.workspace_id))
        command = ManageMonitoringRoot(
            monitoring_database.workspace,
            SqlWriteCoordinator(monitoring_database.factory),
            SqlMonitoringRepository(read_session),
        )
        command.add(root, _context(root, workspace_id))
        with pytest.raises(MonitoringRootError, match="MONITOR_ROOT_OVERLAP"):
            command.add(child, _context(child, workspace_id))

    with monitoring_database.factory() as session:
        assert session.scalar(select(func.count(MonitoringRootModel.id))) == 1
