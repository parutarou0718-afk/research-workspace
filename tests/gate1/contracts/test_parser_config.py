import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "parser_config.schema.json"
VALID_CONFIG = {
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
}


def validate(value: object) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def test_default_expanded_parser_config_is_valid() -> None:
    validate(VALID_CONFIG)


@pytest.mark.parametrize(
    "change",
    [
        {"ocr_enabled": True},
        {"worker_concurrency": 4},
        {"table_mode": "html"},
    ],
)
def test_parser_config_rejects_unsupported_or_operational_fields(change) -> None:
    with pytest.raises(ValidationError):
        validate({**VALID_CONFIG, **change})


def test_parser_extensions_are_closed_and_adapter_specific() -> None:
    with pytest.raises(ValidationError):
        validate({**VALID_CONFIG, "extensions": {"arbitrary": True}})
