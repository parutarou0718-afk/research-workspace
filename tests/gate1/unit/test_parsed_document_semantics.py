from __future__ import annotations

from copy import deepcopy
import hashlib
from uuid import UUID

import pytest
import rfc8785

from research_workspace.domain.parsing import (
    PARSER_WARNING_CODES,
    ParseContractError,
    canonicalize_warnings,
    derived_file_sha256,
    make_block_id,
    normalize_quote,
    semantic_output_sha256,
    validate_parsed_document_v2,
)


ARTIFACT_ID = UUID("123e4567-e89b-12d3-a456-426614174020")


def pdf_locator(block_index: int = 0, paragraph_index: int | None = 0) -> dict:
    return {
        "page": 1,
        "slide": None,
        "block_index": block_index,
        "paragraph_index": paragraph_index,
        "paragraph_id": None,
        "heading_path": [],
        "char_start": 0,
        "char_end": 4,
        "source_offset_start": None,
        "source_offset_end": None,
        "bbox": None,
        "native_locator": {"type": "pdf", "page": 1, "extraction_index": block_index},
    }


def valid_semantic_document(storage_path: str = "derived/original") -> dict:
    locator = pdf_locator()
    block_id = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, "text")
    locator["paragraph_id"] = block_id
    return {
        "schema_version": "2.0",
        "parse_artifact_id": str(ARTIFACT_ID),
        "source": {
            "source_snapshot_id": "123e4567-e89b-12d3-a456-426614174021",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "size_bytes": 4,
            "storage_relative_path": storage_path,
        },
        "parser": {
            "parser_id": "pypdf",
            "parser_version": "6.14.2",
            "config_fingerprint": "b" * 64,
            "contract_version": "2.0",
        },
        "title": None,
        "metadata": {"language": None, "page_count": 1, "slide_count": None},
        "blocks": [
            {
                "block_id": block_id,
                "block_index": 0,
                "kind": "paragraph",
                "text": "text",
                "locator": locator,
                "metadata": {},
            }
        ],
        "warnings": [],
    }


def _framed_sha256(parts: list[bytes]) -> str:
    material = b"".join(len(part).to_bytes(8, "big") + part for part in parts)
    return hashlib.sha256(material).hexdigest()


def test_block_id_uses_length_prefixed_artifact_index_kind_locator_and_text() -> None:
    locator = pdf_locator(3, None)
    locator["paragraph_id"] = "f" * 64
    canonical_locator = deepcopy(locator)
    canonical_locator.pop("paragraph_id")
    expected = _framed_sha256(
        [
            str(ARTIFACT_ID).encode("utf-8"),
            b"3",
            b"paragraph",
            rfc8785.dumps(canonical_locator),
            "a\nb".encode("utf-8"),
        ]
    )

    assert make_block_id(ARTIFACT_ID, 3, "paragraph", locator, "a\r\nb") == expected
    assert make_block_id(ARTIFACT_ID, 3, "paragraph", locator, "a\rb") == expected
    assert make_block_id(ARTIFACT_ID, 3, "paragraph", locator, "a\nb") == expected


def test_block_identity_normalizes_only_nfc_and_newlines() -> None:
    locator = pdf_locator()
    composed = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, " é\n ")
    decomposed = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, " e\u0301\r ")
    trimmed = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, "é\n")
    folded = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, " é \n ")
    assert composed == decomposed
    assert composed != trimmed
    assert composed != folded


def test_storage_path_is_the_only_field_excluded_from_semantic_hash() -> None:
    first = valid_semantic_document("derived/one")
    second = valid_semantic_document("derived/two")
    assert semantic_output_sha256(first) == semantic_output_sha256(second)
    assert derived_file_sha256(first) != derived_file_sha256(second)

    changed = deepcopy(first)
    changed["source"]["mime_type"] = "application/octet-stream"
    assert semantic_output_sha256(changed) != semantic_output_sha256(first)


def test_derived_hash_is_exact_rfc8785_canonical_file_bytes() -> None:
    document = valid_semantic_document()
    assert derived_file_sha256(document) == hashlib.sha256(rfc8785.dumps(document)).hexdigest()


def test_quote_normalization_preserves_outer_and_repeated_whitespace() -> None:
    assert normalize_quote("  e\u0301\r\n x  \r") == "  é\n x  \n"
    assert normalize_quote(" a  b ") == " a  b "


def test_semantic_validator_accepts_nullable_native_paragraph_index() -> None:
    document = valid_semantic_document()
    document["blocks"][0]["locator"]["paragraph_index"] = None
    locator = document["blocks"][0]["locator"]
    block_id = make_block_id(ARTIFACT_ID, 0, "paragraph", locator, "text")
    document["blocks"][0]["block_id"] = block_id
    locator["paragraph_id"] = block_id
    validate_parsed_document_v2(document)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document["blocks"][0].update(block_index=1),
        lambda document: document["blocks"][0]["locator"].update(block_index=1),
        lambda document: document["blocks"][0]["locator"].update(char_start=1),
        lambda document: document["blocks"][0]["locator"].update(char_end=3),
        lambda document: document["blocks"][0].update(text="te\rxt"),
        lambda document: document["blocks"][0]["locator"]["native_locator"].update(extra=True),
    ],
)
def test_semantic_validator_rejects_index_range_normalization_and_locator_drift(mutate) -> None:
    document = valid_semantic_document()
    mutate(document)
    with pytest.raises(ParseContractError, match="PARSED_DOCUMENT_CONTRACT_INVALID"):
        validate_parsed_document_v2(document)


def test_paragraph_id_derivation_depends_on_block_kind() -> None:
    paragraph = valid_semantic_document()
    validate_parsed_document_v2(paragraph)

    heading = valid_semantic_document()
    block = heading["blocks"][0]
    block["kind"] = "heading"
    block["locator"]["paragraph_id"] = None
    block["block_id"] = make_block_id(ARTIFACT_ID, 0, "heading", block["locator"], "text")
    validate_parsed_document_v2(heading)

    heading["blocks"][0]["locator"]["paragraph_id"] = heading["blocks"][0]["block_id"]
    with pytest.raises(ParseContractError, match="PARSED_DOCUMENT_CONTRACT_INVALID"):
        validate_parsed_document_v2(heading)


def test_warning_registry_is_closed_deduplicated_and_sorted() -> None:
    assert "NO_EXTRACTABLE_TEXT" in PARSER_WARNING_CODES
    warnings = [
        {"code": "OCR_REQUIRED", "block_index": None, "native_locator": None},
        {
            "code": "PPTX_MEDIA_UNSUPPORTED",
            "block_index": 2,
            "native_locator": {
                "type": "pptx",
                "slide": 1,
                "shape_path": [{"shape_id": 3, "tree_index": 0}],
                "text_frame_paragraph_index": None,
                "table_index": None,
                "row_index": None,
                "column_index": None,
                "notes": False,
                "alt_source": None,
            },
        },
        {"code": "NO_EXTRACTABLE_TEXT", "block_index": None, "native_locator": None},
        {"code": "OCR_REQUIRED", "block_index": None, "native_locator": None},
    ]
    canonical = canonicalize_warnings(warnings)
    assert [warning["code"] for warning in canonical] == [
        "PPTX_MEDIA_UNSUPPORTED",
        "NO_EXTRACTABLE_TEXT",
        "OCR_REQUIRED",
    ]
    assert len(canonical) == 3

    with pytest.raises(ParseContractError, match="PARSED_DOCUMENT_CONTRACT_INVALID"):
        canonicalize_warnings(
            [{"code": "AD_HOC", "block_index": None, "native_locator": None}]
        )
    with pytest.raises(ParseContractError, match="PARSED_DOCUMENT_CONTRACT_INVALID"):
        canonicalize_warnings(
            [
                {
                    "code": "NO_EXTRACTABLE_TEXT",
                    "block_index": 0,
                    "native_locator": {"type": "pdf", "slide": 1},
                }
            ]
        )


def test_validator_rejects_warning_duplicates_or_unstable_order() -> None:
    document = valid_semantic_document()
    document["warnings"] = [
        {"code": "OCR_REQUIRED", "block_index": None, "native_locator": None},
        {"code": "NO_EXTRACTABLE_TEXT", "block_index": None, "native_locator": None},
        {"code": "OCR_REQUIRED", "block_index": None, "native_locator": None},
    ]
    with pytest.raises(ParseContractError, match="PARSED_DOCUMENT_CONTRACT_INVALID"):
        validate_parsed_document_v2(document)
