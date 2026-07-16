"""Deterministic DOCX adapter over one declared immutable snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import version
import re
import unicodedata
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError, fromstring

from research_workspace.application.dto.parsing_dto import ParseRequest, ParseResult
from research_workspace.domain.parsing import (
    PARSER_WARNING_CODES,
    ParseContractError,
    build_parse_artifact_identity,
    canonicalize_warnings,
    expand_parser_config,
    make_block_id,
    normalize_quote,
    validate_parsed_document_v2,
)
from research_workspace.infrastructure.parsers.table_text import (
    TABLE_TEXT_VERSION,
    escape_table_tsv,
)


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_PARAGRAPH_KINDS = frozenset(
    {"paragraph", "list_item", "caption", "footnote", "code", "equation", "image_alt"}
)
_HEADING_STYLE = re.compile(r"^Heading\s+([1-9][0-9]*)$", re.IGNORECASE)


def _native_locator(
    *,
    part: str = "body",
    section_index: int | None = None,
    part_index: int = 0,
    body_item_index: int | None = None,
    paragraph_index: int | None = None,
    table_index: int | None = None,
    style_name: str | None = None,
    image_relationship_id: str | None = None,
    alt_source: str | None = None,
) -> dict[str, object]:
    return {
        "type": "docx",
        "part": part,
        "section_index": section_index,
        "part_index": part_index,
        "body_item_index": body_item_index,
        "paragraph_index": paragraph_index,
        "table_index": table_index,
        "row_index": None,
        "column_index": None,
        "cell_paragraph_index": None,
        "style_name": style_name,
        "image_relationship_id": image_relationship_id,
        "alt_source": alt_source,
    }


def _warning(code: str, native_locator: Mapping[str, object] | None = None) -> dict[str, object]:
    if code not in PARSER_WARNING_CODES:  # pragma: no cover - adapter registry invariant
        raise ValueError("warning is not registered")
    return {
        "code": code,
        "block_index": None,
        "native_locator": dict(native_locator) if native_locator is not None else None,
    }


class _DocumentBuilder:
    def __init__(self, artifact_id: object) -> None:
        self.artifact_id = artifact_id
        self.blocks: list[dict[str, object]] = []

    def add(
        self,
        kind: str,
        text: str,
        heading_path: list[str],
        native_locator: Mapping[str, object],
        metadata: Mapping[str, object],
        *,
        paragraph_index: int | None,
    ) -> None:
        normalized = normalize_quote(text)
        if not normalized:
            return
        block_index = len(self.blocks)
        locator: dict[str, object] = {
            "page": None,
            "slide": None,
            "block_index": block_index,
            "paragraph_index": paragraph_index,
            "paragraph_id": None,
            "heading_path": list(heading_path),
            "char_start": 0,
            "char_end": len(normalized),
            "source_offset_start": None,
            "source_offset_end": None,
            "bbox": None,
            "native_locator": dict(native_locator),
        }
        block_id = make_block_id(self.artifact_id, block_index, kind, locator, normalized)
        if kind in _PARAGRAPH_KINDS:
            locator["paragraph_id"] = block_id
        self.blocks.append(
            {
                "block_id": block_id,
                "block_index": block_index,
                "kind": kind,
                "text": normalized,
                "locator": locator,
                "metadata": dict(metadata),
            }
        )


class DocxParser:
    """Parse the declared DOCX snapshot without resolving external resources."""

    parser_id = "python-docx"
    parser_version = version("python-docx")
    supported_mime_types = frozenset({_DOCX_MIME})

    def parse(self, request: ParseRequest) -> ParseResult:
        try:
            config = expand_parser_config(request.parser_config)
        except ParseContractError:
            return ParseResult(None, (), "UNSUPPORTED_CONFIGURATION")
        if (
            request.mime_type not in self.supported_mime_types
            or config["ocr_enabled"] is not False
            or config["preserve_footnotes"] is not False
        ):
            return ParseResult(None, (), "UNSUPPORTED_CONFIGURATION")

        try:
            package_facts = self._inspect_package(request.snapshot_path)
            document = Document(request.snapshot_path)
        except (BadZipFile, PackageNotFoundError, FileNotFoundError, PermissionError):
            return ParseResult(None, (), "DOCX_INVALID_PACKAGE")
        except (KeyError, ValueError, XMLSyntaxError, OSError):
            return ParseResult(None, (), "DOCX_CORRUPT")

        identity = build_parse_artifact_identity(
            request.snapshot_id,
            self.parser_id,
            self.parser_version,
            config,
            "2.0",
        )
        builder = _DocumentBuilder(request.parse_artifact_id)
        warnings: list[dict[str, object]] = []
        heading_path: list[str] = []
        paragraph_index = 0
        table_index = 0

        for body_item_index, child in enumerate(document.element.body.iterchildren()):
            if child.tag == f"{{{_W}}}p":
                paragraph = Paragraph(child, document)
                style_name = paragraph.style.name if paragraph.style is not None else None
                match = _HEADING_STYLE.match(style_name or "")
                kind = "paragraph"
                if match is not None:
                    kind = "heading"
                    level = int(match.group(1))
                    heading_path = heading_path[: level - 1]
                    while len(heading_path) < level - 1:
                        heading_path.append("Untitled")
                    heading_text = normalize_quote(paragraph.text)
                    if heading_text:
                        heading_path.append(heading_text)
                elif child.find(f".//{{{_W}}}numPr") is not None:
                    kind = "list_item"
                native = _native_locator(
                    body_item_index=body_item_index,
                    paragraph_index=paragraph_index,
                    style_name=style_name,
                )
                builder.add(
                    kind,
                    paragraph.text,
                    heading_path,
                    native,
                    {"style_name": style_name},
                    paragraph_index=paragraph_index,
                )
                self._emit_image_alt(
                    child,
                    builder,
                    warnings,
                    heading_path,
                    native,
                    paragraph_index,
                    bool(config["preserve_image_alt"]),
                )
                paragraph_index += 1
            elif child.tag == f"{{{_W}}}tbl":
                table = Table(child, document)
                rows = [
                    [unicodedata.normalize("NFC", cell.text) for cell in row.cells]
                    for row in table.rows
                ]
                text = escape_table_tsv(rows)
                builder.add(
                    "table",
                    text,
                    heading_path,
                    _native_locator(body_item_index=body_item_index, table_index=table_index),
                    {
                        "table_text_version": TABLE_TEXT_VERSION,
                        "row_count": len(rows),
                        "column_count": max((len(row) for row in rows), default=0),
                    },
                    paragraph_index=None,
                )
                table_index += 1

        self._append_package_warnings(package_facts, warnings, config)
        self._emit_headers_and_footers(document, builder, warnings, config)
        canonical_warnings = canonicalize_warnings(warnings)
        keywords = []
        for raw_keyword in (document.core_properties.keywords or "").split(","):
            keyword = raw_keyword.strip()
            if keyword and keyword not in keywords:
                keywords.append(keyword)
        parsed_document = {
            "schema_version": "2.0",
            "parse_artifact_id": str(request.parse_artifact_id),
            "source": {
                "source_snapshot_id": str(request.snapshot_id),
                "sha256": request.snapshot_sha256,
                "mime_type": request.mime_type,
                "size_bytes": request.snapshot_path.stat().st_size,
                "storage_relative_path": (
                    f"sources/sha256/{request.snapshot_sha256[:2]}/"
                    f"{request.snapshot_sha256}/content"
                ),
            },
            "parser": {
                "parser_id": self.parser_id,
                "parser_version": self.parser_version,
                "config_fingerprint": identity.config_fingerprint,
                "contract_version": "2.0",
            },
            "title": document.core_properties.title or None,
            "metadata": {
                "language": config["language"],
                "page_count": None,
                "slide_count": None,
                "author": document.core_properties.author or None,
                "subject": document.core_properties.subject or None,
                "keywords": keywords,
            },
            "blocks": builder.blocks,
            "warnings": list(canonical_warnings),
        }
        try:
            validate_parsed_document_v2(parsed_document)
        except ParseContractError:
            return ParseResult(None, tuple(item["code"] for item in canonical_warnings), "PARSED_DOCUMENT_CONTRACT_INVALID")
        warning_codes = tuple(dict.fromkeys(item["code"] for item in canonical_warnings))
        return ParseResult(parsed_document, warning_codes, None)

    @staticmethod
    def _inspect_package(path) -> dict[str, object]:
        with ZipFile(path, "r") as archive:
            names = frozenset(archive.namelist())
            document_xml = archive.read("word/document.xml")
            relationships_xml = archive.read("word/_rels/document.xml.rels")
            header_xml = tuple(
                archive.read(name)
                for name in sorted(names)
                if name.startswith("word/header") and name.endswith(".xml")
            )
            footer_xml = tuple(
                archive.read(name)
                for name in sorted(names)
                if name.startswith("word/footer") and name.endswith(".xml")
            )
        root = fromstring(document_xml)
        relationships = fromstring(relationships_xml)
        relationship_types = tuple(
            relationship.get("Type", "")
            for relationship in relationships.findall(f"{{{_REL}}}Relationship")
            if relationship.get("TargetMode") != "External"
        )
        return {
            "names": names,
            "root": root,
            "relationship_types": relationship_types,
            "has_header_text": any(DocxParser._xml_has_text(value) for value in header_xml),
            "has_footer_text": any(DocxParser._xml_has_text(value) for value in footer_xml),
        }

    @staticmethod
    def _xml_has_text(payload: bytes) -> bool:
        root = fromstring(payload)
        return any((node.text or "") for node in root.iter(f"{{{_W}}}t"))

    @staticmethod
    def _emit_image_alt(
        paragraph_element,
        builder: _DocumentBuilder,
        warnings: list[dict[str, object]],
        heading_path: list[str],
        paragraph_native: Mapping[str, object],
        paragraph_index: int,
        preserve_image_alt: bool,
    ) -> None:
        for document_properties in paragraph_element.iter(f"{{{_WP}}}docPr"):
            inline = document_properties.getparent()
            blip = inline.find(f".//{{{_A}}}blip")
            relationship_id = None if blip is None else blip.get(f"{{{_R}}}embed")
            values = (
                ("title", document_properties.get("title")),
                ("description", document_properties.get("descr")),
            )
            explicit = [(source, value) for source, value in values if value]
            native_base = dict(paragraph_native)
            native_base["image_relationship_id"] = relationship_id
            if not explicit:
                warnings.append(_warning("DOCX_IMAGE_WITHOUT_ALT", native_base))
                continue
            if not preserve_image_alt:
                continue
            for alt_source, text in explicit:
                native = dict(native_base)
                native["alt_source"] = alt_source
                builder.add(
                    "image_alt",
                    text,
                    heading_path,
                    native,
                    {"alt_source": alt_source},
                    paragraph_index=paragraph_index,
                )

    @staticmethod
    def _append_package_warnings(
        facts: Mapping[str, object],
        warnings: list[dict[str, object]],
        config: Mapping[str, object],
    ) -> None:
        root = facts["root"]
        assert hasattr(root, "iter")
        tags = {element.tag for element in root.iter()}
        names = facts["names"]
        assert isinstance(names, frozenset)
        relationships = facts["relationship_types"]
        assert isinstance(relationships, tuple)

        checks = (
            (f"{{{_W}}}txbxContent" in tags, "DOCX_TEXTBOX_UNSUPPORTED"),
            (
                f"{{{_W}}}ins" in tags or f"{{{_W}}}del" in tags,
                "DOCX_TRACKED_CHANGES_PARTIAL",
            ),
            (
                f"{{{_W}}}fldSimple" in tags or f"{{{_W}}}instrText" in tags,
                "DOCX_FIELDS_FLATTENED",
            ),
            (f"{{{_M}}}oMath" in tags or f"{{{_M}}}oMathPara" in tags, "DOCX_EQUATION_UNSUPPORTED"),
            (f"{{{_W}}}object" in tags, "DOCX_EMBEDDED_OBJECT_UNSUPPORTED"),
            ("word/comments.xml" in names, "DOCX_COMMENTS_UNSUPPORTED"),
            ("word/endnotes.xml" in names, "DOCX_ENDNOTES_UNSUPPORTED"),
            (
                any(value.endswith("/diagramData") for value in relationships),
                "DOCX_SMARTART_UNSUPPORTED",
            ),
        )
        for present, code in checks:
            if present:
                warnings.append(_warning(code))
        if "word/footnotes.xml" in names:
            warnings.append(_warning("DOCX_FOOTNOTES_SKIPPED", _native_locator(part="footnote")))
        if facts["has_header_text"] and not config["preserve_headers"]:
            warnings.append(
                _warning(
                    "DOCX_HEADERS_SKIPPED",
                    _native_locator(part="header", section_index=0),
                )
            )
        if facts["has_footer_text"] and not config["preserve_footers"]:
            warnings.append(
                _warning(
                    "DOCX_FOOTERS_SKIPPED",
                    _native_locator(part="footer", section_index=0),
                )
            )

    @staticmethod
    def _emit_headers_and_footers(
        document,
        builder: _DocumentBuilder,
        warnings: list[dict[str, object]],
        config: Mapping[str, object],
    ) -> None:
        del warnings
        for kind, enabled in (
            ("header", bool(config["preserve_headers"])),
            ("footer", bool(config["preserve_footers"])),
        ):
            if not enabled:
                continue
            seen_parts: set[str] = set()
            part_index = 0
            for section_index, section in enumerate(document.sections):
                story = section.header if kind == "header" else section.footer
                part_name = str(story.part.partname)
                if part_name in seen_parts:
                    continue
                seen_parts.add(part_name)
                for paragraph_index, paragraph in enumerate(story.paragraphs):
                    style_name = paragraph.style.name if paragraph.style is not None else None
                    builder.add(
                        kind,
                        paragraph.text,
                        [],
                        _native_locator(
                            part=kind,
                            section_index=section_index,
                            part_index=part_index,
                            paragraph_index=paragraph_index,
                            style_name=style_name,
                        ),
                        {"style_name": style_name},
                        paragraph_index=paragraph_index,
                    )
                part_index += 1
