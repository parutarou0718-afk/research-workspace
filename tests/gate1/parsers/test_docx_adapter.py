from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from research_workspace.domain.parsing import validate_parsed_document_v2
from research_workspace.infrastructure.parsers.docx_parser import DocxParser


RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"


def _plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def test_docx_fixture_manifest_and_zip_metadata_are_deterministic() -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0"
    assert [entry["relative_path"] for entry in manifest["fixtures"]] == [
        "docx/body_order.docx",
        "docx/table_escapes.docx",
        "docx/image_alt.docx",
        "docx/unsupported_constructs.docx",
    ]
    for entry in manifest["fixtures"]:
        with ZipFile(fixture_root / entry["relative_path"]) as archive:
            assert archive.namelist() == sorted(archive.namelist())
            assert {item.date_time for item in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
            for name in archive.namelist():
                if not name.endswith(".rels"):
                    continue
                relationships = etree.fromstring(archive.read(name))
                assert all(
                    item.get("TargetMode") != "External"
                    for item in relationships.findall(
                        f"{{{RELATIONSHIPS_NAMESPACE}}}Relationship"
                    )
                )


def test_docx_body_paragraphs_and_tables_follow_xml_child_order(snapshot_request) -> None:
    result = DocxParser().parse(snapshot_request("body_order.docx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    validate_parsed_document_v2(document)
    assert [block["kind"] for block in document["blocks"]] == [
        "heading",
        "paragraph",
        "table",
        "paragraph",
    ]
    assert [block["text"] for block in document["blocks"]] == [
        "Methods",
        "P1",
        "A\tB\nC\tD",
        "P2",
    ]
    assert [block["block_index"] for block in document["blocks"]] == [0, 1, 2, 3]
    assert [block["locator"]["heading_path"] for block in document["blocks"]] == [
        ["Methods"],
        ["Methods"],
        ["Methods"],
        ["Methods"],
    ]
    assert [
        block["locator"]["native_locator"]["body_item_index"]
        for block in document["blocks"]
    ] == [0, 1, 2, 3]
    assert [
        block["locator"]["native_locator"]["paragraph_index"]
        for block in document["blocks"]
    ] == [0, 1, None, 2]
    assert document["blocks"][2]["locator"]["native_locator"]["table_index"] == 0


def test_docx_table_is_emitted_once_with_reversible_escape_text(snapshot_request) -> None:
    result = DocxParser().parse(snapshot_request("table_escapes.docx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    assert len(document["blocks"]) == 1
    block = document["blocks"][0]
    assert block["kind"] == "table"
    assert block["text"] == "back\\\\slash\ttab\\tvalue\nline\\nfeed\tcarriage\\rreturn"
    assert block["metadata"] == {
        "table_text_version": "tsv-escaped-1",
        "row_count": 2,
        "column_count": 2,
    }
    assert "back\\slash" not in [
        candidate["text"] for candidate in document["blocks"] if candidate["kind"] == "paragraph"
    ]


def test_docx_explicit_image_title_and_description_keep_relationship_location(
    snapshot_request,
) -> None:
    result = DocxParser().parse(snapshot_request("image_alt.docx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    assert [(block["text"], block["metadata"]["alt_source"]) for block in document["blocks"]] == [
        ("Figure title", "title"),
        ("Figure description", "description"),
    ]
    native_locators = [block["locator"]["native_locator"] for block in document["blocks"]]
    assert native_locators[0]["image_relationship_id"]
    assert native_locators[0]["image_relationship_id"] == native_locators[1]["image_relationship_id"]
    assert [locator["alt_source"] for locator in native_locators] == ["title", "description"]
    assert result.warning_codes == ()


def test_docx_unsupported_and_configured_exclusions_use_closed_sorted_warnings(
    snapshot_request,
) -> None:
    result = DocxParser().parse(snapshot_request("unsupported_constructs.docx"))

    assert result.error_code is None
    expected = (
        "DOCX_COMMENTS_UNSUPPORTED",
        "DOCX_EMBEDDED_OBJECT_UNSUPPORTED",
        "DOCX_ENDNOTES_UNSUPPORTED",
        "DOCX_EQUATION_UNSUPPORTED",
        "DOCX_FIELDS_FLATTENED",
        "DOCX_FOOTERS_SKIPPED",
        "DOCX_FOOTNOTES_SKIPPED",
        "DOCX_HEADERS_SKIPPED",
        "DOCX_SMARTART_UNSUPPORTED",
        "DOCX_TEXTBOX_UNSUPPORTED",
        "DOCX_TRACKED_CHANGES_PARTIAL",
    )
    assert result.warning_codes == expected
    document = _plain(result.parsed_document)
    assert tuple(warning["code"] for warning in document["warnings"]) == expected
    assert all(warning["code"] in expected for warning in document["warnings"])


def test_docx_enabled_headers_and_footers_follow_section_part_order(snapshot_request) -> None:
    result = DocxParser().parse(
        snapshot_request(
            "unsupported_constructs.docx",
            {"preserve_headers": True, "preserve_footers": True},
        )
    )

    assert result.error_code is None
    document = _plain(result.parsed_document)
    selected = [
        (
            block["kind"],
            block["text"],
            block["locator"]["native_locator"]["section_index"],
            block["locator"]["native_locator"]["part_index"],
        )
        for block in document["blocks"]
        if block["kind"] in {"header", "footer"}
    ]
    assert selected == [
        ("header", "Excluded header", 0, 0),
        ("footer", "Excluded footer", 0, 0),
    ]
    assert "DOCX_HEADERS_SKIPPED" not in result.warning_codes
    assert "DOCX_FOOTERS_SKIPPED" not in result.warning_codes


def test_unsupported_footnote_configuration_is_rejected_before_opening_snapshot(
    snapshot_request, monkeypatch
) -> None:
    opened = False

    def forbidden_open(_path):
        nonlocal opened
        opened = True
        raise AssertionError("DOCX package must not be opened")

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.docx_parser.Document", forbidden_open
    )
    result = DocxParser().parse(
        snapshot_request("body_order.docx", {"preserve_footnotes": True})
    )

    assert result.error_code == "UNSUPPORTED_CONFIGURATION"
    assert result.parsed_document is None
    assert opened is False


def test_docx_parser_opens_only_the_declared_snapshot(snapshot_request, monkeypatch) -> None:
    request = snapshot_request("body_order.docx")
    opened: list[Path] = []
    from docx import Document as real_document

    def recording_open(path):
        opened.append(Path(path))
        return real_document(path)

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.docx_parser.Document", recording_open
    )
    result = DocxParser().parse(request)

    assert result.error_code is None
    assert opened == [request.snapshot_path]


def test_docx_invalid_package_maps_to_stable_product_error(snapshot_request, tmp_path: Path) -> None:
    request = snapshot_request("body_order.docx")
    invalid = tmp_path / "not-a-package.docx"
    invalid.write_bytes(b"not a zip package")

    result = DocxParser().parse(replace(request, snapshot_path=invalid))

    assert result.parsed_document is None
    assert result.warning_codes == ()
    assert result.error_code == "DOCX_INVALID_PACKAGE"


def test_docx_same_request_has_byte_equivalent_semantic_result(snapshot_request) -> None:
    request = snapshot_request("body_order.docx")

    first = _plain(DocxParser().parse(request).parsed_document)
    second = _plain(DocxParser().parse(request).parsed_document)

    assert first == second
