"""Privacy-safe local logging configuration."""

import json
import logging
from pathlib import Path
import traceback
from collections.abc import Mapping

from research_workspace.application.ports.config_store import LOG_LEVELS


_SENSITIVE_KEYS = frozenset(
    {
        "api_key", "authorization", "extracted_text", "model_input", "model_inputs",
        "paper_body", "paper_text", "password", "prompt", "secret", "token",
    }
)
_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message", "asctime"
}


class PrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        sensitive_values: list[str] = []
        for key, value in tuple(record.__dict__.items()):
            if key.lower() in _SENSITIVE_KEYS:
                if isinstance(value, str) and value:
                    sensitive_values.append(value)
                setattr(record, key, "[REDACTED]")
            elif key not in _STANDARD_RECORD_KEYS:
                sanitized, nested_values = _sanitize_context(value)
                setattr(record, key, sanitized)
                sensitive_values.extend(nested_values)

        for value in sensitive_values:
            message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()

        if record.exc_info is not None:
            exception_type, _, tb = record.exc_info
            frames = "".join(
                f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
                for frame in traceback.extract_tb(tb)
            )
            record.msg += (
                "\nTraceback (most recent call last):\n"
                f"{frames}{exception_type.__name__}: [REDACTED]"
            )
            record.exc_info = None
            record.exc_text = None
        return True


def _sanitize_context(value):
    if isinstance(value, Mapping):
        sanitized = {}
        sensitive_values: list[str] = []
        for key, nested in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                if isinstance(nested, str) and nested:
                    sensitive_values.append(nested)
                sanitized[key] = "[REDACTED]"
            else:
                sanitized_value, found = _sanitize_context(nested)
                sanitized[key] = sanitized_value
                sensitive_values.extend(found)
        return sanitized, sensitive_values
    if isinstance(value, (list, tuple)):
        sanitized_items = []
        sensitive_values = []
        for item in value:
            sanitized, found = _sanitize_context(item)
            sanitized_items.append(sanitized)
            sensitive_values.extend(found)
        return type(value)(sanitized_items), sensitive_values
    return value, []


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
        }
        base = super().format(record)
        if context:
            base += " context=" + json.dumps(context, default=str, sort_keys=True)
        return base

def configure_logging(
    log_dir: Path,
    level: str,
    *,
    logger_name: str = "research_workspace",
) -> logging.Logger:
    if level not in LOG_LEVELS:
        raise ValueError("Unsupported logging level")
    resolved = log_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = True
    for handler in tuple(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    for active_filter in tuple(logger.filters):
        logger.removeFilter(active_filter)

    privacy_filter = PrivacyFilter()
    logger.addFilter(privacy_filter)
    handler = logging.FileHandler(resolved / "research_workspace.log", encoding="utf-8")
    handler.setLevel(level)
    handler.addFilter(privacy_filter)
    handler.setFormatter(ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return logger
