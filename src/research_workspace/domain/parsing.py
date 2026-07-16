"""Closed Gate 1 parse identity and status vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
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


PARSER_WARNING_CODES = frozenset(
    {
        "NO_EXTRACTABLE_TEXT",
        "OCR_REQUIRED",
        "DOCX_HEADERS_SKIPPED",
        "DOCX_FOOTERS_SKIPPED",
        "DOCX_FOOTNOTES_SKIPPED",
        "DOCX_ENDNOTES_UNSUPPORTED",
        "DOCX_TEXTBOX_UNSUPPORTED",
        "DOCX_TRACKED_CHANGES_PARTIAL",
        "DOCX_COMMENTS_UNSUPPORTED",
        "DOCX_FIELDS_FLATTENED",
        "DOCX_EQUATION_UNSUPPORTED",
        "DOCX_SMARTART_UNSUPPORTED",
        "DOCX_EMBEDDED_OBJECT_UNSUPPORTED",
        "DOCX_IMAGE_WITHOUT_ALT",
        "PPTX_READING_ORDER_HEURISTIC",
        "PPTX_NOTES_SKIPPED",
        "PPTX_CHART_TEXT_UNSUPPORTED",
        "PPTX_SMARTART_UNSUPPORTED",
        "PPTX_MEDIA_UNSUPPORTED",
        "PPTX_EMBEDDED_OBJECT_UNSUPPORTED",
        "PPTX_IMAGE_WITHOUT_ALT",
        "PPTX_GROUP_DEPTH_EXCEEDED",
    }
)

_PARAGRAPH_LIKE_KINDS = frozenset(
    {"paragraph", "list_item", "caption", "footnote", "code", "equation", "image_alt"}
)


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


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


@lru_cache(maxsize=1)
def _parsed_document_schema() -> dict[str, object]:
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / "parsed_document.schema.json"
    value = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):  # pragma: no cover - repository contract invariant
        raise TypeError("ParsedDocument schema must be an object")
    return value


def normalize_quote(text: str) -> str:
    """Apply only the normalization approved for evidence text."""

    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _frame_utf8(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big", signed=False) + value


def make_block_id(
    parse_artifact_id: UUID | str,
    block_index: int,
    kind: str,
    locator: Mapping[str, object],
    text: str,
) -> str:
    if block_index < 0:
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    canonical_locator = _plain_json(locator)
    if not isinstance(canonical_locator, dict):
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    canonical_locator.pop("paragraph_id", None)
    parts = (
        str(parse_artifact_id).encode("utf-8"),
        str(block_index).encode("utf-8"),
        kind.encode("utf-8"),
        rfc8785.dumps(canonical_locator),
        normalize_quote(text).encode("utf-8"),
    )
    return hashlib.sha256(b"".join(_frame_utf8(part) for part in parts)).hexdigest()


def semantic_output_sha256(document: Mapping[str, object]) -> str:
    semantic = _plain_json(document)
    if not isinstance(semantic, dict) or not isinstance(semantic.get("source"), dict):
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    source = semantic["source"]
    if "storage_relative_path" not in source:
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    del source["storage_relative_path"]
    return hashlib.sha256(rfc8785.dumps(semantic)).hexdigest()


def derived_file_sha256(document: Mapping[str, object]) -> str:
    plain = _plain_json(document)
    if not isinstance(plain, dict):
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    return hashlib.sha256(rfc8785.dumps(plain)).hexdigest()


def canonicalize_warnings(
    warnings: object,
) -> tuple[dict[str, object], ...]:
    if not isinstance(warnings, (tuple, list)):
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    by_identity: dict[tuple[str, int | None, bytes], dict[str, object]] = {}
    for raw_warning in warnings:
        warning = _plain_json(raw_warning)
        if not isinstance(warning, dict) or set(warning) != {
            "code",
            "block_index",
            "native_locator",
        }:
            raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
        code = warning["code"]
        block_index = warning["block_index"]
        native_locator = warning["native_locator"]
        if code not in PARSER_WARNING_CODES or (
            block_index is not None
            and (not isinstance(block_index, int) or isinstance(block_index, bool) or block_index < 0)
        ):
            raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
        if native_locator is not None and not isinstance(native_locator, dict):
            raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
        if native_locator is not None:
            document_schema = _parsed_document_schema()
            native_schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": "#/$defs/nativeLocator",
                "$defs": document_schema["$defs"],
            }
            try:
                Draft202012Validator(
                    native_schema, format_checker=FormatChecker()
                ).validate(native_locator)
            except ValidationError as exc:
                raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID") from exc
        locator_bytes = rfc8785.dumps(native_locator)
        by_identity[(code, block_index, locator_bytes)] = warning

    def sort_key(item: tuple[tuple[str, int | None, bytes], dict[str, object]]):
        (code, block_index, locator_bytes), _warning = item
        return (block_index is None, block_index if block_index is not None else 0, code, locator_bytes)

    return tuple(warning for _identity, warning in sorted(by_identity.items(), key=sort_key))


def validate_parsed_document_v2(document: Mapping[str, object]) -> None:
    plain = _plain_json(document)
    if not isinstance(plain, dict):
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID")
    schema = _parsed_document_schema()
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(plain)
    except ValidationError as exc:
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID", exc.message) from exc

    errors: list[str] = []
    blocks = plain["blocks"]
    artifact_id = plain["parse_artifact_id"]
    previous_offset_end: int | None = None
    for index, block in enumerate(blocks):
        locator = block["locator"]
        text = block["text"]
        kind = block["kind"]
        if block["block_index"] != index:
            errors.append(f"blocks[{index}].block_index must equal {index}")
        if locator["block_index"] != index:
            errors.append(f"blocks[{index}].locator.block_index must equal {index}")
        normalized_text = normalize_quote(text)
        if text != normalized_text:
            errors.append(f"blocks[{index}].text must be NFC with LF newlines")
        if locator["char_start"] != 0 or locator["char_end"] != len(normalized_text):
            errors.append(f"blocks[{index}].locator.char range must cover normalized text")
        expected_id = make_block_id(artifact_id, index, kind, locator, text)
        if block["block_id"] != expected_id:
            errors.append(f"blocks[{index}].block_id is not deterministic")
        if kind in _PARAGRAPH_LIKE_KINDS:
            if locator["paragraph_id"] != block["block_id"]:
                errors.append(f"blocks[{index}].locator.paragraph_id must equal block_id")
        elif locator["paragraph_id"] is not None:
            errors.append(f"blocks[{index}].locator.paragraph_id must be null")

        offset_start = locator["source_offset_start"]
        offset_end = locator["source_offset_end"]
        if (offset_start is None) != (offset_end is None):
            errors.append(f"blocks[{index}].locator.source offsets must both be null or integers")
        elif isinstance(offset_start, int) and isinstance(offset_end, int):
            if offset_end < offset_start:
                errors.append(f"blocks[{index}].locator.source_offset_end must be >= source_offset_start")
            if previous_offset_end is not None and offset_start < previous_offset_end:
                errors.append(f"blocks[{index}].locator.source offsets overlap previous block")
            previous_offset_end = max(previous_offset_end or 0, offset_end)

        bbox = locator["bbox"]
        if isinstance(bbox, dict) and (
            bbox["right"] < bbox["left"] or bbox["bottom"] < bbox["top"]
        ):
            errors.append(f"blocks[{index}].locator.bbox coordinates must be ordered")

    try:
        canonical_warnings = canonicalize_warnings(plain["warnings"])
    except ParseContractError as exc:
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID") from exc
    if list(canonical_warnings) != plain["warnings"]:
        errors.append("warnings must be unique and deterministically sorted")
    if any(
        warning["block_index"] is not None and warning["block_index"] >= len(blocks)
        for warning in canonical_warnings
    ):
        errors.append("warning block_index must reference an emitted block")
    if errors:
        raise ParseContractError("PARSED_DOCUMENT_CONTRACT_INVALID", "; ".join(errors))


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
