"""Read-only projection for terminal Gate 1 import/parse outcomes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from research_workspace.presentation.view_models.imports import (
    ImportRowViewModel,
    ImportsViewModel,
    localized_parse_status,
)


@dataclass(frozen=True, slots=True)
class ImportReadRecord:
    filename: str
    parse_status: str
    error_code: str | None
    block_count: int | None


class GetImports:
    def __init__(self, reader: Callable[[], Iterable[ImportReadRecord]]) -> None:
        self._reader = reader

    def execute(self) -> ImportsViewModel:
        rows: list[ImportRowViewModel] = []
        for record in self._reader():
            if record.parse_status == "succeeded":
                state = "searchable" if (record.block_count or 0) > 0 else "zero_text"
            elif record.parse_status == "failed":
                state = (
                    "password_required"
                    if record.error_code == "PDF_PASSWORD_REQUIRED"
                    else "parse_failed"
                )
            else:
                raise ValueError("UNKNOWN_IMPORT_STATUS")
            rows.append(
                ImportRowViewModel(record.filename, localized_parse_status(state))
            )
        return ImportsViewModel(tuple(rows))
