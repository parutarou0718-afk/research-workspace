"""Atomic UTF-8 JSON configuration storage."""

import json
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_dir

from research_workspace.application.ports.config_store import AppConfig


CONFIG_FIELDS = frozenset(
    {"schema_version", "active_data_directory", "pending_data_directory", "log_level"}
)


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration member: {key}")
        result[key] = value
    return result


def default_config_path() -> Path:
    return Path(user_config_dir("ResearchWorkspace", "ResearchWorkspace")) / "config.json"


class JsonConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = (path or default_config_path()).expanduser().resolve()

    def load(self) -> AppConfig | None:
        if not self.path.exists():
            return None
        payload = json.loads(
            self.path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object
        )
        if not isinstance(payload, dict) or set(payload) != CONFIG_FIELDS:
            raise ValueError("Configuration must contain exactly the v0.1 fields")
        if not all(isinstance(payload[key], str) for key in ("schema_version", "active_data_directory", "log_level")):
            raise ValueError("Configuration contains an invalid field type")
        pending = payload["pending_data_directory"]
        if pending is not None and not isinstance(pending, str):
            raise ValueError("pending_data_directory must be a string or null")
        return AppConfig(
            schema_version=payload["schema_version"],
            active_data_directory=Path(payload["active_data_directory"]),
            pending_data_directory=Path(pending) if pending is not None else None,
            log_level=payload["log_level"],
        )

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": config.schema_version,
            "active_data_directory": str(config.active_data_directory),
            "pending_data_directory": (
                str(config.pending_data_directory)
                if config.pending_data_directory is not None
                else None
            ),
            "log_level": config.log_level,
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
