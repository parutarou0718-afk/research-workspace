"""Versioned reversible text projection for DOCX/PPTX tables."""

from __future__ import annotations

from collections.abc import Sequence


TABLE_TEXT_VERSION = "tsv-escaped-1"


def _escape_cell(cell: str) -> str:
    return (
        cell.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def escape_table_tsv(rows: Sequence[Sequence[str]]) -> str:
    return "\n".join("\t".join(_escape_cell(cell) for cell in row) for row in rows)
