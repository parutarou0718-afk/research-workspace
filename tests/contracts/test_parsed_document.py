import pytest
from jsonschema import ValidationError

from conftest import validate_contract


def test_complete_parsed_document_is_valid(valid_document):
    validate_contract("parsed_document.schema.json", valid_document)


@pytest.mark.parametrize("field", ["schema_version", "source", "parser", "title", "metadata", "blocks", "warnings"])
def test_required_document_fields(field, valid_document):
    del valid_document[field]
    with pytest.raises(ValidationError):
        validate_contract("parsed_document.schema.json", valid_document)


@pytest.mark.parametrize("field,value", [("sha256", "A" * 64), ("size_bytes", -1), ("modified_at", "2026-07-16T09:00:00+09:00")])
def test_source_rejects_invalid_values(field, value, valid_document):
    valid_document["source"][field] = value
    with pytest.raises(ValidationError):
        validate_contract("parsed_document.schema.json", valid_document)


def test_block_rejects_invalid_kind(valid_document):
    valid_document["blocks"][0]["kind"] = "unknown"
    with pytest.raises(ValidationError):
        validate_contract("parsed_document.schema.json", valid_document)


def test_document_rejects_extra_closed_properties(valid_document):
    valid_document["blocks"][0]["locator"]["extra"] = True
    with pytest.raises(ValidationError):
        validate_contract("parsed_document.schema.json", valid_document)


def test_metadata_extension_objects_are_open(valid_document):
    valid_document["metadata"]["custom"] = {"value": 1}
    valid_document["blocks"][0]["metadata"]["custom"] = True
    validate_contract("parsed_document.schema.json", valid_document)
