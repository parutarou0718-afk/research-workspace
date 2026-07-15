"""Privacy-safe local logging configuration."""

from collections.abc import Mapping
import json
import logging
from pathlib import Path
import re
import traceback

from research_workspace.application.ports.config_store import LOG_LEVELS


_SAFE_MESSAGES = frozenset(
    {"configuration failed", "failure", "processing failed", "recorded"}
)
_SAFE_CONTEXT_KEYS = frozenset(
    {
        "attempt",
        "category",
        "component",
        "count",
        "error_code",
        "operation",
        "region",
        "retryable",
        "status",
        "technical_context",
    }
)
_SAFE_REGION_KEYS = frozenset({"name", "zone"})
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")
_STANDARD_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}


class PrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = (
            record.msg
            if isinstance(record.msg, str)
            and not record.args
            and record.msg in _SAFE_MESSAGES
            else "unexpected_error"
        )
        redacted = False
        for key, value in tuple(record.__dict__.items()):
            if key not in _STANDARD_RECORD_KEYS:
                if key not in _SAFE_CONTEXT_KEYS:
                    del record.__dict__[key]
                    redacted = True
                else:
                    sanitized, item_redacted = _sanitize_context(key, value)
                    setattr(record, key, sanitized)
                    redacted = redacted or item_redacted
        if redacted:
            record.privacy_redacted = "[REDACTED]"
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


def _sanitize_context(key: str, value):
    if key == "technical_context":
        if not isinstance(value, Mapping):
            return "[REDACTED]", True
        sanitized = {}
        redacted = False
        for nested_key, nested in value.items():
            nested_key = str(nested_key)
            if nested_key not in _SAFE_CONTEXT_KEYS:
                redacted = True
                continue
            sanitized_value, item_redacted = _sanitize_context(nested_key, nested)
            sanitized[nested_key] = sanitized_value
            redacted = redacted or item_redacted
        return sanitized, redacted
    if key == "region":
        if isinstance(value, Mapping):
            sanitized = {}
            redacted = False
            for nested_key, nested in value.items():
                nested_key = str(nested_key)
                if nested_key not in _SAFE_REGION_KEYS:
                    redacted = True
                    continue
                sanitized_value, item_redacted = _sanitize_safe_value(nested)
                sanitized[nested_key] = sanitized_value
                redacted = redacted or item_redacted
            return sanitized, redacted
    return _sanitize_safe_value(value)


def _sanitize_safe_value(value):
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        if value == value and abs(value) != float("inf"):
            return value, False
        return "[REDACTED]", True
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value, False
    if isinstance(value, (list, tuple)):
        sanitized = []
        redacted = False
        for item in value:
            sanitized_item, item_redacted = _sanitize_safe_value(item)
            sanitized.append(sanitized_item)
            redacted = redacted or item_redacted
        return sanitized, redacted
    return "[REDACTED]", True


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_")
        }
        base = super().format(record)
        if context:
            base += " context=" + json.dumps(context, sort_keys=True)
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
    logger.propagate = False
    for handler in tuple(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    for active_filter in tuple(logger.filters):
        logger.removeFilter(active_filter)

    privacy_filter = PrivacyFilter()
    handler = logging.FileHandler(resolved / "research_workspace.log", encoding="utf-8")
    handler.setLevel(level)
    handler.addFilter(privacy_filter)
    handler.setFormatter(ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return logger
