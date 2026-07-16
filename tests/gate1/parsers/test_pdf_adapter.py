from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import rfc8785

from research_workspace.domain.parsing import (
    DEFAULT_PARSER_CONFIG,
    ParseContractError,
    build_parse_artifact_identity,
    validate_parsed_document_v2,
)
from research_workspace.infrastructure.parsers.pdf_parser import PdfParser


def _plain(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def test_pdf_fixture_manifest_matches_structural_boundary() -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    pdf_entries = [
        item for item in manifest["fixtures"] if item["relative_path"].startswith("pdf/")
    ]

    assert [entry["relative_path"] for entry in pdf_entries] == [
        "pdf/normal_text.pdf",
        "pdf/empty_password.pdf",
        "pdf/password_required.pdf",
        "pdf/image_only.pdf",
        "pdf/corrupt.pdf",
        "pdf/truncated.pdf",
    ]
    assert all(entry["generator_version"] == "gate1-pdf-1" for entry in pdf_entries)
    assert (fixture_root / "pdf/corrupt.pdf").read_bytes()[:5] != b"%PDF-"
    truncated = (fixture_root / "pdf/truncated.pdf").read_bytes()
    assert truncated.startswith(b"%PDF-")
    assert b"%%EOF" not in truncated[-32:]
    image_reader = PdfReader(fixture_root / "pdf/image_only.pdf", strict=True)
    assert len(image_reader.pages) == 1
    assert image_reader.pages[0].extract_text() == ""
    assert len(image_reader.pages[0].images) == 1
    assert all(
        b"\x00" in (fixture_root / entry["relative_path"]).read_bytes()
        for entry in pdf_entries
    )


@pytest.mark.parametrize(
    ("fixture", "expected"),
    (
        ("normal_text.pdf", "succeeded"),
        ("empty_password.pdf", "succeeded"),
        ("password_required.pdf", "PDF_PASSWORD_REQUIRED"),
        ("corrupt.pdf", "PDF_CORRUPT"),
        ("truncated.pdf", "PDF_TRUNCATED"),
    ),
)
def test_pdf_boundary(snapshot_request, fixture: str, expected: str) -> None:
    result = PdfParser().parse(snapshot_request(fixture))

    actual = "succeeded" if result.error_code is None else result.error_code
    assert actual == expected


def test_normal_pdf_emits_one_contract_valid_block_per_page(snapshot_request) -> None:
    result = PdfParser().parse(snapshot_request("normal_text.pdf"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    validate_parsed_document_v2(document)
    assert [block["text"] for block in document["blocks"]] == [
        "Page one text",
        "Page two text",
    ]
    assert [block["locator"]["page"] for block in document["blocks"]] == [1, 2]
    assert [block["locator"]["native_locator"] for block in document["blocks"]] == [
        {"type": "pdf", "page": 1, "extraction_index": 0},
        {"type": "pdf", "page": 2, "extraction_index": 0},
    ]
    assert document["metadata"]["page_count"] == 2
    assert result.warning_codes == ()


def test_image_only_is_contract_valid_zero_block_success(snapshot_request) -> None:
    result = PdfParser().parse(snapshot_request("image_only.pdf"))

    assert result.error_code is None
    document = _plain(result.parsed_document)
    validate_parsed_document_v2(document)
    assert document["blocks"] == []
    assert document["metadata"]["page_count"] == 1
    assert [warning["code"] for warning in document["warnings"]] == [
        "NO_EXTRACTABLE_TEXT",
        "OCR_REQUIRED",
    ]
    assert result.warning_codes == ("NO_EXTRACTABLE_TEXT", "OCR_REQUIRED")


def test_ocr_request_is_rejected_before_pdf_open(snapshot_request, monkeypatch) -> None:
    opened = False

    def forbidden_reader(*_args, **_kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("PDF must not be opened")

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.pdf_parser.PdfReader", forbidden_reader
    )
    result = PdfParser().parse(
        snapshot_request("normal_text.pdf", {"ocr_enabled": True})
    )

    assert result.error_code == "UNSUPPORTED_CONFIGURATION"
    assert result.parsed_document is None
    assert opened is False


def test_future_ocr_config_has_distinct_identity_but_remains_non_executable(
    snapshot_request,
) -> None:
    request = snapshot_request("image_only.pdf")
    baseline = build_parse_artifact_identity(
        request.snapshot_id,
        "pypdf",
        PdfParser.parser_version,
        DEFAULT_PARSER_CONFIG,
        "2.0",
    )
    future_config = _plain(DEFAULT_PARSER_CONFIG)
    future_config["ocr_enabled"] = True
    future_fingerprint = hashlib.sha256(rfc8785.dumps(future_config)).hexdigest()

    assert baseline.config_fingerprint != future_fingerprint
    with pytest.raises(ParseContractError, match="UNSUPPORTED_CONFIGURATION"):
        build_parse_artifact_identity(
            request.snapshot_id,
            "pypdf",
            PdfParser.parser_version,
            future_config,
            "2.0",
        )
    assert PdfParser().parse(
        snapshot_request("image_only.pdf", {"ocr_enabled": True})
    ).error_code == "UNSUPPORTED_CONFIGURATION"


def test_password_boundary_has_no_password_interface_or_diagnostic_leak(
    snapshot_request, caplog
) -> None:
    result = PdfParser().parse(snapshot_request("password_required.pdf"))

    assert tuple(inspect.signature(PdfParser.parse).parameters) == ("self", "request")
    assert "gate1-fixture-password" not in inspect.getsource(
        __import__(
            "research_workspace.infrastructure.parsers.pdf_parser",
            fromlist=["PdfParser"],
        )
    )
    assert result.error_code == "PDF_PASSWORD_REQUIRED"
    assert result.parsed_document is None
    assert caplog.records == []


def test_raw_pypdf_exception_detail_never_escapes(snapshot_request, monkeypatch, caplog) -> None:
    def broken_reader(*_args, **_kwargs):
        raise PdfReadError("internal pypdf parser detail")

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.pdf_parser.PdfReader", broken_reader
    )
    result = PdfParser().parse(snapshot_request("normal_text.pdf"))

    assert result.error_code == "PDF_INVALID_STRUCTURE"
    assert "internal pypdf parser detail" not in repr(result)
    assert caplog.records == []


def test_metadata_read_error_maps_to_stable_code(snapshot_request, monkeypatch, caplog) -> None:
    class Page:
        @staticmethod
        def extract_text() -> str:
            return "Page text"

    class Reader:
        is_encrypted = False
        pages = (Page(),)

        @property
        def metadata(self):
            raise PdfReadError("metadata implementation detail")

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.pdf_parser.PdfReader",
        lambda *_args, **_kwargs: Reader(),
    )

    result = PdfParser().parse(snapshot_request("normal_text.pdf"))

    assert result.error_code == "PDF_READ_ERROR"
    assert "metadata implementation detail" not in repr(result)
    assert caplog.records == []


def test_pdf_parser_opens_only_declared_snapshot(snapshot_request, monkeypatch) -> None:
    request = snapshot_request("normal_text.pdf")
    opened: list[Path] = []
    real_reader = PdfReader

    def recording_reader(path, *args, **kwargs):
        opened.append(Path(path))
        return real_reader(path, *args, **kwargs)

    monkeypatch.setattr(
        "research_workspace.infrastructure.parsers.pdf_parser.PdfReader", recording_reader
    )
    result = PdfParser().parse(request)

    assert result.error_code is None
    assert opened == [request.snapshot_path]


def test_pdf_same_request_has_deterministic_result(snapshot_request) -> None:
    request = snapshot_request("normal_text.pdf")

    first = _plain(PdfParser().parse(request).parsed_document)
    second = _plain(PdfParser().parse(request).parsed_document)

    assert first == second
