from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile

from lxml import etree

from research_workspace.application.dto.parsing_dto import ParseRequest
from research_workspace.domain.parsing import DEFAULT_PARSER_CONFIG, validate_parsed_document_v2
from research_workspace.infrastructure.parsers.pptx_parser import PptxParser


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"


def _plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _request(tmp_path: Path, name: str, config: dict[str, object] | None = None) -> ParseRequest:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
    relative_path = f"pptx/{name}"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["fixtures"] if item["relative_path"] == relative_path)
    payload = (fixture_root / relative_path).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == entry["sha256"]
    assert len(payload) == entry["size_bytes"]
    snapshot_path = tmp_path / "workspace" / "sources" / "sha256" / digest[:2] / digest / "content"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(payload)
    parser_config = dict(DEFAULT_PARSER_CONFIG)
    if config:
        parser_config.update(config)
    return ParseRequest(
        uuid5(NAMESPACE_URL, f"gate1:{relative_path}:{parser_config!r}"),
        uuid5(NAMESPACE_URL, f"gate1-snapshot:{digest}"),
        snapshot_path,
        digest,
        PPTX_MIME,
        parser_config,
    )


def test_pptx_fixture_manifest_and_zip_metadata_are_deterministic() -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    entries = [
        item for item in manifest["fixtures"] if item["relative_path"].startswith("pptx/")
    ]

    assert [entry["relative_path"] for entry in entries] == [
        "pptx/ordered_shapes.pptx",
        "pptx/nested_groups.pptx",
        "pptx/table_alt_empty.pptx",
        "pptx/unsupported_constructs.pptx",
    ]
    assert all(entry["generator_version"] == "gate1-pptx-1" for entry in entries)
    for entry in entries:
        payload = (fixture_root / entry["relative_path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert len(payload) == entry["size_bytes"]
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


def test_shape_text_follows_slide_and_xml_tree_order_not_coordinates(tmp_path: Path) -> None:
    result = PptxParser().parse(_request(tmp_path, "ordered_shapes.pptx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    validate_parsed_document_v2(document)
    assert [block["text"] for block in document["blocks"]] == [
        "Slide 1 XML first",
        "Slide 1 XML second",
        "Slide 2 XML first",
        "Slide 2 XML second",
    ]
    assert [block["locator"]["slide"] for block in document["blocks"]] == [1, 1, 2, 2]
    assert [
        block["locator"]["native_locator"]["shape_path"][0]["tree_index"]
        for block in document["blocks"]
    ] == [0, 1, 0, 1]
    assert document["metadata"]["slide_count"] == 2
    assert "PPTX_READING_ORDER_HEURISTIC" in result.warning_codes


def test_group_locator_records_every_shape_level_and_depth_is_bounded(tmp_path: Path) -> None:
    result = PptxParser().parse(_request(tmp_path, "nested_groups.pptx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    leaf = next(block for block in document["blocks"] if block["text"] == "Nested leaf")
    assert leaf["locator"]["native_locator"]["shape_path"] == [
        {"shape_id": 2, "tree_index": 0},
        {"shape_id": 5, "tree_index": 1},
        {"shape_id": 9, "tree_index": 0},
    ]
    assert "Too deep leaf" not in [block["text"] for block in document["blocks"]]
    depth_warnings = [
        warning
        for warning in document["warnings"]
        if warning["code"] == "PPTX_GROUP_DEPTH_EXCEEDED"
    ]
    assert len(depth_warnings) == 1
    assert len(depth_warnings[0]["native_locator"]["shape_path"]) == 32


def test_table_alt_and_empty_slide_have_contract_locations(tmp_path: Path) -> None:
    result = PptxParser().parse(_request(tmp_path, "table_alt_empty.pptx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    assert document["metadata"]["slide_count"] == 2
    assert [block["kind"] for block in document["blocks"]] == [
        "table",
        "image_alt",
        "image_alt",
    ]
    assert {block["locator"]["slide"] for block in document["blocks"]} == {1}
    table = document["blocks"][0]
    assert table["text"] == "back\\\\slash\ttab\\tvalue\nline\\nfeed\tcarriage\\rreturn"
    assert table["metadata"] == {
        "table_text_version": "tsv-escaped-1",
        "row_count": 2,
        "column_count": 2,
    }
    assert table["locator"]["native_locator"]["table_index"] == 0
    assert [(block["text"], block["metadata"]["alt_source"]) for block in document["blocks"][1:]] == [
        ("Figure title", "title"),
        ("Figure description", "description"),
    ]
    assert [
        block["locator"]["native_locator"]["alt_source"]
        for block in document["blocks"][1:]
    ] == ["title", "description"]


def test_unsupported_constructs_and_default_notes_are_warnings_with_zero_blocks(
    tmp_path: Path,
) -> None:
    result = PptxParser().parse(_request(tmp_path, "unsupported_constructs.pptx"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    assert document["blocks"] == []
    assert result.warning_codes == (
        "PPTX_CHART_TEXT_UNSUPPORTED",
        "PPTX_EMBEDDED_OBJECT_UNSUPPORTED",
        "PPTX_IMAGE_WITHOUT_ALT",
        "PPTX_MEDIA_UNSUPPORTED",
        "PPTX_NOTES_SKIPPED",
        "PPTX_READING_ORDER_HEURISTIC",
        "PPTX_SMARTART_UNSUPPORTED",
    )


def test_notes_are_emitted_only_when_configuration_enables_them(tmp_path: Path) -> None:
    result = PptxParser().parse(
        _request(tmp_path, "unsupported_constructs.pptx", {"preserve_footnotes": True})
    )

    assert result.error_code is None
    document = _plain(result.parsed_document)
    assert [(block["text"], block["locator"]["native_locator"]["notes"]) for block in document["blocks"]] == [
        ("Speaker notes", True)
    ]
    assert "PPTX_NOTES_SKIPPED" not in result.warning_codes


def test_pptx_parser_opens_only_declared_snapshot(tmp_path: Path, monkeypatch) -> None:
    request = _request(tmp_path, "ordered_shapes.pptx")
    opened: list[Path] = []
    from pptx import Presentation as real_presentation

    def recording_open(path):
        opened.append(Path(path))
        return real_presentation(path)

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.pptx_parser.Presentation",
        recording_open,
    )
    result = PptxParser().parse(request)

    assert result.error_code is None
    assert opened == [request.snapshot_path]


def test_pptx_invalid_package_maps_to_stable_error(tmp_path: Path) -> None:
    request = _request(tmp_path, "ordered_shapes.pptx")
    invalid = tmp_path / "not-a-package.pptx"
    invalid.write_bytes(b"not a package")

    result = PptxParser().parse(replace(request, snapshot_path=invalid))

    assert result.parsed_document is None
    assert result.warning_codes == ()
    assert result.error_code == "PPTX_INVALID_PACKAGE"


def test_pptx_same_request_has_deterministic_result(tmp_path: Path) -> None:
    request = _request(tmp_path, "ordered_shapes.pptx")

    first = _plain(PptxParser().parse(request).parsed_document)
    second = _plain(PptxParser().parse(request).parsed_document)

    assert first == second
