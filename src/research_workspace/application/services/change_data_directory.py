"""Validate a later data-directory selection and persist it as pending."""

import os
from pathlib import Path
import tempfile
from typing import Callable

from research_workspace.application.ports.config_store import AppConfig, ConfigStore
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


DirectoryValidator = Callable[[Path], Result[Path]]


def validate_data_directory(selected: Path) -> Result[Path]:
    resolved = selected.expanduser().resolve()
    probe: Path | None = None
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".research-workspace-write-probe-", dir=resolved)
        probe = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"ok")
            stream.flush()
            os.fsync(stream.fileno())
        return Result.success(resolved)
    except (OSError, ValueError) as exc:
        return Result.failure(
            AppError(
                "CONFIG_DIRECTORY_UNWRITABLE",
                "The selected data directory cannot be created or written.",
                details={"exception_type": type(exc).__name__},
            )
        )
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)


class ChangeDataDirectory:
    def __init__(
        self,
        config_store: ConfigStore,
        validate_directory: DirectoryValidator = validate_data_directory,
    ):
        self._config_store = config_store
        self._validate_directory = validate_directory

    def execute(self, selected: Path | None) -> Result[AppConfig]:
        try:
            current = self._config_store.load()
        except Exception as exc:
            return Result.failure(_config_error("CONFIG_LOAD_FAILED", exc))
        if selected is None:
            if current is None:
                return Result.failure(
                    AppError("CONFIG_NOT_INITIALIZED", "Application configuration is not initialized.")
                )
            return Result.success(current)

        resolved = selected.expanduser().resolve()
        validation = self._validate_directory(resolved)
        if not validation.ok:
            return Result.failure(validation.error)
        updated = (
            AppConfig("1.0", resolved, None, "INFO")
            if current is None
            else AppConfig(
                current.schema_version,
                current.active_data_directory,
                resolved,
                current.log_level,
            )
        )
        try:
            self._config_store.save(updated)
        except Exception as exc:
            return Result.failure(_config_error("CONFIG_SAVE_FAILED", exc))
        return Result.success(updated)


def _config_error(code: str, exc: Exception) -> AppError:
    return AppError(
        code,
        "Application configuration could not be saved safely." if code == "CONFIG_SAVE_FAILED" else "Application configuration could not be read.",
        details={"exception_type": type(exc).__name__},
    )
