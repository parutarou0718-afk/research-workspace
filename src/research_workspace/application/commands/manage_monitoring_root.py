"""Safe Gate 2 monitoring-root lifecycle and metadata-only baseline creation."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import UUID, uuid4

from research_workspace.application.dto.monitoring_dto import (
    BaselineObservationDTO,
    MonitoringRootRecord,
    MonitoringRootSeed,
)
from research_workspace.application.ports.repositories import MonitoringRepository
from research_workspace.application.ports.write_coordinator import WriteCoordinator
from research_workspace.domain.capabilities import PermissionContext
from research_workspace.domain.monitoring import (
    DEFAULT_MONITORING_CONFIG,
    MonitoringConfiguration,
    MonitoringRootStatus,
)
from research_workspace.infrastructure.filesystem.path_safety import (
    SourceFailure,
    normalize_path_text,
    normalized_path_hash,
    reject_reparse_chain,
)


class MonitoringRootError(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def _paths_overlap(first: str, second: str) -> bool:
    try:
        common = os.path.commonpath((first, second))
    except ValueError:
        return False
    return common in {first, second}


def resolve_monitoring_root(
    root_path: Path,
    workspace_root: Path,
    active_roots: tuple[MonitoringRootRecord, ...],
) -> Path:
    lexical = Path(os.path.abspath(root_path.expanduser()))
    normalized_lexical = normalize_path_text(lexical)
    if any(
        root.removed_at is None
        and _paths_overlap(normalized_lexical, root.normalized_path)
        for root in active_roots
    ):
        raise MonitoringRootError("MONITOR_ROOT_OVERLAP")
    try:
        reject_reparse_chain(lexical)
        final_root = lexical.resolve(strict=True)
        reject_reparse_chain(final_root)
    except SourceFailure as exc:
        raise MonitoringRootError(exc.error_code) from exc
    except OSError as exc:
        raise MonitoringRootError("MONITOR_ROOT_PATH_UNSAFE") from exc
    if not final_root.is_dir():
        raise MonitoringRootError("MONITOR_ROOT_PATH_UNSAFE")

    workspace = workspace_root.expanduser().resolve(strict=False)
    normalized_root = normalize_path_text(final_root)
    normalized_workspace = normalize_path_text(workspace)
    if _paths_overlap(normalized_root, normalized_workspace):
        raise MonitoringRootError("MONITOR_ROOT_PATH_UNSAFE")
    if any(
        root.removed_at is None
        and _paths_overlap(normalized_root, root.normalized_path)
        for root in active_roots
    ):
        raise MonitoringRootError("MONITOR_ROOT_OVERLAP")
    return final_root


def _require_scope(context: PermissionContext, root: Path) -> None:
    if "source.observe.request" not in context.capabilities:
        raise MonitoringRootError("COMMAND_PERMISSION_DENIED")
    identity = normalized_path_hash(root)
    if not any(
        scope.scope_type == "monitoring_root"
        and scope.access_mode == "list"
        and scope.recursive
        and scope.normalized_path_hash == identity
        for scope in context.path_scopes
    ):
        raise MonitoringRootError("COMMAND_PERMISSION_DENIED")


def _baseline(
    root: Path, config: MonitoringConfiguration, observed_at: datetime
) -> tuple[BaselineObservationDTO, ...]:
    observations: list[BaselineObservationDTO] = []
    excluded = set(config.excluded_names)
    allowed = set(config.allowed_extensions)
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        reject_reparse_chain(current_path)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory.casefold() not in excluded
        )
        for filename in sorted(filenames):
            if filename.casefold() in excluded or Path(filename).suffix.casefold() not in allowed:
                continue
            source = current_path / filename
            reject_reparse_chain(source)
            details = source.stat()
            normalized = normalize_path_text(source)
            observations.append(
                BaselineObservationDTO(
                    uuid4(),
                    source,
                    normalized,
                    normalized_path_hash(source),
                    filename,
                    "file",
                    details.st_size,
                    datetime.fromtimestamp(details.st_mtime_ns / 1_000_000_000, timezone.utc),
                    str(details.st_ino) if details.st_ino else None,
                    str(details.st_dev) if details.st_dev else None,
                    observed_at,
                )
            )
    return tuple(sorted(observations, key=lambda item: item.normalized_path))


class ManageMonitoringRoot:
    def __init__(
        self,
        workspace_root: Path,
        coordinator: WriteCoordinator,
        repository: MonitoringRepository,
    ) -> None:
        self._workspace_root = workspace_root
        self._coordinator = coordinator
        self._repository = repository

    def add(
        self,
        root_path: Path,
        permission_context: PermissionContext,
        config: MonitoringConfiguration = DEFAULT_MONITORING_CONFIG,
    ) -> UUID:
        root = resolve_monitoring_root(
            root_path, self._workspace_root, self._repository.list_roots()
        )
        _require_scope(permission_context, root)
        now = datetime.now(timezone.utc)
        seed = MonitoringRootSeed(
            uuid4(),
            root,
            normalize_path_text(root),
            normalized_path_hash(root),
            config.canonical_json(),
            config.fingerprint(),
            now,
        )
        return self._coordinator.register_monitoring_root(seed, _baseline(root, config, now))

    def pause(self, root_id: UUID, context: PermissionContext) -> int:
        root = self._authorized_root(root_id, context)
        return self._coordinator.change_monitoring_root_status(root_id, root.status, MonitoringRootStatus.PAUSED)

    def resume(self, root_id: UUID, context: PermissionContext) -> int:
        root = self._authorized_root(root_id, context)
        return self._coordinator.change_monitoring_root_status(root_id, root.status, MonitoringRootStatus.ACTIVE)

    def remove(self, root_id: UUID, context: PermissionContext) -> int:
        root = self._authorized_root(root_id, context)
        return self._coordinator.remove_monitoring_root(root_id, root.status)

    def _authorized_root(self, root_id: UUID, context: PermissionContext) -> MonitoringRootRecord:
        root = self._repository.get_root(root_id)
        if root is None or root.removed_at is not None:
            raise MonitoringRootError("MONITOR_ROOT_NOT_FOUND")
        _require_scope(context, root.original_path)
        return root
