"""Content-addressed snapshot materialization without database access."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from research_workspace.infrastructure.filesystem.atomic_files import (
    PromotionState,
    promote_no_replace,
    verify_promotion_outcome,
)
from research_workspace.infrastructure.filesystem.path_safety import SourceFailure
from research_workspace.infrastructure.filesystem.stability import stream_stable_copy


@dataclass(frozen=True)
class MaterializedSnapshot:
    sha256: str
    size_bytes: int
    storage_relative_path: str
    physical_file_reused: bool


class SnapshotStore:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root

    def materialize(self, source: Path, import_item_id: UUID) -> MaterializedSnapshot:
        staging = self._workspace_root / "staging" / "imports" / f"{import_item_id}.partial"
        staged = stream_stable_copy(source, staging)
        relative = Path("sources") / "sha256" / staged.sha256[:2] / staged.sha256 / "content"
        final = self._workspace_root / relative

        if final.exists() or final.is_symlink():
            outcome = verify_promotion_outcome(staged, final)
            if outcome.state is not PromotionState.RESUME_VERIFICATION:
                raise SourceFailure("SNAPSHOT_HASH_MISMATCH")
            staging.unlink(missing_ok=True)
            return MaterializedSnapshot(staged.sha256, staged.size_bytes, relative.as_posix(), True)

        outcome = promote_no_replace(staged, final)
        if outcome.state is PromotionState.COMPLETED:
            return MaterializedSnapshot(staged.sha256, staged.size_bytes, relative.as_posix(), False)
        if outcome.state is PromotionState.RESUME_VERIFICATION:
            staging.unlink(missing_ok=True)
            return MaterializedSnapshot(staged.sha256, staged.size_bytes, relative.as_posix(), False)
        if outcome.state is PromotionState.SAFE_CLEANUP:
            staging.unlink(missing_ok=True)
        raise SourceFailure("SOURCE_UNSTABLE")
