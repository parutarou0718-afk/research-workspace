"""Closed Gate 1 parse identity and status vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import unicodedata
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import rfc8785

from research_workspace.domain.operations import freeze_json


DEFAULT_PARSER_CONFIG = freeze_json({
    "contract_version": "2.0",
    "ocr_enabled": False,
    "preserve_headers": False,
    "preserve_footers": False,
    "preserve_footnotes": False,
    "table_mode": "tsv-escaped-1",
    "language": None,
    "preserve_image_alt": True,
    "reading_order": "native_structural",
    "extensions": {},
})
if not isinstance(DEFAULT_PARSER_CONFIG, Mapping):  # pragma: no cover - construction invariant
    raise TypeError("default parser config must be an object")


class ParseContractError(ValueError):
    def __init__(self, error_code: str, detail: str | None = None):
        super().__init__(error_code if detail is None else f"{error_code}: {detail}")
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class ParseArtifactIdentity:
    source_snapshot_id: UUID
    parser_id: str
    parser_version: str
    config_fingerprint: str
    contract_version: str


def _normalized_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _normalized_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalized_json(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    return value


def expand_parser_config(config: Mapping[str, object]) -> dict[str, object]:
    normalized = _normalized_json(config)
    if not isinstance(normalized, dict):
        raise ParseContractError("UNSUPPORTED_CONFIGURATION")
    expanded = _normalized_json(DEFAULT_PARSER_CONFIG)
    if not isinstance(expanded, dict):  # pragma: no cover - construction invariant
        raise TypeError("default parser config must be an object")
    expanded.update(normalized)
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / "parser_config.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(expanded)
    except ValidationError as exc:
        raise ParseContractError("UNSUPPORTED_CONFIGURATION") from exc
    return expanded


def build_parse_artifact_identity(
    source_snapshot_id: UUID,
    parser_id: str,
    parser_version: str,
    config: Mapping[str, object],
    contract_version: str,
) -> ParseArtifactIdentity:
    if not parser_id.strip() or not parser_version.strip() or contract_version != "2.0":
        raise ParseContractError("UNSUPPORTED_CONFIGURATION")
    expanded = expand_parser_config(config)
    if expanded["contract_version"] != contract_version:
        raise ParseContractError("UNSUPPORTED_CONFIGURATION")
    fingerprint = hashlib.sha256(rfc8785.dumps(expanded)).hexdigest()
    return ParseArtifactIdentity(
        source_snapshot_id,
        parser_id,
        parser_version,
        fingerprint,
        contract_version,
    )


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
