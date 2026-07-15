"""Document-parser contract boundary; no parser implementation in v0.1."""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import rfc8785


class DocumentParser(Protocol):
    """Future document parser port."""

    parser_id: str
    parser_version: str
    supported_extensions: frozenset[str]

    def parse(self, source: Path) -> Mapping[str, object]:
        raise NotImplementedError


_PARAGRAPH_LIKE_KINDS = frozenset(
    {"paragraph", "list_item", "caption", "footnote", "code", "equation", "image_alt"}
)


def _normalized_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n"))


def _deterministic_block_id(
    source_sha256: str,
    kind: str,
    locator: Mapping[str, object],
    text: str,
) -> str:
    canonical_locator = {key: value for key, value in locator.items() if key != "paragraph_id"}
    material = (
        source_sha256.encode("utf-8")
        + b"\0"
        + kind.encode("utf-8")
        + b"\0"
        + rfc8785.dumps(canonical_locator)
        + b"\0"
        + _normalized_text(text).encode("utf-8")
    )
    return hashlib.sha256(material).hexdigest()


def validate_parsed_document_semantics(
    document: Mapping[str, object],
) -> Sequence[str]:
    """Return deterministic cross-field violations not expressible in JSON Schema."""

    errors: list[str] = []
    source = document.get("source")
    blocks = document.get("blocks")
    if not isinstance(source, Mapping) or not isinstance(blocks, Sequence):
        return ()

    source_sha256 = source.get("sha256")
    previous_offset_end: int | None = None
    for index, raw_block in enumerate(blocks):
        if not isinstance(raw_block, Mapping):
            continue
        locator = raw_block.get("locator")
        if not isinstance(locator, Mapping):
            continue

        prefix = f"blocks[{index}].locator"
        if locator.get("paragraph_index") != index:
            errors.append(f"{prefix}.paragraph_index must equal {index}")

        kind = raw_block.get("kind")
        block_id = raw_block.get("block_id")
        paragraph_id = locator.get("paragraph_id")
        if kind in _PARAGRAPH_LIKE_KINDS:
            if paragraph_id != block_id:
                errors.append(f"{prefix}.paragraph_id must equal block_id")
        elif paragraph_id is not None:
            errors.append(f"{prefix}.paragraph_id must be null")

        text = raw_block.get("text")
        if isinstance(text, str):
            if locator.get("char_start") != 0 or locator.get("char_end") != len(_normalized_text(text)):
                errors.append(f"{prefix}.char range must cover normalized text")
            if (
                locator.get("paragraph_index") == index
                and isinstance(source_sha256, str)
                and isinstance(kind, str)
                and isinstance(block_id, str)
            ):
                expected_id = _deterministic_block_id(source_sha256, kind, locator, text)
                if block_id != expected_id:
                    errors.append(f"blocks[{index}].block_id is not deterministic")

        offset_start = locator.get("source_offset_start")
        offset_end = locator.get("source_offset_end")
        if (offset_start is None) != (offset_end is None):
            errors.append(f"{prefix}.source offsets must both be null or integers")
        elif isinstance(offset_start, int) and isinstance(offset_end, int):
            if offset_end < offset_start:
                errors.append(f"{prefix}.source_offset_end must be >= source_offset_start")
            if previous_offset_end is not None and offset_start < previous_offset_end:
                errors.append(f"{prefix}.source offsets overlap previous block")
            previous_offset_end = max(previous_offset_end or 0, offset_end)

        bbox = locator.get("bbox")
        if isinstance(bbox, Mapping):
            left, top, right, bottom = (
                bbox.get("left"),
                bbox.get("top"),
                bbox.get("right"),
                bbox.get("bottom"),
            )
            if all(isinstance(value, (int, float)) for value in (left, top, right, bottom)):
                if right < left or bottom < top:
                    errors.append(f"{prefix}.bbox coordinates must be ordered")

    return tuple(errors)
