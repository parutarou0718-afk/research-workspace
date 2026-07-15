"""Resolve first-run configuration and next-start pending promotion."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from platformdirs import user_data_dir

from research_workspace.application.ports.config_store import AppConfig, ConfigStore
from research_workspace.application.services.change_data_directory import (
    DirectoryValidator,
    validate_data_directory,
)
from research_workspace.shared.errors import AppError
from research_workspace.shared.result import Result


@dataclass(frozen=True, slots=True)
class StartupRecovery:
    active_data_directory: Path
    failed_pending_data_directory: Path
    error: AppError


@dataclass(frozen=True, slots=True)
class InitializationState:
    config: AppConfig
    recovery: StartupRecovery | None = None


def _default_data_directory() -> Path:
    return Path(user_data_dir("ResearchWorkspace", "ResearchWorkspace"))


class InitializeApplication:
    def __init__(
        self,
        config_store: ConfigStore,
        default_data_directory: Callable[[], Path] = _default_data_directory,
        validate_directory: DirectoryValidator = validate_data_directory,
    ):
        self._config_store = config_store
        self._default_data_directory = default_data_directory
        self._validate_directory = validate_directory

    def execute(self) -> Result[InitializationState]:
        try:
            current = self._config_store.load()
        except Exception as exc:
            return Result.failure(_startup_error("CONFIG_LOAD_FAILED", "Application configuration could not be read.", exc))

        if current is None:
            default = self._default_data_directory().expanduser().resolve()
            validation = self._validate_directory(default)
            if not validation.ok:
                error = validation.error
                return Result.failure(
                    AppError(
                        error.code,
                        error.message,
                        error.retryable,
                        {**error.details, "attempted_data_directory": str(default)},
                    )
                )
            config = AppConfig("1.0", default, None, "INFO")
            save_error = self._save(config)
            return save_error or Result.success(InitializationState(config))

        if current.pending_data_directory is not None:
            pending = current.pending_data_directory
            validation = self._validate_directory(pending)
            if validation.ok:
                promoted = AppConfig(current.schema_version, pending, None, current.log_level)
                save_error = self._save(promoted)
                return save_error or Result.success(InitializationState(promoted))

            retained = AppConfig(
                current.schema_version, current.active_data_directory, None, current.log_level
            )
            save_error = self._save(retained)
            if save_error is not None:
                return save_error
            return Result.success(
                InitializationState(
                    retained,
                    StartupRecovery(current.active_data_directory, pending, validation.error),
                )
            )

        validation = self._validate_directory(current.active_data_directory)
        if not validation.ok:
            return Result.failure(validation.error)
        return Result.success(InitializationState(current))

    def _save(self, config: AppConfig) -> Result[InitializationState] | None:
        try:
            self._config_store.save(config)
        except Exception as exc:
            return Result.failure(_startup_error("CONFIG_SAVE_FAILED", "Application configuration could not be saved safely.", exc))
        return None


def _startup_error(code: str, message: str, exc: Exception) -> AppError:
    return AppError(code, message, details={"exception_type": type(exc).__name__})
