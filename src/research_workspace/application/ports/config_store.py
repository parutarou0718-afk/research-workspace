"""Configuration-store port boundary."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


@dataclass(frozen=True, slots=True)
class AppConfig:
    schema_version: str
    active_data_directory: Path
    pending_data_directory: Path | None
    log_level: str

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("Unsupported configuration schema version")
        if self.log_level not in LOG_LEVELS:
            raise ValueError("Unsupported logging level")
        active = self.active_data_directory.expanduser().resolve()
        pending = (
            self.pending_data_directory.expanduser().resolve()
            if self.pending_data_directory is not None
            else None
        )
        object.__setattr__(self, "active_data_directory", active)
        object.__setattr__(self, "pending_data_directory", pending)


class ConfigStore(Protocol):
    def load(self) -> AppConfig | None: ...

    def save(self, config: AppConfig) -> None: ...
