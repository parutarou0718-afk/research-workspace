from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from research_workspace.application.dto.monitoring_dto import MonitoringRootSeed
from research_workspace.application.queries.get_monitoring import GetMonitoringDashboard
from research_workspace.domain.monitoring import DEFAULT_MONITORING_CONFIG
from research_workspace.infrastructure.db.write_coordinator import SqlWriteCoordinator
from research_workspace.infrastructure.filesystem.path_safety import (
    normalize_path_text,
    normalized_path_hash,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def test_monitoring_projection_covers_empty_and_persisted_root_states(
    monitoring_database,
) -> None:
    query = GetMonitoringDashboard(monitoring_database.factory)
    assert query.execute().roots == ()

    root = monitoring_database.workspace.parent / "external"
    root.mkdir()
    root_id = uuid4()
    SqlWriteCoordinator(monitoring_database.factory).register_monitoring_root(
        MonitoringRootSeed(
            root_id,
            root,
            normalize_path_text(root),
            normalized_path_hash(root),
            DEFAULT_MONITORING_CONFIG.canonical_json(),
            DEFAULT_MONITORING_CONFIG.fingerprint(),
            NOW,
        ),
        (),
    )

    dashboard = query.execute()

    assert len(dashboard.roots) == 1
    row = dashboard.roots[0]
    assert row.monitoring_root_id == root_id
    assert row.status == "active"
    assert row.waiting_count == row.failure_count == 0
    assert row.reconciliation_status is None
    assert row.meaningful_update_marker


def test_projection_is_read_only_and_does_not_add_unread_state(
    monitoring_database,
) -> None:
    before = monitoring_database.database.read_bytes()

    GetMonitoringDashboard(monitoring_database.factory).execute()

    assert monitoring_database.database.read_bytes() == before
