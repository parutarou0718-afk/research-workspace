"""Immutable parse DTOs fixed by the Gate 1 Interface Ledger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from research_workspace.domain.operations import freeze_json


@dataclass(frozen=True)
class ParseRequest:
    parse_artifact_id: UUID
    snapshot_id: UUID
    snapshot_path: Path
    snapshot_sha256: str
    mime_type: str
    parser_config: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parser_config", freeze_json(self.parser_config))


@dataclass(frozen=True)
class ParseResult:
    parsed_document: Mapping[str, object] | None
    warning_codes: tuple[str, ...]
    error_code: str | None

    def __post_init__(self) -> None:
        if self.parsed_document is not None:
            object.__setattr__(self, "parsed_document", freeze_json(self.parsed_document))
        object.__setattr__(self, "warning_codes", tuple(self.warning_codes))


@dataclass(frozen=True)
class ParseSuccessDTO:
    operation_id: UUID
    parse_artifact_id: UUID
    parse_attempt_id: UUID
    parsed_document: Mapping[str, object]
    output_sha256: str
    derived_file_sha256: str
    derived_relative_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parsed_document", freeze_json(self.parsed_document))


@dataclass(frozen=True)
class ParseFailureDTO:
    operation_id: UUID
    parse_artifact_id: UUID
    parse_attempt_id: UUID
    error_code: str
    warning_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "warning_codes", tuple(self.warning_codes))
