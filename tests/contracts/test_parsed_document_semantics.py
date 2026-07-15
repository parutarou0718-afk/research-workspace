def validate_parsed_document_semantics(document):
    from research_workspace.application.ports import document_parser

    return document_parser.validate_parsed_document_semantics(document)


def test_valid_document_has_no_semantic_errors(valid_document):
    assert validate_parsed_document_semantics(valid_document) == ()


def test_parsed_blocks_require_contiguous_indexes(valid_document):
    valid_document["blocks"][0]["locator"]["paragraph_index"] = 2
    assert validate_parsed_document_semantics(valid_document) == (
        "blocks[0].locator.paragraph_index must equal 0",
    )


def test_block_id_must_match_normative_hash(valid_document):
    valid_document["blocks"][0]["block_id"] = "0" * 64
    assert "blocks[0].block_id is not deterministic" in validate_parsed_document_semantics(valid_document)


def test_paragraph_like_block_requires_matching_paragraph_id(valid_document):
    valid_document["blocks"][0]["locator"]["paragraph_id"] = None
    assert "blocks[0].locator.paragraph_id must equal block_id" in validate_parsed_document_semantics(valid_document)


def test_non_paragraph_block_requires_null_paragraph_id(valid_document):
    block = valid_document["blocks"][0]
    block["kind"] = "heading"
    assert "blocks[0].locator.paragraph_id must be null" in validate_parsed_document_semantics(valid_document)


def test_full_block_character_range_matches_normalized_text(valid_document):
    valid_document["blocks"][0]["locator"]["char_end"] = 1
    assert "blocks[0].locator.char range must cover normalized text" in validate_parsed_document_semantics(valid_document)


def test_source_offsets_must_be_both_null_or_both_integers(valid_document):
    valid_document["blocks"][0]["locator"]["source_offset_start"] = 0
    assert "blocks[0].locator.source offsets must both be null or integers" in validate_parsed_document_semantics(valid_document)


def test_source_offset_end_must_not_precede_start(valid_document):
    locator = valid_document["blocks"][0]["locator"]
    locator["source_offset_start"] = 4
    locator["source_offset_end"] = 3
    assert "blocks[0].locator.source_offset_end must be >= source_offset_start" in validate_parsed_document_semantics(valid_document)


def test_source_offsets_must_not_overlap(valid_document, clone):
    second = clone(valid_document["blocks"][0])
    valid_document["blocks"].append(second)
    for index, block in enumerate(valid_document["blocks"]):
        block["locator"]["paragraph_index"] = index
        block["locator"]["source_offset_start"] = index
        block["locator"]["source_offset_end"] = index + 2
    errors = validate_parsed_document_semantics(valid_document)
    assert "blocks[1].locator.source offsets overlap previous block" in errors


def test_bbox_coordinates_must_be_ordered(valid_document):
    valid_document["blocks"][0]["locator"]["bbox"] = {"left": 2, "top": 0, "right": 1, "bottom": 1, "unit": "pt", "page": 1}
    assert "blocks[0].locator.bbox coordinates must be ordered" in validate_parsed_document_semantics(valid_document)
