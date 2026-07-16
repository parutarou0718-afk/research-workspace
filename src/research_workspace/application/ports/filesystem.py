"""Bounded filesystem protocol; implementations begin in Task 5."""

from pathlib import Path
from typing import Protocol

from research_workspace.domain.capabilities import PathScope
from research_workspace.domain.import_model import StagedSource


class FilesystemPort(Protocol):
    def validate_source(self, source: Path, allowed_scope: PathScope) -> None: ...

    def stage_stable_copy(self, source: Path, staging_dir: Path) -> StagedSource: ...

    def promote_snapshot(self, staged: StagedSource, sources_root: Path) -> Path: ...
