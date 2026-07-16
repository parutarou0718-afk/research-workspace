"""Gate 1 immutable import value objects."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileStat:
    size_bytes: int
    modified_time_ns: int
    file_id_hint: str | None
    volume_serial_hint: str | None


@dataclass(frozen=True)
class StagedSource:
    source_path: Path
    staging_path: Path
    sha256: str
    size_bytes: int
    pre_stat: FileStat
    post_stat: FileStat
