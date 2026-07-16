import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "parsed_document.schema.json"


def valid_v2_document() -> dict:
    block_id = "c" * 64
    return {
        "schema_version": "2.0",
        "parse_artifact_id": "123e4567-e89b-12d3-a456-426614174020",
        "source": {
            "source_snapshot_id": "123e4567-e89b-12d3-a456-426614174021",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "size_bytes": 12345,
            "storage_relative_path": "sources/sha256/aa/" + "a" * 64 + "/content",
        },
        "parser": {
            "parser_id": "pypdf",
            "parser_version": "6.14.2",
            "config_fingerprint": "b" * 64,
            "contract_version": "2.0",
        },
        "title": "Optional title",
        "metadata": {"language": None, "page_count": 1, "slide_count": None},
        "blocks": [
            {
                "block_id": block_id,
                "block_index": 0,
                "kind": "paragraph",
                "text": "Extracted text",
                "locator": {
                    "page": 1,
                    "slide": None,
                    "block_index": 0,
                    "paragraph_index": 0,
                    "paragraph_id": block_id,
                    "heading_path": [],
                    "char_start": 0,
                    "char_end": 14,
                    "source_offset_start": None,
                    "source_offset_end": None,
                    "bbox": None,
                    "native_locator": {"type": "pdf", "page": 1, "extraction_index": 0},
                },
                "metadata": {"style_name": None},
            }
        ],
        "warnings": [],
    }


def validate(value: object) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


@pytest.mark.parametrize(
    "native_locator",
    [
        {
            "type": "docx",
            "part": "body",
            "section_index": None,
            "part_index": 0,
            "body_item_index": 0,
            "paragraph_index": 0,
            "table_index": None,
            "row_index": None,
            "column_index": None,
            "cell_paragraph_index": None,
            "style_name": "Normal",
            "image_relationship_id": None,
            "alt_source": None,
        },
        {"type": "pdf", "page": 1, "extraction_index": 0},
        {
            "type": "pptx",
            "slide": 1,
            "shape_path": [{"shape_id": 2, "tree_index": 0}],
            "text_frame_paragraph_index": 0,
            "table_index": None,
            "row_index": None,
            "column_index": None,
            "notes": False,
            "alt_source": None,
        },
    ],
)
def test_closed_native_locator_variants(native_locator: dict) -> None:
    document = valid_v2_document()
    document["blocks"][0]["locator"]["native_locator"] = native_locator
    validate(document)


def test_paragraph_index_is_nullable_but_block_index_is_required() -> None:
    document = valid_v2_document()
    document["blocks"][0]["locator"]["paragraph_index"] = None
    validate(document)
    del document["blocks"][0]["block_index"]
    with pytest.raises(ValidationError):
        validate(document)


def test_block_metadata_is_selected_by_block_kind() -> None:
    document = valid_v2_document()
    block = document["blocks"][0]
    block["kind"] = "table"
    block["metadata"] = {
        "table_text_version": "tsv-escaped-1",
        "row_count": 1,
        "column_count": 1,
    }
    block["locator"]["paragraph_id"] = None
    validate(document)
    block["metadata"]["style_name"] = "not-table-metadata"
    with pytest.raises(ValidationError):
        validate(document)


def test_warning_registry_is_closed() -> None:
    document = valid_v2_document()
    document["warnings"] = [
        {"code": "NO_EXTRACTABLE_TEXT", "block_index": None, "native_locator": None}
    ]
    validate(document)
    document["warnings"][0]["code"] = "AD_HOC_WARNING"
    with pytest.raises(ValidationError):
        validate(document)
