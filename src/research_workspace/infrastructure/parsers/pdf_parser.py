"""Deterministic pypdf adapter implementing the approved Gate 1 PDF boundary."""

from __future__ import annotations

from importlib.metadata import version

from pypdf import PasswordType, PdfReader
from pypdf.errors import (
    EmptyFileError,
    FileNotDecryptedError,
    PdfReadError,
    PdfStreamError,
    WrongPasswordError,
)

from research_workspace.application.dto.parsing_dto import ParseRequest, ParseResult
from research_workspace.domain.parsing import (
    ParseContractError,
    build_parse_artifact_identity,
    canonicalize_warnings,
    expand_parser_config,
    make_block_id,
    normalize_quote,
    validate_parsed_document_v2,
)


_PDF_MIME = "application/pdf"


def _document_warning(code: str) -> dict[str, object]:
    return {"code": code, "block_index": None, "native_locator": None}


def _text_block(
    artifact_id: object,
    block_index: int,
    page_number: int,
    text: str,
) -> dict[str, object]:
    normalized = normalize_quote(text)
    locator: dict[str, object] = {
        "page": page_number,
        "slide": None,
        "block_index": block_index,
        "paragraph_index": block_index,
        "paragraph_id": None,
        "heading_path": [],
        "char_start": 0,
        "char_end": len(normalized),
        "source_offset_start": None,
        "source_offset_end": None,
        "bbox": None,
        "native_locator": {
            "type": "pdf",
            "page": page_number,
            "extraction_index": 0,
        },
    }
    block_id = make_block_id(artifact_id, block_index, "paragraph", locator, normalized)
    locator["paragraph_id"] = block_id
    return {
        "block_id": block_id,
        "block_index": block_index,
        "kind": "paragraph",
        "text": normalized,
        "locator": locator,
        "metadata": {},
    }


class PdfParser:
    """Read one immutable PDF snapshot without OCR or non-empty passwords."""

    parser_id = "pypdf"
    parser_version = version("pypdf")
    supported_mime_types = frozenset({_PDF_MIME})

    def parse(self, request: ParseRequest) -> ParseResult:
        try:
            config = expand_parser_config(request.parser_config)
        except ParseContractError:
            return ParseResult(None, (), "UNSUPPORTED_CONFIGURATION")
        if request.mime_type not in self.supported_mime_types or config["ocr_enabled"] is not False:
            return ParseResult(None, (), "UNSUPPORTED_CONFIGURATION")

        container_error = self._container_error(request.snapshot_path)
        if container_error is not None:
            return ParseResult(None, (), container_error)

        try:
            reader = PdfReader(request.snapshot_path, strict=True)
        except (EmptyFileError, FileNotFoundError):
            return ParseResult(None, (), "PDF_CORRUPT")
        except (PermissionError, OSError):
            return ParseResult(None, (), "PDF_READ_ERROR")
        except (WrongPasswordError, FileNotDecryptedError):
            return ParseResult(None, (), "PDF_PASSWORD_REQUIRED")
        except PdfReadError:
            return ParseResult(None, (), "PDF_INVALID_STRUCTURE")

        if reader.is_encrypted:
            try:
                password_type = reader.decrypt("")
            except (WrongPasswordError, FileNotDecryptedError):
                return ParseResult(None, (), "PDF_PASSWORD_REQUIRED")
            except PdfReadError:
                return ParseResult(None, (), "PDF_INVALID_STRUCTURE")
            if password_type == PasswordType.NOT_DECRYPTED:
                return ParseResult(None, (), "PDF_PASSWORD_REQUIRED")

        blocks: list[dict[str, object]] = []
        try:
            for page_number, page in enumerate(reader.pages, start=1):
                extracted = page.extract_text() or ""
                normalized = normalize_quote(extracted)
                if normalized:
                    blocks.append(
                        _text_block(
                            request.parse_artifact_id,
                            len(blocks),
                            page_number,
                            normalized,
                        )
                    )
        except (FileNotDecryptedError, WrongPasswordError):
            return ParseResult(None, (), "PDF_PASSWORD_REQUIRED")
        except NotImplementedError:
            return ParseResult(None, (), "PDF_UNSUPPORTED_FEATURE")
        except (PdfStreamError, PdfReadError, OSError):
            return ParseResult(None, (), "PDF_READ_ERROR")

        warnings = []
        if not blocks:
            warnings = [
                _document_warning("NO_EXTRACTABLE_TEXT"),
                _document_warning("OCR_REQUIRED"),
            ]
        canonical_warnings = canonicalize_warnings(warnings)
        identity = build_parse_artifact_identity(
            request.snapshot_id,
            self.parser_id,
            self.parser_version,
            config,
            "2.0",
        )
        try:
            metadata = reader.metadata
            page_count = len(reader.pages)
        except (FileNotDecryptedError, WrongPasswordError):
            return ParseResult(None, (), "PDF_PASSWORD_REQUIRED")
        except (PdfStreamError, PdfReadError, OSError):
            return ParseResult(None, (), "PDF_READ_ERROR")
        keywords: list[str] = []
        raw_keywords = None if metadata is None else metadata.get("/Keywords")
        if isinstance(raw_keywords, str):
            for raw_keyword in raw_keywords.split(","):
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
            "title": None if metadata is None else metadata.title,
            "metadata": {
                "language": config["language"],
                "page_count": page_count,
                "slide_count": None,
                "author": None if metadata is None else metadata.author,
                "subject": None if metadata is None else metadata.subject,
                "keywords": keywords,
            },
            "blocks": blocks,
            "warnings": list(canonical_warnings),
        }
        try:
            validate_parsed_document_v2(parsed_document)
        except ParseContractError:
            return ParseResult(
                None,
                tuple(item["code"] for item in canonical_warnings),
                "PARSED_DOCUMENT_CONTRACT_INVALID",
            )
        return ParseResult(
            parsed_document,
            tuple(item["code"] for item in canonical_warnings),
            None,
        )

    @staticmethod
    def _container_error(path) -> str | None:
        try:
            with path.open("rb") as stream:
                header = stream.read(8)
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 1024))
                tail = stream.read()
        except FileNotFoundError:
            return "PDF_CORRUPT"
        except (PermissionError, OSError):
            return "PDF_READ_ERROR"
        if not header.startswith(b"%PDF-"):
            return "PDF_CORRUPT"
        if b"%%EOF" not in tail:
            return "PDF_TRUNCATED"
        return None
