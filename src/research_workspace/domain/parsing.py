"""Closed Gate 1 parse status vocabulary."""

from enum import Enum


class ParseAttemptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ParseErrorCode(str, Enum):
    PDF_PASSWORD_REQUIRED = "PDF_PASSWORD_REQUIRED"
    PDF_CORRUPT = "PDF_CORRUPT"
    PDF_TRUNCATED = "PDF_TRUNCATED"
    PDF_INVALID_STRUCTURE = "PDF_INVALID_STRUCTURE"
    PDF_UNSUPPORTED_FEATURE = "PDF_UNSUPPORTED_FEATURE"
    PDF_READ_ERROR = "PDF_READ_ERROR"
    UNSUPPORTED_CONFIGURATION = "UNSUPPORTED_CONFIGURATION"
