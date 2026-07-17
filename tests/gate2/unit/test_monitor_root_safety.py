from datetime import datetime, timezone
from pathlib import Path
import unicodedata
from uuid import UUID

import pytest

from research_workspace.application.commands.manage_monitoring_root import (
    MonitoringRootError,
    resolve_monitoring_root,
)
from research_workspace.application.dto.monitoring_dto import MonitoringRootRecord
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    MonitoringConfiguration,
    MonitoringRootStatus,
)
from research_workspace.infrastructure.filesystem import path_safety
from research_workspace.infrastructure.filesystem.path_safety import normalize_path_text


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _record(path: Path) -> MonitoringRootRecord:
    return MonitoringRootRecord(
        UUID("42000000-0000-0000-0000-000000000001"),
        path,
        normalize_path_text(path),
        "a" * 64,
        MonitoringRootStatus.ACTIVE,
        "b" * 64,
        0,
        NOW,
        NOW,
        None,
    )


@pytest.mark.parametrize(
    "internal",
    (
        "",
        "research_workspace.db",
        "sources",
        "derived",
        "staging",
        "recovery",
        "exports",
        "backups",
    ),
)
def test_workspace_and_internal_paths_cannot_be_monitoring_roots(
    tmp_path: Path, internal: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / internal if internal else workspace
    if candidate.suffix:
        candidate.write_bytes(b"database")
    else:
        candidate.mkdir(exist_ok=True)
    with pytest.raises(MonitoringRootError, match="MONITOR_ROOT_PATH_UNSAFE"):
        resolve_monitoring_root(candidate, workspace, ())


def test_reparse_or_symlink_root_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        link.mkdir()
        monkeypatch.setattr(path_safety, "_has_reparse_attribute", lambda path: path == link)
    with pytest.raises(MonitoringRootError, match="SOURCE_REPARSE_POINT"):
        resolve_monitoring_root(link, tmp_path / "workspace", ())


def test_equivalent_and_overlapping_active_roots_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "Résumé"
    child = root / "Papers"
    child.mkdir(parents=True)
    equivalent = Path(unicodedata.normalize("NFD", str(root)).upper())

    with pytest.raises(MonitoringRootError, match="MONITOR_ROOT_OVERLAP"):
        resolve_monitoring_root(equivalent, tmp_path / "workspace", (_record(root),))
    with pytest.raises(MonitoringRootError, match="MONITOR_ROOT_OVERLAP"):
        resolve_monitoring_root(child, tmp_path / "workspace", (_record(root),))
    with pytest.raises(MonitoringRootError, match="MONITOR_ROOT_OVERLAP"):
        resolve_monitoring_root(root, tmp_path / "workspace", (_record(child),))


def test_semantic_fingerprint_excludes_runtime_and_ui_scheduling() -> None:
    assert DEFAULT_MONITORING_CONFIG == MonitoringConfiguration()
    semantic = DEFAULT_MONITORING_CONFIG.semantic_payload()
    assert set(semantic) == {
        "quiet_window_seconds",
        "stable_observations",
        "max_stability_attempts",
        "backoff_seconds",
        "allowed_extensions",
        "excluded_names",
        "candidate_window",
    }
    assert not {"worker_count", "ui_refresh_rate", "batch_size"} & set(semantic)
    assert DEFAULT_MONITORING_CONFIG.fingerprint() == MonitoringConfiguration().fingerprint()
